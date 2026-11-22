"""Is the saved session still good? Opens the institution's logged-in page with the saved profile and says what it
finds. Read-only: it only navigates. This is what the nightly job runs first."""

import json
import sys

from playwright.sync_api import sync_playwright

from . import institutions
from .session import facts_from, launch


def check(name: str, profile_root: str, shot: str | None = None) -> dict:
    inst = institutions.get(name)
    with sync_playwright() as p:
        ctx = launch(p, profile_root, name)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            response = page.goto(
                inst.home_url, wait_until="domcontentloaded", timeout=60000
            )
            page.wait_for_timeout(5000)
            facts = facts_from(page, response)
            state = inst.classify(facts)
            if shot:
                page.screenshot(path=shot)
            return {
                "institution": name,
                "state": state,
                "url": facts.url,
                "status": facts.status,
                "title": facts.title,
                "webdriver": page.evaluate("navigator.webdriver"),
            }
        finally:
            ctx.close()


def main(name: str, profile_root: str, shot: str | None) -> int:
    result = check(name, profile_root, shot)
    print(json.dumps(result))
    return institutions.EXIT_CODES[result["state"]]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
