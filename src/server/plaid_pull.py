"""Pull new transactions for the linked Plaid accounts into the user's data, then rebuild.

Ported from the Streamlit app's pull(). Differences: the Plaid keys come from bao (bao.PlaidKeys), errors
are returned per account instead of drawn on a page, access tokens are never returned or logged, and the
paging is fixed. The old loop advanced the offset once per *transaction* inside the page loop, so an account
with more than one page (500) in the window was silently cut off after the first.
"""

import json
import logging
from datetime import date, datetime, timedelta

from cardstore import dump_csv, merge_tx
from fsutil import make_dirs

log = logging.getLogger("expenses.plaid")
PAGE = 500


def make_client(keys: dict):
    import plaid
    from plaid.api import plaid_api

    configuration = plaid.Configuration(
        host=plaid.Environment.Production,
        api_key={"clientId": keys["client_id"], "secret": keys["secret"]},
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def fetch_transactions(client, access_token: str, start: str, end: str):
    from plaid.model.transactions_get_request import TransactionsGetRequest
    from plaid.model.transactions_get_request_options import (
        TransactionsGetRequestOptions,
    )

    out, offset = [], 0
    while True:
        response = client.transactions_get(
            TransactionsGetRequest(
                access_token=access_token,
                start_date=datetime.strptime(start, "%Y-%m-%d").date(),
                end_date=datetime.strptime(end, "%Y-%m-%d").date(),
                options=TransactionsGetRequestOptions(count=PAGE, offset=offset),
            )
        )
        page = response["transactions"]
        out.extend(page)
        offset += len(page)
        if not page or offset >= response["total_transactions"]:
            return out


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not serializable")


def _plaid_error(exc) -> str:
    """The Plaid error code and message, from an ApiException body; never the request."""
    try:
        err = json.loads(exc.body)
        return f"{err['error_code']}: {err['error_message']}"
    except Exception:
        return type(exc).__name__


def pull_all(store, keys, client_factory=make_client, today=date.today) -> dict:
    """keys: bao.PlaidKeys. Raises PlaidUnavailable if the keys cannot be had."""
    accounts = (store.config().get("linked_accounts") or {}).items()
    if not accounts:
        return {"accounts": [], "pipeline": None}
    client = client_factory(keys.get())
    make_dirs([store.cards_dir, store.raw_dir])
    results, new_starts = [], {}
    for key, card in accounts:
        alias = card.get("alias", key)
        try:
            transactions = fetch_transactions(
                client, card["token"], card["start_date"], today().isoformat()
            )
        except Exception as e:
            log.warning("pull failed for %s: %s", alias, type(e).__name__)
            results.append({"alias": alias, "error": _plaid_error(e)})
            continue
        # the card file is replaced whole, like before; merge_tx then adds only unseen transaction ids
        with open(store.cards_dir / f"{alias}.json", "w") as outfile:
            for tx in transactions:
                record = tx.to_dict()
                record["institution"] = card.get("institution")
                outfile.write(json.dumps(record, default=_json_default) + "\n")
        db_file = merge_tx(str(store.cards_dir), alias)
        if db_file:
            dump_csv(str(store.dir), db_file, alias)
        new_starts[key] = (today() - timedelta(days=30)).isoformat()
        results.append({"alias": alias, "pulled": len(transactions)})

    def remember(cfg):
        for key, start in new_starts.items():
            cfg["linked_accounts"][key]["start_date"] = start

    if new_starts:
        store.update_config(remember)
    pipeline = store.run_pipeline() if new_starts else None
    return {"accounts": results, "pipeline": pipeline}
