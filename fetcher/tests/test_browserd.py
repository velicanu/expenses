import json
import os
import signal
import stat

import pytest
from fastapi.testclient import TestClient
from fetcher import browserd

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


_next_pid = iter(
    range(2**22 + 1000, 2**23)
)  # above any real pid: a stray os.kill could never hit a real process


class FakeProc:
    def __init__(self, argv, env=None):
        self.argv, self.env = argv, env
        self.pid = next(_next_pid)
        self.returncode = None
        self.signals = []  # group/tree kills
        self.main_signals = []  # signals to just this process (the polite request)

    def poll(self):
        return self.returncode

    def finish(self, rc):
        self.returncode = rc


class World:
    """Fake processes and a fake clock, so a session's whole life can be driven and inspected."""

    def __init__(self, tmp_path):
        self.procs, self.now, self.x_ok, self.vnc_ok = [], 1000.0, True, True
        self.tmp = tmp_path
        self.browser_quits_when_asked = True  # Chrome does; a hung one would not
        self.prepared = []  # (profile, how many processes had been started by then)

    def spawn(self, argv, env=None):
        p = FakeProc(argv, env)
        self.procs.append(p)
        return p

    def kill_group(self, proc, sig):
        proc.signals.append(sig)
        if (
            proc.returncode is None
        ):  # a process that already left cannot be killed again
            proc.returncode = -int(sig)

    def signal_proc(self, proc, sig):
        proc.main_signals.append(sig)
        if self.browser_quits_when_asked:
            proc.returncode = 0

    @property
    def browser(self):
        return self.procs[-1]

    def sessions(self, **kw):
        return browserd.Sessions(
            profiles="/profiles",
            minutes=15,
            spawn=self.spawn,
            kill_group=self.kill_group,
            signal_proc=self.signal_proc,
            prepare_profile=lambda profile: self.prepared.append(
                (str(profile), len(self.procs))
            )
            or True,
            grace=0.3,
            x_ready=lambda: self.x_ok,
            vnc_ready=lambda: self.vnc_ok,
            clock=lambda: self.now,
            workdir=str(self.tmp),
            ready_timeout=0.2,
            **kw,
        )

    def names(self):
        return [p.argv[0] for p in self.procs]


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def test_a_session_starts_the_display_the_vnc_server_and_a_plain_chrome_in_order(world):
    s = world.sessions()
    s.start("venmo-dragos")
    assert world.names() == ["Xvfb", "fluxbox", "x11vnc", "google-chrome-stable"]
    chrome = world.browser
    assert chrome.env["DISPLAY"] == ":99"
    assert "--user-data-dir=/profiles/venmo-dragos" in chrome.argv
    assert chrome.argv[-1] == "https://account.venmo.com/"
    assert "--window-size=540,960" in chrome.argv
    st = s.status()
    assert (
        st["state"] == "running"
        and st["account"] == "venmo-dragos"
        and st["remaining"] == 900
    )
    assert len(st["vnc_password"]) == 8


def test_the_browser_is_started_like_a_person_would_not_like_a_script(world):
    """A bank's bot defense reads these: no Playwright, no debugging pipe or port, no automation switches."""
    world.sessions().start("venmo-dragos")
    argv = " ".join(world.browser.argv)
    for automation in (
        "playwright",
        "--enable-automation",
        "--remote-debugging",
        "--headless",
        "--disable-blink-features",
        "--user-agent",
        "-m fetcher",
    ):
        assert automation not in argv, automation
    assert not any("python" in a for a in world.browser.argv)


def test_the_vnc_password_is_in_a_private_file_and_never_on_a_command_line(world):
    s = world.sessions()
    s.start("venmo-dragos")
    pw = s.status()["vnc_password"]
    vnc = next(p for p in world.procs if p.argv[0] == "x11vnc")
    assert pw not in " ".join(" ".join(p.argv) for p in world.procs)
    pwfile = vnc.argv[vnc.argv.index("-passwdfile") + 1]
    assert open(pwfile).read() == pw
    assert stat.S_IMODE(os.stat(pwfile).st_mode) == 0o600
    assert "-localhost" in vnc.argv and "-nopw" not in vnc.argv
    s.stop()
    assert not os.path.exists(pwfile)


