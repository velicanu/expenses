"""The one-time login by hand. Runs inside the remote-login container (a virtual display seen through noVNC, reached
over an SSH tunnel): opens the institution's sign-in page in the persistent profile and waits while a person logs in,
solves any human check, and does the 2FA. When the session looks logged in it keeps the window open briefly so the
cookies are flushed to the profile, then closes. Nothing here types a password or clicks anything."""

import sys
import time

from playwright.sync_api import sync_playwright

from . import institutions
from .session import facts_from, launch


def login(name: str, profile_root: str, minutes: int = 30) -> int:
    inst = institutions.get(name)
    deadline = time.time() + minutes * 60
    with sync_playwright() as p:
        ctx = launch(p, profile_root, name)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        closed = []
        ctx.on("close", lambda *_: closed.append(True))
        page.goto(inst.start_url, wait_until="domcontentloaded", timeout=60000)
        print(
            f"{name}: sign in in the window (human check, password, 2FA). Waiting up to {minutes} minutes.",
            flush=True,
        )
        good_polls = 0
        while time.time() < deadline and not closed:
            page.wait_for_timeout(4000)
            try:
                state = inst.classify(facts_from(page))
            except Exception:  # the page is navigating
                continue
            good_polls = good_polls + 1 if state == institutions.LOGGED_IN else 0
            if good_polls >= 3:
                print(f"{name}: looks logged in; saving the session.", flush=True)
                page.wait_for_timeout(15000)  # let the browser write its cookies
                ctx.close()
                return 0
        if not closed:
            ctx.close()
        print(
            f"{name}: not logged in when the window closed or the time ran out.",
            flush=True,
        )
        return 1


if __name__ == "__main__":
    sys.exit(
        login(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 30)
    )
