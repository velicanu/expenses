"""Does a headed Chromium (virtual display, tess's home IP) get a normal sign-in page, or a bot challenge?
No login, no credentials: navigation only. Prints what it found and saves a screenshot."""

import sys
import time

from playwright.sync_api import sync_playwright

BLOCK_WORDS = ["captcha", "verify you are human", "access denied", "unusual activity", "blocked", "robot", "are you a human", "challenge"]


def probe(url: str, shot: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US", timezone_id="America/New_York")
        page = ctx.new_page()
        started = time.time()
        resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        text = page.inner_text("body")[:4000].lower()
        out = {
            "requested": url,
            "final_url": page.url,
            "status": resp.status if resp else None,
            "title": page.title(),
            "seconds": round(time.time() - started, 1),
            "webdriver": page.evaluate("navigator.webdriver"),
            "block_words": [w for w in BLOCK_WORDS if w in text],
            "inputs": page.evaluate("[...document.querySelectorAll('input')].map(i => (i.type + ':' + (i.name || i.id || i.placeholder || '')).slice(0, 40))"),
            "buttons": [b.strip()[:30] for b in page.evaluate("[...document.querySelectorAll('button')].map(b => b.innerText)") if b.strip()][:8],
        }
        page.screenshot(path=shot)
        browser.close()
        return out


if __name__ == "__main__":
    for k, v in probe(sys.argv[1], sys.argv[2]).items():
        print(f"{k:12} {v}")
