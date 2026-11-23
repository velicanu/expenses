"""Direct pulls: accounts fetched by a real browser on the person's saved login (the browser container in
velicanu/server's fetcher), as a second source for Refresh data next to Plaid.

The browser side only downloads: for Venmo, the monthly statement CSVs from account.venmo.com, one per month asked for.
Everything that decides what enters the data is here, so it can be tested without a browser:

- a statement is checked against the columns the pipeline expects (a changed export fails loudly instead of being
  ingested wrong); its preamble and its balance summary rows are dropped;
- a transaction already in any raw file of the account (matched by Venmo's ID) is skipped, and so is one still pending,
  which arrives in a later pull with its final status;
- new transactions are only ever APPENDED to one file, `<account>-direct.csv`. Edits are keyed by position in a raw
  file (`<source_file>-<line>`), so a file that only grows keeps every earlier row where it was.

A visit to a bank is rate limited: after a successful fetch the same account is left alone for MIN_INTERVAL, so a second
click of Refresh data never means a second visit. (A fetch that found the login expired does not start the clock: the
person fixes the login and clicks again.)
"""

import csv
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

MIN_INTERVAL = 600  # seconds between successful fetches of one account
MAX_MONTHS = 24  # the most one pull will ask for
FIRST_PULL_MONTHS = 12  # when an account has no data at all yet

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_SCHEMAS = json.loads(
    (Path(__file__).parent.parent / "card_definitions.json").read_text()
)


class DirectPullError(Exception):
    pass


def schema(institution: str) -> list[str]:
    try:
        return list(_SCHEMAS[institution]["schema"])
    except KeyError:
        raise DirectPullError(f"no layout for {institution!r}") from None


# --- reading a statement ------------------------------------------------------------------------------------------


def parse_statement(text: str, institution: str = "venmo"):
    """(header, transaction rows) from one downloaded statement. Raises DirectPullError if it is not the layout the
    pipeline knows."""
    rows = list(csv.reader(io.StringIO(text, newline="")))
    start = next((i for i, r in enumerate(rows) if "Datetime" in r and "ID" in r), None)
    if start is None:
        raise DirectPullError("the download is not a Venmo statement")
    header = rows[start]
    if header != schema(institution):
        raise DirectPullError("Venmo changed the columns of its statement")
    id_col, date_col = header.index("ID"), header.index("Datetime")
    transactions = [
        r
        for r in rows[start + 1 :]
        if len(r) == len(header) and r[id_col].strip() and _DATE.match(r[date_col])
    ]
    return header, transactions


def _raw_files(raw_dir: Path, account: str):
    yield from sorted(raw_dir.glob(f"{account}.csv"))
    yield from sorted(raw_dir.glob(f"{account}-*.csv"))


def known(raw_dir: Path, account: str) -> tuple[set[str], date | None]:
    """The IDs already in the account's raw files, and the date of the latest transaction among them."""
    ids, latest = set(), None
    for path in _raw_files(raw_dir, account):
        try:
            rows = list(csv.reader(open(path, newline="")))
        except (OSError, csv.Error):
            continue
        head = next((r for r in rows[:5] if "ID" in r and "Datetime" in r), None)
        if (
            head is None
        ):  # another layout (e.g. a Plaid dump): not Venmo's statement rows
            continue
        id_col, date_col = head.index("ID"), head.index("Datetime")
        for r in rows[rows.index(head) + 1 :]:
            if len(r) > max(id_col, date_col) and r[id_col].strip():
                ids.add(r[id_col].strip())
                if _DATE.match(r[date_col]):
                    d = date.fromisoformat(r[date_col][:10])
                    latest = d if latest is None or d > latest else latest
    return ids, latest


def months_to_fetch(latest: date | None, today: date) -> list[str]:
    """Which months to download, oldest first: from the month of the latest known transaction, or the previous month if
    that is more recent (late items land in the month before), through this month."""
    first_of_this = today.replace(day=1)
    previous = _add_months(first_of_this, -1)
    if latest is None:
        start = _add_months(first_of_this, -(FIRST_PULL_MONTHS - 1))
    else:
        start = min(latest.replace(day=1), previous)
    start = max(start, _add_months(first_of_this, -(MAX_MONTHS - 1)))
    out, m = [], start
    while m <= first_of_this:
        out.append(f"{m.year:04d}-{m.month:02d}")
        m = _add_months(m, 1)
    return out


