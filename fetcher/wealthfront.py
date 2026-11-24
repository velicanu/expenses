"""Wealthfront's cash account activity, driven by a person's saved login: open the account, press its own
"Download activity" -> "All time" -> "Download CSV".

Nothing here logs in or gets past a check; it only works on a session that is already logged in (by hand or by
autologin.py) and reports a page error when the site is not what it was on 2026-11-24, when this was worked out:
dashboard -> the card named "Individual Cash Account" -> "See all activity" (/cash-activity) -> "Download activity"
opens a dialog with a period choice (the "All time" label) and a "Download CSV" link. The export has the header
Transaction date,Description,Type,Amount, newest first.
"""

import re

from .pageutil import PageError, wait_visible

DASHBOARD_URL = "https://www.wealthfront.com/dashboard"
ACCOUNT_NAME = (
    "Individual Cash Account"  # found by its words, never by an account number
)


def download_all(page, account_name: str = ACCOUNT_NAME) -> str:
    """The text of the all-time activity CSV for one account."""
    if "/dashboard" not in page.url:
        page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
    wait_visible(
        page.get_by_text(account_name, exact=False), f"the {account_name} card"
    ).click()
    wait_visible(
        page.get_by_text(re.compile(r"see all activity", re.I)),
        "the See all activity link",
    ).click()
    wait_visible(
        page.get_by_role("button", name=re.compile(r"download activity", re.I)),
        "the Download activity button",
    ).click()
    wait_visible(
        page.get_by_text("All time", exact=True), "the All time choice"
    ).click()
    link = wait_visible(
        page.get_by_text("Download CSV", exact=True), "the Download CSV link"
    )
    with page.expect_download(timeout=60000) as download:
        link.click()
    with open(download.value.path(), newline="", encoding="utf-8-sig") as f:
        text = f.read()
    if not text.startswith("Transaction date,"):
        raise PageError("the download is not the activity CSV the app expects")
    return text


def fetch_statements(page, months: list[str]) -> list[dict]:
    """One file with everything the account has; the months asked for do not apply to this export."""
    return [{"month": "all", "csv": download_all(page)}]
