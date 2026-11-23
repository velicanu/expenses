import os
import signal
import stat

import pytest
from fastapi.testclient import TestClient
from fetcher import browserd

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeProc:
    def __init__(self, argv, env=None):
        self.argv, self.env = argv, env
        self.pid = id(self) % 100000
        self.returncode = None
        self.signals = []

    def poll(self):
        return self.returncode

    def finish(self, rc):
        self.returncode = rc


class World:
    """Fake processes and a fake clock, so a session's whole life can be driven and inspected."""

    def __init__(self, tmp_path):
        self.procs, self.now, self.x_ok, self.vnc_ok = [], 1000.0, True, True
        self.tmp = tmp_path

    def spawn(self, argv, env=None):
        p = FakeProc(argv, env)
        self.procs.append(p)
        return p

    def kill_group(self, proc, sig):
        proc.signals.append(sig)
        proc.returncode = -int(sig)

    def sessions(self, **kw):
        return browserd.Sessions(
            profiles="/profiles",
            minutes=15,
            spawn=self.spawn,
            kill_group=self.kill_group,
            x_ready=lambda: self.x_ok,
            vnc_ready=lambda: self.vnc_ok,
            clock=lambda: self.now,
            workdir=str(self.tmp),
            ready_timeout=0.2,
            **kw,
        )

    def names(self):
        return [
            p.argv[0] if p.argv[0] != browserd.sys.executable else "login"
            for p in self.procs
        ]


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def test_a_session_starts_the_display_the_vnc_server_and_the_login_in_order(world):
    s = world.sessions()
    s.start("venmo-dragos")
    assert world.names() == ["Xvfb", "fluxbox", "x11vnc", "login"]
    login = world.procs[-1]
    assert login.argv[1:] == ["-m", "fetcher", "login", "venmo-dragos", "15"]
    assert login.env["DISPLAY"] == ":99" and login.env["FETCHER_SCREEN"] == "540x960"
    st = s.status()
    assert (
        st["state"] == "running"
        and st["account"] == "venmo-dragos"
        and st["remaining"] == 900
    )
    assert len(st["vnc_password"]) == 8


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


@pytest.mark.parametrize("rc,result", [(0, "logged_in"), (1, "ended")])
def test_when_the_login_ends_everything_is_stopped_and_the_result_is_kept(
    world, rc, result
):
    s = world.sessions()
    s.start("venmo-dragos")
    world.procs[-1].finish(rc)
    st = s.status()
    assert st == {
        "state": "idle",
        "account": None,
        "remaining": 0,
        "result": result,
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
    assert all(signal.SIGTERM in p.signals for p in world.procs)


def test_stop_ends_it_and_a_new_session_can_follow(world):
    s = world.sessions()
    s.start("venmo-dragos")
    s.stop()
    assert s.status()["result"] == "stopped" and s.status()["state"] == "idle"
    s.start("venmo-viral")
    assert s.status()["account"] == "venmo-viral" and s.status()["result"] is None
    s.stop()
    s.stop()  # stopping nothing is fine


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
    assert c.post("/stop", headers=AUTH).json()["result"] == "stopped"
    assert c.get("/status", headers=AUTH).json()["vnc_password"] is None
