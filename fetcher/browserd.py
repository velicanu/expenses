"""The browser side of the credentials page's hand-login (`python -m fetcher browserd`), in its own container.

It holds the browser profiles (bank session cookies) and runs a login session on request: a small virtual display,
a window manager, a VNC server on 127.0.0.1, and a plain Google Chrome on the sign-in page in the account's profile.
Plain means what it says: started like a person would start it, with no Playwright, no debugging pipe, none of the
automation switches (`navigator.webdriver`, the "controlled by automated software" banner) that a bank's bot defense
reads. The person drives it through the page exactly as they would a Chrome on a remote desktop; nothing here types or
clicks. It has no bao credentials and no web-facing port; the credentials page, which
has the opposite (bao but no browser), asks it to start and stop sessions over 127.0.0.1 with a shared token and
bridges the VNC stream to the person's browser. So a hostile page that exploits the browser finds no vault login to read.

One session at a time, over by itself after a deadline. VNC gets a fresh random password per session (the protocol
keeps only 8 characters), because the container shares the host's network: any local process could otherwise connect.

Every way a session ends closes Chrome gracefully first (SIGTERM to the browser, then a wait), so it writes its cookies
and the next start does not open on "Chromium didn't shut down correctly". Whether the login worked is not known here
(that would take automation); the session's result says how it ended, and a separate check says if the session holds.
"""

import hmac
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from . import institutions

