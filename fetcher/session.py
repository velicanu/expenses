"""One persistent browser profile per institution: cookies and 'remembered device' survive between runs. The profile
lives on tess outside the Syncthing folder (it holds session cookies) and is never copied anywhere else."""

from pathlib import Path

from .institutions import PageFacts


def launch(playwright, profile_root, name: str, headless: bool = False):
    """A real, headed Chromium with a persistent profile (run it under a virtual display on the server). Plain
    Playwright defaults: no stealth patches, no spoofing."""
    profile = Path(profile_root) / name
    profile.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        str(profile),
        headless=headless,
        viewport={"width": 1280, "height": 900},
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
