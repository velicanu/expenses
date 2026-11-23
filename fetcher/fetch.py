"""`python -m fetcher fetch ACCOUNT MONTH...`: on the account's saved browser profile, check the login and, if it holds,
download the statements for the months asked. Prints one JSON line:

    {"state": "logged_in", "files": [{"month": "2026-11", "csv": "..."}]}
    {"state": "login_required" | "challenge" | "unknown", "files": [], "detail": "HTTP 403 at id.venmo.com/signin"}
    {"state": "error", "message": "...", "files": []}                       something broke; the message has no page text

The browser service (browserd.py) runs this and hands the JSON to the expense app, which decides what enters the data.
"""

import json
import sys
from urllib.parse import urlparse

from . import institutions, venmo
from .session import facts_from, launch

STATES = {
    institutions.LOGGED_IN: "logged_in",
    institutions.LOGIN_REQUIRED: "login_required",
    institutions.CHALLENGE: "challenge",
    institutions.UNKNOWN: "unknown",
}


def fetch(account: str, months: list[str], profiles: str = "/profiles") -> dict:
    from playwright.sync_api import (
        sync_playwright,
    )  # only when a fetch really runs: the tests need no browser

    inst = institutions.get(account)
    with sync_playwright() as p:
        ctx = launch(p, profiles, account)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            response = page.goto(
                inst.home_url, wait_until="domcontentloaded", timeout=60000
            )
            page.wait_for_timeout(5000)
            facts = facts_from(page, response)
            state = STATES[inst.classify(facts)]
            if state != "logged_in":
                # where the page ended up and its status: enough to tell a login page from a bot challenge, no page text
                where = urlparse(facts.url)
                return {
                    "state": state,
                    "files": [],
                    "detail": f"HTTP {facts.status} at {where.netloc}{where.path}",
                }
            return {"state": "logged_in", "files": venmo.fetch_statements(page, months)}
        finally:
            ctx.close()  # closes Chrome properly, so it keeps what it saved


def main(account: str, months: list[str]) -> int:
    try:
        result = fetch(account, months)
    except Exception as e:  # never put page text or a traceback in the reply
        result = {"state": "error", "message": f"{type(e).__name__}", "files": []}
        if isinstance(e, venmo.VenmoPageError):
            result["message"] = str(e)
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