DISPLAY = ":99"
VNC_PORT = 5900
SCREEN = "540x960x24"  # phone-shaped, so the page scales it to a phone without shrinking the text
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def _spawn(argv, env=None):
    # its own process group, so a whole browser (and its children) can be stopped together
    return subprocess.Popen(
        argv,
        env=env,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _kill_group(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _wait_for(check, seconds: float) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.1)
    return False


def _x_ready() -> bool:
    return Path(f"/tmp/.X11-unix/X{DISPLAY[1:]}").exists()


def _vnc_ready() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", VNC_PORT)) == 0


def _signal(proc, sig):
    """Signal just this process (not its group): Chrome shuts its own children down when it is asked nicely."""
    try:
        os.kill(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _browser_argv(account: str, profiles: str) -> list[str]:
    """Google Chrome the way a person starts it, on the institution's sign-in page, in the account's own profile.
    --no-sandbox is needed because the container cannot create user namespaces (Chrome shows a bar saying so)."""
    width, height = SCREEN.split("x")[:2]
    return [
        "google-chrome-stable",
        f"--user-data-dir={Path(profiles) / account}",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--password-store=basic",
        "--window-position=0,0",
        f"--window-size={width},{height}",
        institutions.get(account).start_url,
    ]


class StartError(Exception):
    pass


MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_MONTHS = 24
FETCH_SECONDS = 420  # a first pull downloads a year of months, a few seconds apart


def _run_fetch(
    account: str, months: list[str], profiles: str, timeout=FETCH_SECONDS
) -> dict:
    """`python -m fetcher fetch ...` under its own virtual display; its one JSON line is the result. Whatever goes
    wrong is reduced to a message with no page text."""
    argv = [
        "xvfb-run",
        "-a",
        sys.executable,
        "-m",
        "fetcher",
        "fetch",
        account,
        *months,
    ]
    try:
        proc = subprocess.Popen(
            argv,
            env={**os.environ, "FETCHER_PROFILES": profiles},
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError as e:
        return {
            "state": "error",
            "message": f"could not start the browser ({type(e).__name__})",
            "files": [],
        }
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc, signal.SIGKILL)
        proc.communicate()
        return {"state": "error", "message": "the fetch took too long", "files": []}
    lines = [line for line in out.splitlines() if line.startswith("{")]
    try:
        return json.loads(lines[-1])
    except (IndexError, ValueError):
        return {"state": "error", "message": "the fetch gave no result", "files": []}


class Sessions:
    """The one hand-login session. Everything outside the OS (processes, clock, readiness) is injectable for tests."""

    def __init__(
        self,
        profiles: str = "/profiles",
        minutes: int = 15,
        spawn=_spawn,
        kill_group=_kill_group,
        x_ready=_x_ready,
        vnc_ready=_vnc_ready,
        signal_proc=_signal,
        browser_argv=_browser_argv,
        clock=time.time,
        workdir: str = "/tmp",
        ready_timeout: float = 10,
        grace: float = 15,
        fetch_runner=_run_fetch,
    ):
        self.profiles, self.minutes = profiles, minutes
        self._spawn, self._kill_group = spawn, kill_group
        self._x_ready, self._vnc_ready = x_ready, vnc_ready
        self._signal, self._browser_argv, self._clock = signal_proc, browser_argv, clock
        self._workdir, self._ready_timeout, self._grace = workdir, ready_timeout, grace
        self._lock = threading.RLock()
        self._procs: list = []
        self._fetch_runner = fetch_runner
        self._fetching = False
        self._browser = None
        self._account: str | None = None
        self._password: str | None = None
        self._deadline = 0.0
        self._result: str | None = None
        self._pwfile: Path | None = None

    # -- public -----------------------------------------------------------------------------------------------
    def start(self, account: str) -> None:
        if institutions.find(account) is None:
            raise StartError(f"there is no sign-in flow for {account!r} yet")
        with self._lock:
            self._reap()
            if self._fetching:
                raise StartError("a fetch is running; try again in a minute")
            if self._account is not None:
                raise StartError("a login session is already running")
            password = "".join(secrets.choice(_ALPHABET) for _ in range(8))
            pwfile = Path(self._workdir) / f"vnc-{secrets.token_hex(4)}.pw"
            pwfile.write_text(password)
            pwfile.chmod(0o600)
            self._pwfile = pwfile
            env = {**os.environ, "DISPLAY": DISPLAY}
            try:
                self._procs.append(
                    self._spawn(
                        ["Xvfb", DISPLAY, "-screen", "0", SCREEN, "-nolisten", "tcp"],
                        env,
                    )
                )
                if not _wait_for(self._x_ready, self._ready_timeout):
                    raise StartError("the virtual display did not start")
                self._procs.append(self._spawn(["fluxbox"], env))
                self._procs.append(
                    self._spawn(
                        [
                            "x11vnc",
                            "-display",
                            DISPLAY,
                            "-localhost",
                            "-forever",
                            "-shared",
                            "-quiet",
                            "-rfbport",
                            str(VNC_PORT),
                            "-passwdfile",
                            str(pwfile),
                        ],
                        env,
                    )
                )
                if not _wait_for(self._vnc_ready, self._ready_timeout):
                    raise StartError("the VNC server did not start")
                self._browser = self._spawn(
                    self._browser_argv(account, self.profiles), env
                )
                self._procs.append(self._browser)
            except StartError:
                self._teardown()
                raise
            except OSError as e:
                self._teardown()
                raise StartError(
                    f"could not start the browser ({type(e).__name__})"
                ) from None
            self._account, self._password = account, password
            self._deadline = self._clock() + self.minutes * 60
            self._result = None

    def fetch(self, account: str, months: list[str]) -> dict:
        """Download statements on the account's saved login (the Refresh data button). One at a time, and never while a
        hand login is open: both use the account's browser profile."""
        if institutions.find(account) is None:
            raise StartError(f"there is no sign-in flow for {account!r} yet")
        if (
            not months
            or len(months) > MAX_MONTHS
            or not all(MONTH.match(m) for m in months)
        ):
            raise StartError("months must be YYYY-MM, at most 24")
        with self._lock:
            self._reap()
            if self._account is not None:
                raise StartError("a login session is open; finish it first")
            if self._fetching:
                raise StartError("a fetch is already running")
            self._fetching = True
        try:
            return self._fetch_runner(account, months, self.profiles)
        finally:
            with self._lock:
                self._fetching = False

    def stop(self, reason: str = "finished") -> None:
        """The person is done (or gave up): close Chrome gracefully so it keeps its cookies, then everything else."""
        with self._lock:
            if self._account is not None:
                self._close_browser()
                self._finish(reason)

    def status(self) -> dict:
        with self._lock:
            self._reap()
            running = self._account is not None
            return {
                "state": "running" if running else "idle",
                "account": self._account,
                "remaining": max(0, int(self._deadline - self._clock()))
                if running
                else 0,
                "result": self._result,
                "vnc_password": self._password if running else None,
            }

    # -- internals --------------------------------------------------------------------------------------------
    def _close_browser(self) -> None:
        """Ask Chrome to quit and give it time to write its profile; the teardown after this is the backstop."""
        browser = self._browser
        if browser is None or browser.poll() is not None:
            return
        self._signal(browser, signal.SIGTERM)
        end = time.monotonic() + self._grace
        while browser.poll() is None and time.monotonic() < end:
            time.sleep(0.05)

    def _reap(self) -> None:
        """Notice that the browser was closed or the time is up."""
        if self._account is None:
            return
        if self._browser is not None and self._browser.poll() is not None:
            self._finish("closed")
        elif self._clock() >= self._deadline:
            self._close_browser()
            self._finish("timed_out")

    def _finish(self, result: str) -> None:
        self._teardown()
        self._account, self._password, self._result = None, None, result

    def _teardown(self) -> None:
        for proc in reversed(self._procs):
            self._kill_group(proc, signal.SIGTERM)
        end = time.monotonic() + 3
        for proc in self._procs:
            while proc.poll() is None and time.monotonic() < end:
                time.sleep(0.05)
            if proc.poll() is None:
                self._kill_group(proc, signal.SIGKILL)
        self._procs, self._browser = [], None
        if self._pwfile is not None:
            self._pwfile.unlink(missing_ok=True)
            self._pwfile = None


class StartIn(BaseModel):
    account: str


class FetchIn(BaseModel):
    account: str
    months: list[str] = Field(max_length=MAX_MONTHS)


def create_app(token: str, sessions: Sessions) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def authorized(request: Request) -> None:
        sent = request.headers.get("authorization", "")
        if not token or not hmac.compare_digest(sent, f"Bearer {token}"):
            raise HTTPException(401, "not authorized")

    @app.get("/status", dependencies=[Depends(authorized)])
    def status():
        return sessions.status()

    @app.post("/start", dependencies=[Depends(authorized)])
    def start(body: StartIn):
        try:
            sessions.start(body.account)
        except StartError as e:
            raise HTTPException(409, str(e)) from None
        return sessions.status()

    @app.post("/fetch", dependencies=[Depends(authorized)])
    def fetch(body: FetchIn):
        try:
            return sessions.fetch(body.account, body.months)
        except StartError as e:
            raise HTTPException(409, str(e)) from None

    @app.post("/stop", dependencies=[Depends(authorized)])
    def stop():
        sessions.stop()
        return sessions.status()

    return app


def serve() -> None:
    import uvicorn

    token = os.environ.get("BROWSERD_TOKEN", "")
    if len(token) < 24:
        raise SystemExit("set BROWSERD_TOKEN (at least 24 characters)")
    sessions = Sessions(os.environ.get("FETCHER_PROFILES", "/profiles"))

    def watch():  # ends a session whose time ran out even if nobody asks for its status
        while True:
            time.sleep(2)
            sessions.status()

    threading.Thread(target=watch, daemon=True).start()
    uvicorn.run(
        create_app(token, sessions),
        host=os.environ.get("LISTEN_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8097")),  # not 8096: jellyfin has that on tess
        proxy_headers=False,
        access_log=False,
    )