def test_a_fresh_password_each_session(world):
    s = world.sessions()
    seen = set()
    for _ in range(3):
        s.start("venmo-dragos")
        seen.add(s.status()["vnc_password"])
        s.stop()
    assert len(seen) == 3


def test_only_one_session_at_a_time(world):
    s = world.sessions()
    s.start("venmo-dragos")
    count = len(world.procs)
    with pytest.raises(browserd.StartError, match="already running"):
        s.start("venmo-viral")
    assert len(world.procs) == count


def test_an_account_without_a_sign_in_flow_starts_nothing(world):
    s = world.sessions()
    with pytest.raises(browserd.StartError, match="no sign-in flow"):
        s.start("fidelity-dragos")
    assert world.procs == [] and list(world.tmp.iterdir()) == []


@pytest.mark.parametrize("rc", [0, 1])
def test_when_the_browser_is_closed_everything_is_stopped_and_the_result_is_kept(
    world, rc
):
    s = world.sessions()
    s.start("venmo-dragos")
    world.browser.finish(rc)  # the person closed Chrome
    st = s.status()
    assert st == {
        "state": "idle",
        "account": None,
        "remaining": 0,
        "result": "closed",
        "vnc_password": None,
    }
    assert all(
        p.signals for p in world.procs[:3]
    )  # display, window manager and VNC server stopped too
    assert list(world.tmp.iterdir()) == []


def test_a_session_ends_by_itself_at_its_deadline(world):
    s = world.sessions()
    s.start("venmo-dragos")
    world.now += 899
    assert s.status()["state"] == "running" and s.status()["remaining"] == 1
    world.now += 2
    st = s.status()
    assert st["state"] == "idle" and st["result"] == "timed_out"
    assert world.browser.main_signals == [
        signal.SIGTERM
    ]  # asked to quit before anything was torn down
    assert all(signal.SIGTERM in p.signals for p in world.procs[:3])


def test_stop_ends_it_and_a_new_session_can_follow(world):
    s = world.sessions()
    s.start("venmo-dragos")
    s.stop()
    assert s.status()["result"] == "finished" and s.status()["state"] == "idle"
    s.start("venmo-viral")
    assert s.status()["account"] == "venmo-viral" and s.status()["result"] is None
    s.stop()
    s.stop()  # stopping nothing is fine


def test_finishing_asks_chrome_to_quit_and_waits_so_it_can_write_its_cookies(world):
    """Chrome gets a plain SIGTERM to itself first; the rest is only torn down after it has gone."""
    s = world.sessions()
    s.start("venmo-dragos")
    chrome = world.browser
    s.stop()
    assert chrome.main_signals == [signal.SIGTERM]
    assert chrome.returncode == 0  # it left by itself, not by being killed
    assert not any(sig == signal.SIGKILL for sig in chrome.signals)


def test_a_browser_that_ignores_the_request_is_killed_after_the_grace_period(world):
    import time

    world.browser_quits_when_asked = False
    s = world.sessions()
    s.start("venmo-dragos")
    chrome = world.browser
    started = time.monotonic()
    s.stop()
    assert time.monotonic() - started >= 0.3  # it was given the grace period
    assert chrome.main_signals == [signal.SIGTERM] and signal.SIGTERM in chrome.signals
    assert s.status()["state"] == "idle"


@pytest.mark.parametrize("which", ["x_ok", "vnc_ok"])
def test_a_failed_start_cleans_up_and_leaves_it_usable(world, which):
    s = world.sessions()
    setattr(world, which, False)
    with pytest.raises(browserd.StartError):
        s.start("venmo-dragos")
    assert s.status()["state"] == "idle"
    assert all(p.signals for p in world.procs)  # whatever had started was stopped
    assert list(world.tmp.iterdir()) == []
    setattr(world, which, True)
    s.start("venmo-dragos")
    assert s.status()["state"] == "running"


def test_a_missing_binary_is_a_start_error_not_a_crash(world):
    def broken(argv, env=None):
        raise FileNotFoundError("Xvfb")

    s = world.sessions()
    s._spawn = broken
    with pytest.raises(browserd.StartError, match="FileNotFoundError"):
        s.start("venmo-dragos")
    assert list(world.tmp.iterdir()) == []


