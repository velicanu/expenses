"""Venmo's statement page, driven by a person's saved login: pick a month, press its own Download CSV button.

Nothing here logs in, types credentials, or gets past a check: it only works on a profile a person logged in by hand
(browserd.py), and reports "login needed" when that has lapsed. It downloads what the page offers a logged-in person.

What was observed (2026-11-23) on account.venmo.com/statement: a text field with the placeholder "MMMM YYYY" selects the
month (typing "December 2025" and Enter works; the month grid has no visible year step), and the "Download CSV" button
exports that month as VenmoStatement_<Month>_<year>.csv: two preamble lines, the header, a beginning-balance row, the
transactions oldest first, an ending-balance row.
"""

import calendar
import time

STATEMENT_URL = "https://account.venmo.com/statement"
PAUSE = 4.0  # seconds between downloads: a person does not click this fast, and it is kinder to the site


class VenmoPageError(Exception):
    pass


def month_label(month: str) -> str:
    """'2025-12' -> 'December 2025'"""
    year, number = month.split("-")
    return f"{calendar.month_name[int(number)]} {int(year)}"


def select_month(page, month: str, settle=2.5) -> None:
    label = month_label(month)
    field = page.locator("input[placeholder='MMMM YYYY']")
    if field.count() != 1:
        raise VenmoPageError("the month field is not on the page (Venmo changed it?)")
    field.click()
    field.fill(label)
    page.keyboard.press("Enter")
    page.wait_for_timeout(int(settle * 1000))
    if field.input_value() != label:
        raise VenmoPageError(f"could not select {label}")


def download_month(page, month: str) -> str:
    """The text of the statement CSV for one month."""
    select_month(page, month)
    button = page.get_by_role("button", name="Download CSV")
    if button.count() != 1:
        raise VenmoPageError("the Download CSV button is not on the page")
    with page.expect_download(timeout=60000) as download:
        button.click()
    path = download.value.path()
    with open(path, newline="", encoding="utf-8-sig") as f:
        return f.read()


def fetch_statements(
    page, months: list[str], pause=PAUSE, sleep=time.sleep
) -> list[dict]:
    files = []
    for i, month in enumerate(months):
        if i:
            sleep(pause)
        files.append({"month": month, "csv": download_month(page, month)})
    return files
