"""One persistent browser profile per institution: cookies and 'remembered device' survive between runs. The profile
lives on tess outside the Syncthing folder (it holds session cookies) and is never copied anywhere else."""

from pathlib import Path

from .institutions import PageFacts


def launch(
    playwright,
    profile_root,
    name: str,
    headless: bool = False,
    screen: tuple[int, int] | None = None,
):
    """A real, headed Chromium with a persistent profile (run it under a virtual display on the server). Plain
    Playwright defaults: no stealth patches, no spoofing. `name` is the account key (venmo-dragos): one profile each.
    `screen` fills a small virtual display (the phone-sized one for a hand login) instead of the 1280x900 default."""
    profile = Path(profile_root) / name
    profile.mkdir(parents=True, exist_ok=True)
    extra = {}
    if screen:
        w, h = screen
        extra = {
            "viewport": {"width": w, "height": h},
            "args": ["--window-position=0,0", f"--window-size={w},{h}"],
        }
    return playwright.chromium.launch_persistent_context(
        str(profile),
        headless=headless,
        **({"viewport": {"width": 1280, "height": 900}} | extra),
        locale="en-US",
        timezone_id="America/New_York",
    )


def facts_from(page, response=None) -> PageFacts:
    return PageFacts(
        url=page.url,
        status=response.status if response is not None else None,
        title=page.title(),
        text=page.inner_text("body")[:4000],
        has_password_field=bool(page.query_selector("input[type=password]")),
    )
