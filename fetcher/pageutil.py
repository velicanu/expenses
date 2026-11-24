"""What every site's download code needs: wait for a control the way a person does, and fail loudly when the page is not what
it was when the code was written."""


class PageError(Exception):
    """The page does not look the way the downloader expects (a control missing or a site changed). Never carries page text."""


def wait_visible(locator, what: str, timeout_ms=20000):
    """Wait for a control the way a person would: pages re-render while they load, so one may be briefly absent.
    (The first production run of the Venmo download counted its button once, found none, and gave up.)"""
    try:
        locator.first.wait_for(state="visible", timeout=timeout_ms)
    except Exception as e:
        if (
            type(e).__name__ != "TimeoutError"
        ):  # Playwright's TimeoutError; anything else is a different problem
            raise
        raise PageError(
            f"{what} did not appear within {timeout_ms // 1000} s (found {locator.count()} on the page)"
        ) from None
    return locator.first
