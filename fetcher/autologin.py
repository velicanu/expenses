"""Log in the way a person does: a plain Chrome on the sign-in page, Chrome's own saved login, a few keystrokes.

The password never passes through this code. Chrome already holds the login (the person saved it during a hand login: one
saved login in each profile) and offers it on the sign-in page; the steps only accept that offer and submit the form, by
sending keys to the screen with xdotool, exactly what the hand-login page's Paste button does. There is no Playwright and no
debugging port in this browser, so the page sees an ordinary Chrome.

What it deliberately does not do: read the page, find a button, solve or get past a check, or retry. It sends its fixed keys
once and closes Chrome properly (so the session is kept). Whether it got in is decided afterwards by the normal login check
(fetch.py); if a captcha, a code prompt or an error page was in the way, that check says the login is still needed and a
person takes over.

A site's steps are data (Institution.autologin): ("wait", seconds), ("key", "Return"), or ("totp", "wealthfront"). The last types
the current one-time code from the person's dedicated KeePass file (the entry with that title), for a site that asks for an
authenticator code after the password: the code is made at the moment it is typed and is never logged or returned. The steps
were worked out by looking at that site's sign-in page once.
"""

import os
import re
import signal
import subprocess
import time
from pathlib import Path

GRACE = 15  # seconds Chrome is given to exit after SIGTERM, so it writes its cookies


class AutoLoginError(Exception):
    """The keys could not be sent (no xdotool, no display). Never carries page text."""


_ENTRY = re.compile(r"^[a-z0-9-]{1,40}$")


def valid_steps(steps) -> bool:
    return bool(steps) and all(
        len(s) == 2
        and (
            (s[0] == "wait" and isinstance(s[1], (int, float)) and 0 <= s[1] <= 60)
            or (s[0] == "key" and isinstance(s[1], str) and s[1].isalnum())
            or (s[0] == "totp" and isinstance(s[1], str) and _ENTRY.match(s[1]))
        )
        for s in steps
    )


def _spawn(argv, env):
    return subprocess.Popen(
        argv,
        env=env,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _close(proc, sleep=time.sleep, grace=GRACE) -> None:
    """Ask the process to quit and give it time; kill its group only if it ignores that."""
    if proc is None or proc.poll() is not None:
        return
    try:
        os.kill(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    waited = 0.0
    while proc.poll() is None and waited < grace:
        sleep(0.25)
        waited += 0.25
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def run(
    account: str,
    profiles: str,
    steps,
    spawn=_spawn,
    send_key=None,
    sleep=time.sleep,
    close=_close,
    send_text=None,
    get_code=None,
) -> None:
    """One attempt: start Chrome on the sign-in page, send the steps, close Chrome properly."""
    from .browserd import _browser_argv, _keep_session_cookies

    if not valid_steps(steps):
        raise AutoLoginError("this site has no valid login steps")
    _keep_session_cookies(Path(profiles) / account)
    env = {**os.environ, "HOME": os.environ.get("HOME", "/tmp")}
    send = send_key or _send_key
    type_text = send_text or _send_text
    code_for = get_code or _keepass_code
    window_manager = chrome = None
    try:
        try:
            window_manager = spawn(
                ["fluxbox"], env
            )  # keyboard focus needs one; Chrome works without, less reliably
        except OSError:
            window_manager = None
        chrome = spawn(_browser_argv(account, profiles), env)
        for kind, arg in steps:
            if kind == "wait":
                sleep(arg)
            elif kind == "key":
                send(arg)
            else:  # "totp": made now, typed now, never kept
                code = code_for(arg)
                if not (code.isdigit() and 6 <= len(code) <= 8):
                    raise AutoLoginError("the one-time code was not a number")
                type_text(code)
    finally:
        close(chrome)
        close(window_manager)


def _send_key(name: str) -> None:
    try:
        subprocess.run(
            ["xdotool", "key", name], check=True, timeout=10, capture_output=True
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise AutoLoginError(f"could not send keys ({type(e).__name__})") from None


def _send_text(text: str) -> None:
    try:
        subprocess.run(
            ["xdotool", "type", "--delay", "90", "--", text],
            check=True,
            timeout=15,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise AutoLoginError(f"could not send keys ({type(e).__name__})") from None


def _keepass_code(entry: str) -> str:
    """The current one-time code of the entry titled `entry` in the dedicated KeePass file (KEEPASS_FILE, default
    /keepass/twofas.kdbx; password in KEEPASS_PASSWORD). Errors name the problem, never a value."""
    try:
        import pyotp
        from pykeepass import PyKeePass

        db = PyKeePass(
            os.environ.get("KEEPASS_FILE", "/keepass/twofas.kdbx"),
            password=os.environ["KEEPASS_PASSWORD"],
        )
        found = next(
            (e for e in db.entries if (e.title or "").strip().lower() == entry), None
        )
        if found is None or not found.otp:
            raise AutoLoginError(f"no one-time-code entry named {entry!r}")
        return pyotp.parse_uri(found.otp).now()
    except AutoLoginError:
        raise
    except KeyError:
        raise AutoLoginError("KEEPASS_PASSWORD is not set") from None
    except (
        Exception
    ) as e:  # wrong password, missing file, bad otp setting: the type only
        raise AutoLoginError(
            f"could not make the one-time code ({type(e).__name__})"
        ) from None
