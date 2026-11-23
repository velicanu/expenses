"""What each institution's pages look like to the fetcher, and how to tell where a session stands.

`classify` is pure (it gets facts about a page, not the page) so it is unit-tested against what the real pages showed
(see the probe in docs/expense-direct-pulls.md). A site that answers an automated browser with a human check is a
CHALLENGE: the fetcher stops and says so. It never tries to pass one.
"""

from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

LOGGED_IN = "logged_in"
LOGIN_REQUIRED = "login_required"
CHALLENGE = "challenge"
UNKNOWN = "unknown"

# process exit codes, so a shell or cron can tell them apart
EXIT_CODES = {LOGGED_IN: 0, LOGIN_REQUIRED: 10, CHALLENGE: 11, UNKNOWN: 12}


@dataclass(frozen=True)
class PageFacts:
    url: str
    status: int | None
    title: str
    text: str  # the visible text, as much as is needed
    has_password_field: bool = False


@dataclass(frozen=True)
class Institution:
    name: str
    start_url: str  # where a login begins
    home_url: str  # a page that only a logged-in session can open
    classify: Callable[[PageFacts], str]


def human_check(facts: PageFacts) -> bool:
    text = facts.text.lower()
    return (
        ("confirm you" in text and "human" in text)
        or "verify you are human" in text
        or "captcha" in text
        or "are you a human" in text
    )


def classify_venmo(facts: PageFacts) -> str:
    """Venmo (PayPal): an automated browser is met by a 403 'Confirm you're human' slider before any login form."""
    if human_check(facts) or facts.status == 403:
        return CHALLENGE
    host = urlparse(facts.url).netloc
    if (
        host == "id.venmo.com"
        or facts.has_password_field
        or "sign in" in facts.title.lower()
    ):
        return LOGIN_REQUIRED
    if host == "account.venmo.com":
        return LOGGED_IN
    return UNKNOWN


INSTITUTIONS = {
    "venmo": Institution(
        name="venmo",
        start_url="https://account.venmo.com/",
        home_url="https://account.venmo.com/statement",
        classify=classify_venmo,
    ),
}


def find(key: str) -> Institution | None:
    """An account key like venmo-dragos names an institution (the part before the first dash) and its owner."""
    return INSTITUTIONS.get(key.split("-", 1)[0])


def get(key: str) -> Institution:
    inst = find(key)
    if inst is None:
        raise SystemExit(
            f"no sign-in flow for {key!r} yet; known: {', '.join(sorted(INSTITUTIONS))}"
        )
    return inst
