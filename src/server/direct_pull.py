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

A visit to a bank is rate limited and only made when it can work:
- after a successful fetch the same account is left alone for MIN_INTERVAL, so a second click never means a second visit;
- a saved web login does not last (Venmo's expired within about 40 minutes), so a plain Refresh only visits an account whose
  login was seen working within SESSION_TRUST; otherwise it says the login is needed, with a link to the hand login, and
  makes no visit. An account found logged out is not visited again until a person logs in;
- finishing a hand login sends the person here with that one account and `fresh`: the login was seconds ago, so the
  interval and the trust window do not apply, and the fetch runs straight away.
A lapsed login is information, not an error: Refresh data picks up the accounts whose login persists.
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
SESSION_TRUST = (
    25 * 60
)  # a login seen working this recently is believed to still work (Venmo's lasted 30-40 minutes)
AUTOLOGIN_RETRY = (
    30 * 60
)  # after a failed automatic login, none for this long (a site that refuses is not hammered)
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

    def fetch(self, account: str, months: list[str], autologin: bool = False) -> dict:
        body = {"account": account, "months": months}
        if autologin:
            body["autologin"] = (
                True  # one automatic login attempt is allowed if the saved login has lapsed
            )
        req = urllib.request.Request(
            self._url + "/fetch",
            data=json.dumps(body).encode(),
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


def _ago(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes} min" if minutes < 90 else f"{minutes // 60} h"


def _name(account: dict) -> str:
    return (account.get("institution") or "the site").capitalize()


def refresh_account(
    store, account: dict, client, today: date, now: float, fresh: bool = False
) -> dict:
    alias = account["alias"]
    if client is None:
        return {"alias": alias, "error": "the browser service is not configured"}
    last = account.get("last_success")
    if not fresh and last and now - last < MIN_INTERVAL:
        wait = int((MIN_INTERVAL - (now - last)) // 60) + 1
        return {
            "alias": alias,
            "skipped": f"fetched moments ago; it can be fetched again in about {wait} min",
        }
    # An account set up for automatic login (a site where that works: no captcha) may log itself in once if its saved
    # login has lapsed, but not again for AUTOLOGIN_RETRY after a failed attempt: a site that refuses is not hammered.
    failed_at = account.get("autologin_failed")
    retry_blocked = bool(failed_at and now - failed_at < AUTOLOGIN_RETRY)
    may_autologin = bool(account.get("autologin")) and not retry_blocked and not fresh
    if not fresh and not may_autologin:
        seen = account.get("last_ok")
        if not seen or now - seen > SESSION_TRUST:
            how = (
                f"last seen logged in {_ago(now - seen)} ago"
                if seen
                else "not logged in since it was last checked"
            )
            why = (
                f"the automatic login failed {_ago(now - failed_at)} ago and is not retried yet; "
                if retry_blocked and account.get("autologin")
                else ""
            )
            return {
                "alias": alias,
                "login_needed": f"{why}the saved login has probably expired ({how}); log in by hand to fetch it",
                "login_url": client.login_link(alias),
            }
    ids, latest = known(store.raw_dir, alias)
    months = months_to_fetch(latest, today)
    try:
        result = client.fetch(alias, months, autologin=may_autologin)
    except FetcherError as e:
        return {"alias": alias, "error": str(e)}
    state = result.get("state")
    auto = result.get("auto_login")
    if auto == "failed":
        store.mark_direct_autologin(alias, now)  # no automatic retry for a while
    elif auto == "ok":
        store.mark_direct_autologin(alias, None)
    if (
        state == "error"
    ):  # the fetch itself broke: say so, do not call it a login problem
        return {"alias": alias, "error": result.get("message") or "the fetch failed"}
    if state != "logged_in":
        store.mark_direct_session(
            alias, None
        )  # known logged out: no more visits until a person logs in
        name = _name(account)
        reason = {
            "login_required": f"{name} is asking for a login",
            "challenge": f"{name} showed its bot check",
        }.get(state, "could not tell whether the session is logged in")
        detail = result.get(
            "detail"
        )  # e.g. "HTTP 403 at id.venmo.com/signin": status and page, never page text
        tried = (
            f"the automatic login did not get in ({reason}"
            + (f", {detail}" if detail else "")
            + ")"
            if auto == "failed"
            else None
        )
        return {
            "alias": alias,
            "login_needed": f"{tried}; log in by hand to fetch it"
            if tried
            else (
                f"{reason} ({detail}); log in by hand to fetch it"
                if detail
                else f"{reason}; log in by hand to fetch it"
            ),
            "state": state,
            "login_url": client.login_link(alias),
            **({"auto_login": "failed"} if auto == "failed" else {}),
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
    out = {"alias": alias, "pulled": pulled, "months": len(parsed)}
    if auto == "ok":
        out["auto_login"] = (
            "ok"  # the saved login had lapsed and the automatic login got back in
        )
    return out


def refresh_direct(
    store,
    client,
    today: date,
    now: float | None = None,
    only: str | None = None,
    fresh: bool = False,
) -> list[dict]:
    """Every direct account (or just `only`). fresh: a person has just logged in to it, so fetch regardless of the
    interval and the trust window."""
    now = time.time() if now is None else now
    return [
        refresh_account(store, a, client, today, now, fresh=fresh)
        for a in store.direct_accounts()
        if only is None or a["alias"] == only
    ]
