"""`python -m fetcher fetch ACCOUNT MONTH...`: on the account's saved browser profile, check the login and, if it holds,
download the statements for the months asked. Prints one JSON line:

    {"state": "logged_in", "files": [{"month": "2026-11", "csv": "..."}]}
    {"state": "login_required" | "challenge" | "unknown", "files": [], "detail": "HTTP 403 at id.venmo.com/signin"}
    {"state": "error", "message": "...", "files": []}                       something broke; the message has no page text

The browser service (browserd.py) runs this and hands the JSON to the expense app, which decides what enters the data.
"""

import json
import os
import sys
from urllib.parse import urlparse

from . import autologin, institutions, venmo
from .session import facts_from, launch

STATES = {
    institutions.LOGGED_IN: "logged_in",
    institutions.LOGIN_REQUIRED: "login_required",
    institutions.CHALLENGE: "challenge",
    institutions.UNKNOWN: "unknown",
}


def _open(p, inst, account, profiles):
    """Chrome (driven by Playwright) on the account's profile at the page only a logged-in session opens, and the verdict."""
    ctx = launch(p, profiles, account)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    response = page.goto(inst.home_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    facts = facts_from(page, response)
    return ctx, page, STATES[inst.classify(facts)], facts


def _where(facts) -> str:
    """Where the page ended up and its status: enough to tell a login page from a bot challenge, no page text."""
    where = urlparse(facts.url)
    return f"HTTP {facts.status} at {where.netloc}{where.path}"


def fetch(
    account: str,
    months: list[str],
    profiles: str = "/profiles",
    allow_autologin: bool = False,
) -> dict:
    from playwright.sync_api import (
        sync_playwright,
    )  # only when a fetch really runs: the tests need no browser

    inst = institutions.get(account)
    auto = "not attempted"
    with sync_playwright() as p:
        ctx, page, state, facts = _open(p, inst, account, profiles)
        try:
            if state != "logged_in" and allow_autologin:
                if not inst.autologin:
                    auto = "unsupported"
                else:
                    # the login lapsed: try once with Chrome's saved login in a plain Chrome (no Playwright), then look again
                    ctx.close()
                    ctx = None
                    try:
                        autologin.run(account, profiles, inst.autologin)
                    except autologin.AutoLoginError as e:
                        return {
                            "state": state,
                            "files": [],
                            "detail": _where(facts),
                            "auto_login": "failed",
                            "auto_login_error": str(e),
                        }
                    ctx, page, state, facts = _open(p, inst, account, profiles)
                    auto = "ok" if state == "logged_in" else "failed"
            if state == "logged_in" and inst.download is None:
                return {
                    "state": "error",
                    "message": f"downloading from {inst.name} is not built yet",
                    "files": [],
                    "auto_login": auto,
                }
            if state != "logged_in":
                return {
                    "state": state,
                    "files": [],
                    "detail": _where(facts),
                    "auto_login": auto,
                }
            return {
                "state": "logged_in",
                "files": inst.download(page, months),
                "auto_login": auto,
            }
        finally:
            if ctx is not None:
                ctx.close()  # closes Chrome properly, so it keeps what it saved


def main(account: str, months: list[str]) -> int:
    try:
        result = fetch(
            account,
            months,
            allow_autologin=os.environ.get("FETCHER_AUTOLOGIN") == "1",
        )
    except Exception as e:  # never put page text or a traceback in the reply
        result = {"state": "error", "message": f"{type(e).__name__}", "files": []}
        if isinstance(e, venmo.VenmoPageError):
            result["message"] = str(e)
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