def test_the_control_api_needs_the_token(world):
    c = TestClient(browserd.create_app(TOKEN, world.sessions()))
    for headers in (
        {},
        {"Authorization": "Bearer nope"},
        {"Authorization": TOKEN},
        {"Authorization": "Bearer "},
    ):
        assert c.get("/status", headers=headers).status_code == 401
        assert (
            c.post(
                "/start", headers=headers, json={"account": "venmo-dragos"}
            ).status_code
            == 401
        )
        assert c.post("/stop", headers=headers).status_code == 401
    assert world.procs == []
    # a server configured with no token accepts nothing, not even "Bearer "
    blank = TestClient(browserd.create_app("", world.sessions()))
    assert blank.get("/status", headers={"Authorization": "Bearer "}).status_code == 401


def test_the_control_api_runs_a_session(world):
    c = TestClient(browserd.create_app(TOKEN, world.sessions()))
    assert c.get("/status", headers=AUTH).json()["state"] == "idle"
    r = c.post("/start", headers=AUTH, json={"account": "venmo-dragos"})
    assert (
        r.status_code == 200
        and r.json()["state"] == "running"
        and len(r.json()["vnc_password"]) == 8
    )
    assert (
        c.post("/start", headers=AUTH, json={"account": "venmo-viral"}).status_code
        == 409
    )
    assert (
        c.post("/start", headers=AUTH, json={"account": "fidelity-dragos"}).status_code
        == 409
    )
    assert c.post("/stop", headers=AUTH).json()["result"] == "finished"
    assert c.get("/status", headers=AUTH).json()["vnc_password"] is None


def test_a_wealthfront_hand_login_opens_its_sign_in_page_in_a_plain_chrome(world):
    s = world.sessions()
    s.start("wealthfront-dragos")
    chrome = world.browser
    assert chrome.argv[-1] == "https://www.wealthfront.com/login"
    assert (
        "--user-data-dir=/profiles/wealthfront-dragos" in chrome.argv
    )  # its own profile
    assert not any(
        flag in " ".join(chrome.argv)
        for flag in ("playwright", "--enable-automation", "--remote-debugging")
    )


# --- the profile is set up so a login survives Chrome closing -----------------------------------------------------------


def test_the_profile_is_prepared_before_chrome_starts(world):
    world.sessions().start("venmo-dragos")
    assert world.prepared == [
        ("/profiles/venmo-dragos", 0)
    ]  # for this account's own profile, with nothing started yet


def test_continue_where_you_left_off_is_set_in_a_new_profile(tmp_path):
    profile = tmp_path / "wealthfront-dragos"
    assert browserd._keep_session_cookies(profile) is True
    prefs = json.loads((profile / "Default" / "Preferences").read_text())
    assert prefs == {"session": {"restore_on_startup": 1}}


def test_it_keeps_every_other_preference_and_does_not_rewrite_what_is_already_right(
    tmp_path,
):
    profile = tmp_path / "p"
    (profile / "Default").mkdir(parents=True)
    path = profile / "Default" / "Preferences"
    path.write_text(
        json.dumps(
            {
                "profile": {"exit_type": "SessionEnded", "name": "x"},
                "session": {"other": 5},
                "homepage": "h",
            }
        )
    )
    assert browserd._keep_session_cookies(profile) is True
    prefs = json.loads(path.read_text())
    assert prefs["session"] == {"other": 5, "restore_on_startup": 1}
    assert (
        prefs["profile"] == {"exit_type": "SessionEnded", "name": "x"}
        and prefs["homepage"] == "h"
    )
    before = (path.stat().st_ino, path.stat().st_mtime_ns)
    assert browserd._keep_session_cookies(profile) is True
    after = (path.stat().st_ino, path.stat().st_mtime_ns)
    assert (
        after == before
    )  # already right: not rewritten (a rewrite is a new file, so a new inode)
    assert not list((profile / "Default").glob("Preferences.tmp"))  # no stray temp file


def test_a_preferences_file_it_cannot_understand_is_left_exactly_as_it_was(tmp_path):
    profile = tmp_path / "p"
    (profile / "Default").mkdir(parents=True)
    path = profile / "Default" / "Preferences"
    for content in ("{not json", "[1, 2]", json.dumps({"session": "oops"})):
        path.write_text(content)
        assert browserd._keep_session_cookies(profile) is False
        assert path.read_text() == content


def test_a_profile_it_cannot_write_is_not_an_error(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("a file where a directory should be")
    assert browserd._keep_session_cookies(blocked / "profile") is False