def _add_months(d: date, n: int) -> date:
    index = d.year * 12 + (d.month - 1) + n
    return date(index // 12, index % 12 + 1, 1)


# --- adding what is new ------------------------------------------------------------------------------------------


def append_new(
    raw_dir: Path, account: str, header: list[str], transactions: list[list[str]]
) -> int:
    """Append the transactions not already known (and not pending) to <account>-direct.csv; returns how many."""
    ids, _ = known(raw_dir, account)
    status_col, id_col, date_col = (
        header.index("Status"),
        header.index("ID"),
        header.index("Datetime"),
    )
    fresh, seen = [], set()
    for r in transactions:
        tid = r[id_col].strip()
        if tid in ids or tid in seen or r[status_col].strip().lower() == "pending":
            continue
        seen.add(tid)
        fresh.append(r)
    if not fresh:
        return 0
    fresh.sort(key=lambda r: r[date_col])  # stable: ties keep the statement's order
    target = raw_dir / f"{account}-direct.csv"
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    if target.exists() and target.stat().st_size:
        with open(target, newline="") as f:  # newline="": bytes exactly as they are
            text = f.read()
        if not text.endswith("\n"):
            text += "\n"
        out.write(text)
    else:
        writer.writerow(header)
    writer.writerows(fresh)
    tmp = target.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="") as f:
        f.write(out.getvalue())
    os.replace(
        tmp, target
    )  # the old lines are byte-for-byte where they were; only new ones follow
    return len(fresh)


# --- asking the browser service ----------------------------------------------------------------------------------


class FetcherError(Exception):
    pass


class FetcherClient:
    """The browser container's API on 127.0.0.1 with the shared token. Errors say what happened, never what was sent."""

    def __init__(
        self,
        url: str,
        token: str,
        login_url: str = "",
        opener=urllib.request.urlopen,
    ):
        self._url, self._token, self._open = url.rstrip("/"), token, opener
        self.login_url = login_url.rstrip("/")

    def login_link(self, account: str) -> str | None:
        """Where the person fixes a login that has lapsed (the credentials page's hand-login)."""
        return f"{self.login_url}/login?account={account}" if self.login_url else None

    def fetch(self, account: str, months: list[str]) -> dict:
        req = urllib.request.Request(
            self._url + "/fetch",
            data=json.dumps({"account": account, "months": months}).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._open(req, timeout=420) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                try:
                    raise FetcherError(json.load(e)["detail"]) from None
                except (ValueError, KeyError, TypeError):
                    pass
            raise FetcherError(f"the browser service refused (HTTP {e.code})") from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise FetcherError(
                f"cannot reach the browser service ({type(e).__name__})"
            ) from None


# --- one account, then all ---------------------------------------------------------------------------------------


def refresh_account(store, account: dict, client, today: date, now: float) -> dict:
    alias = account["alias"]
    last = account.get("last_success")
    if last and now - last < MIN_INTERVAL:
        wait = int((MIN_INTERVAL - (now - last)) // 60) + 1
        return {
            "alias": alias,
            "skipped": f"fetched moments ago; it can be fetched again in about {wait} min",
        }
    if client is None:
        return {"alias": alias, "error": "the browser service is not configured"}
    ids, latest = known(store.raw_dir, alias)
    months = months_to_fetch(latest, today)
    try:
        result = client.fetch(alias, months)
    except FetcherError as e:
        return {"alias": alias, "error": str(e)}
    state = result.get("state")
    if (
        state == "error"
    ):  # the fetch itself broke: say so, do not call it a login problem
        return {"alias": alias, "error": result.get("message") or "the fetch failed"}
    if state != "logged_in":
        reason = {
            "login_required": "Venmo is asking for a login",
            "challenge": "Venmo challenged the automated browser (a bot check, not a login)",
        }.get(state, "could not tell whether the session is logged in")
        detail = result.get(
            "detail"
        )  # e.g. "HTTP 403 at id.venmo.com/signin": status and page, never page text
        return {
            "alias": alias,
            "needs_login": True,
            "state": state,
            "login_url": client.login_link(alias),
            "error": f"{reason} ({detail})" if detail else reason,
        }
    pulled, header = 0, None
    try:
        parsed = [
            parse_statement(f["csv"], account.get("institution", "venmo"))
            for f in sorted(result.get("files", []), key=lambda f: f["month"])
        ]
        for header, transactions in parsed:
            pulled += append_new(store.raw_dir, alias, header, transactions)
    except DirectPullError as e:
        return {"alias": alias, "error": str(e)}
    store.mark_direct_success(alias, now)
    return {"alias": alias, "pulled": pulled, "months": len(parsed)}


def refresh_direct(store, client, today: date, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    return [
        refresh_account(store, a, client, today, now) for a in store.direct_accounts()
    ]
