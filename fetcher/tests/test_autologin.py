import signal
import subprocess
import time

import pytest
from fetcher import autologin as al
from fetcher import fetch as fetch_mod
from fetcher import institutions as inst
from test_fetch import _FakeChromePage, _with_fake_playwright

WEALTHFRONT = inst.get("wealthfront-dragos").autologin


# --- the steps are data, and only simple data is accepted ----------------------------------------------------------------


def test_wealthfronts_steps_are_valid_and_mean_what_was_worked_out_by_hand():
    assert al.valid_steps(WEALTHFRONT)
    keys = [arg for kind, arg in WEALTHFRONT if kind == "key"]
    assert keys == ["Down", "Return", "Return"]  # accept the saved login, then submit
    assert WEALTHFRONT[0] == (
        "wait",
        10,
    )  # the page loads and offers the saved login first


@pytest.mark.parametrize(
    "steps",
    [
        (),
        None,
        (("wait", -1),),
        (("wait", 61),),
        (
            ("key", "Return; rm -rf /"),
        ),  # nothing that is not a plain key name is ever passed to xdotool
        (("key", "a b"),),
        (("key", ""),),
        (
            ("type", "hunter2"),
        ),  # the password is never typed by this code: Chrome fills it
        (("click", 5),),
        (("wait",),),
        (("key", "Return", "extra"),),
    ],
)
def test_anything_but_waits_and_plain_key_names_is_refused(steps):
    assert not al.valid_steps(steps)


# --- one attempt with fakes ----------------------------------------------------------------------------------------------


class FakeProc:
    def __init__(self, argv):
        self.argv, self.pid, self.rc = argv, 99999, None

    def poll(self):
        return self.rc


class Rig:
    def __init__(self, fail_on_key=None):
        self.log, self.procs, self.fail_on_key = [], [], fail_on_key

    def spawn(self, argv, env):
        p = FakeProc(argv)
        self.procs.append(p)
        self.log.append(("spawn", argv[0]))
        return p

    def key(self, name):
        if name == self.fail_on_key:
            raise al.AutoLoginError("could not send keys (CalledProcessError)")
        self.log.append(("key", name))

    def sleep(self, seconds):
        self.log.append(("wait", seconds))

    def close(self, proc):
        self.log.append(("close", proc.argv[0] if proc else None))


def run(rig, tmp_path, steps=WEALTHFRONT):
    al.run(
        "wealthfront-dragos",
        str(tmp_path),
        steps,
        spawn=rig.spawn,
        send_key=rig.key,
        sleep=rig.sleep,
        close=rig.close,
    )


def test_one_attempt_starts_a_plain_chrome_sends_the_steps_in_order_and_closes_chrome_first(
    tmp_path,
):
    rig = Rig()
    run(rig, tmp_path)
    assert [e for e in rig.log if e[0] in ("spawn", "key", "wait")] == [
        ("spawn", "fluxbox"),
        ("spawn", "google-chrome-stable"),
        ("wait", 10),
        ("key", "Down"),
        ("wait", 1),
        ("key", "Return"),
        ("wait", 2),
        ("key", "Return"),
        ("wait", 14),
    ]
    closes = [e for e in rig.log if e[0] == "close"]
    assert closes == [
        ("close", "google-chrome-stable"),
        ("close", "fluxbox"),
    ]  # Chrome saves its session before the rest goes


def test_the_browser_is_the_plain_one_in_the_accounts_own_profile(tmp_path):
    rig = Rig()
    run(rig, tmp_path)
    chrome = next(p for p in rig.procs if p.argv[0] == "google-chrome-stable")
    assert f"--user-data-dir={tmp_path}/wealthfront-dragos" in chrome.argv
    assert chrome.argv[-1] == "https://www.wealthfront.com/login"
    joined = " ".join(chrome.argv)
    for automation in (
        "playwright",
        "--enable-automation",
        "--remote-debugging",
        "--headless",
    ):
        assert automation not in joined
    # and the profile keeps session cookies, or the login would be gone when Chrome closes
    import json

    prefs = json.loads(
        (tmp_path / "wealthfront-dragos" / "Default" / "Preferences").read_text()
    )
    assert prefs["session"]["restore_on_startup"] == 1


def test_chrome_is_closed_even_when_a_key_cannot_be_sent(tmp_path):
    rig = Rig(fail_on_key="Return")
    with pytest.raises(al.AutoLoginError, match="could not send keys"):
        run(rig, tmp_path)
    assert ("close", "google-chrome-stable") in rig.log and (
        "close",
        "fluxbox",
    ) in rig.log
    assert [e for e in rig.log if e[0] == "key"] == [
        ("key", "Down")
    ]  # it stopped at the first failure: no more keys


def test_invalid_steps_start_nothing(tmp_path):
    rig = Rig()
    with pytest.raises(al.AutoLoginError, match="no valid login steps"):
        run(rig, tmp_path, steps=(("type", "x"),))
    assert rig.log == []


def test_a_missing_xdotool_is_a_clean_error_without_details(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(al.AutoLoginError) as e:
        al._send_key("Return")
    assert str(e.value) == "could not send keys (FileNotFoundError)"


# --- closing Chrome properly: real processes ------------------------------------------------------------------------------


def test_close_lets_a_process_that_quits_when_asked_go_without_killing_it():
    proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
    al._close(proc, grace=5)
    assert proc.poll() == -signal.SIGTERM  # it left on SIGTERM, not SIGKILL


def test_close_escalates_only_for_a_process_that_ignores_the_request():
    proc = subprocess.Popen(
        ["sh", "-c", "trap '' TERM; while true; do sleep 1; done"],
        start_new_session=True,
    )
    time.sleep(0.5)
    t0 = time.monotonic()
    al._close(proc, grace=1)
    assert (
        proc.wait(timeout=5) == -signal.SIGKILL
    )  # it ignored SIGTERM, so it was killed...
    assert time.monotonic() - t0 >= 1  # ...but only after it was given the grace period


def test_close_ignores_a_process_that_is_already_gone():
    proc = subprocess.Popen(["true"])
    proc.wait()
    al._close(proc)
    al._close(None)


# --- the fetch flow: look, try once if the login lapsed, look again ---------------------------------------------------


def _login_page():
    return _FakeChromePage(
        "https://www.wealthfront.com/login?redirect=%2Fdashboard",
        200,
        text="Log in",
        title="Login - Wealthfront",
        password_field=True,
    )


def _dashboard():
    return _FakeChromePage(
        "https://www.wealthfront.com/dashboard",
        200,
        text="Your accounts",
        title="My Overview - Wealthfront",
    )


@pytest.fixture
def downloader(monkeypatch):
    """Wealthfront gets a (fake) downloader so the flow can run to the end."""
    import dataclasses

    swapped = dataclasses.replace(
        inst.INSTITUTIONS["wealthfront"],
        download=lambda page, months: [{"month": m, "csv": "c"} for m in months],
    )
    monkeypatch.setitem(inst.INSTITUTIONS, "wealthfront", swapped)


@pytest.fixture
def attempts(monkeypatch):
    calls = []
    monkeypatch.setattr(
        al, "run", lambda account, profiles, steps: calls.append((account, steps))
    )
    return calls


def test_a_lapsed_login_is_retried_once_with_the_saved_login_then_the_fetch_goes_on(
    monkeypatch, tmp_path, downloader, attempts
):
    ctx = _with_fake_playwright(monkeypatch, _login_page(), _dashboard())
    out = fetch_mod.fetch(
        "wealthfront-dragos", ["2026-11"], profiles=str(tmp_path), allow_autologin=True
    )
    assert out == {
        "state": "logged_in",
        "files": [{"month": "2026-11", "csv": "c"}],
        "auto_login": "ok",
    }
    assert attempts == [("wealthfront-dragos", WEALTHFRONT)]  # exactly one attempt
    assert all(c.closed for c in ctx.all) and len(ctx.all) == 2


def test_the_first_browser_is_closed_before_the_attempt_because_they_share_a_profile(
    monkeypatch, tmp_path, downloader
):
    ctx = _with_fake_playwright(monkeypatch, _login_page(), _dashboard())
    seen = []
    monkeypatch.setattr(al, "run", lambda *a: seen.append(ctx.all[0].closed))
    fetch_mod.fetch(
        "wealthfront-dragos", ["2026-11"], profiles=str(tmp_path), allow_autologin=True
    )
    assert seen == [True]


def test_a_login_that_is_not_allowed_to_retry_is_not_retried(
    monkeypatch, tmp_path, downloader, attempts
):
    _with_fake_playwright(monkeypatch, _login_page())
    out = fetch_mod.fetch(
        "wealthfront-dragos", ["2026-11"], profiles=str(tmp_path)
    )  # allow_autologin defaults to False
    assert (
        attempts == []
        and out["state"] == "login_required"
        and out["auto_login"] == "not attempted"
    )


def test_a_logged_in_session_needs_no_attempt(
    monkeypatch, tmp_path, downloader, attempts
):
    _with_fake_playwright(monkeypatch, _dashboard())
    out = fetch_mod.fetch(
        "wealthfront-dragos", ["2026-11"], profiles=str(tmp_path), allow_autologin=True
    )
    assert (
        attempts == []
        and out["state"] == "logged_in"
        and out["auto_login"] == "not attempted"
    )


def test_an_attempt_that_did_not_get_in_is_reported_and_never_repeated(
    monkeypatch, tmp_path, downloader, attempts
):
    challenge = _FakeChromePage(
        "https://www.wealthfront.com/login",
        200,
        text="Please solve this captcha",
        title="Login - Wealthfront",
        password_field=True,
    )
    ctx = _with_fake_playwright(monkeypatch, _login_page(), challenge)
    out = fetch_mod.fetch(
        "wealthfront-dragos", ["2026-11"], profiles=str(tmp_path), allow_autologin=True
    )
    assert (
        out["state"] == "challenge"
        and out["auto_login"] == "failed"
        and out["files"] == []
    )
    assert out["detail"] == "HTTP 200 at www.wealthfront.com/login"
    assert len(attempts) == 1 and all(c.closed for c in ctx.all)


def test_keys_that_could_not_be_sent_are_reported_not_hidden(
    monkeypatch, tmp_path, downloader
):
    def broken(account, profiles, steps):
        raise al.AutoLoginError("could not send keys (FileNotFoundError)")

    monkeypatch.setattr(al, "run", broken)
    ctx = _with_fake_playwright(monkeypatch, _login_page())
    out = fetch_mod.fetch(
        "wealthfront-dragos", ["2026-11"], profiles=str(tmp_path), allow_autologin=True
    )
    assert (
        out["auto_login"] == "failed"
        and out["auto_login_error"] == "could not send keys (FileNotFoundError)"
    )
    assert out["state"] == "login_required" and all(c.closed for c in ctx.all)


def test_a_site_without_login_steps_says_unsupported_and_tries_nothing(
    monkeypatch, tmp_path, attempts
):
    login = _FakeChromePage(
        "https://id.venmo.com/signin",
        200,
        text="Sign in",
        title="Log in | Venmo",
        password_field=True,
    )
    _with_fake_playwright(monkeypatch, login)
    assert inst.get("venmo-dragos").autologin is None
    out = fetch_mod.fetch(
        "venmo-dragos", ["2026-11"], profiles=str(tmp_path), allow_autologin=True
    )
    assert (
        attempts == []
        and out["auto_login"] == "unsupported"
        and out["state"] == "login_required"
    )


def test_main_reads_the_permission_from_the_environment(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(
        fetch_mod,
        "fetch",
        lambda account, months, **kw: seen.append(kw)
        or {"state": "logged_in", "files": []},
    )
    monkeypatch.setenv("FETCHER_AUTOLOGIN", "1")
    fetch_mod.main("wealthfront-dragos", ["2026-11"])
    monkeypatch.setenv("FETCHER_AUTOLOGIN", "0")
    fetch_mod.main("wealthfront-dragos", ["2026-11"])
    monkeypatch.delenv("FETCHER_AUTOLOGIN")
    fetch_mod.main("wealthfront-dragos", ["2026-11"])
    assert seen == [
        {"allow_autologin": True},
        {"allow_autologin": False},
        {"allow_autologin": False},
    ]


# --- the one-time code step ------------------------------------------------------------------------------------------------

SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"  # 160 bits: a seed as a site issues it
MASTER = "correct-horse-battery-staple-7731"


def test_a_totp_step_is_valid_only_for_a_plain_entry_title():
    assert al.valid_steps((("wait", 1), ("totp", "wealthfront"), ("key", "Return")))
    for bad in ("Wealth Front", "a;b", "", "x" * 41, "../keepass", "wealth/front"):
        assert not al.valid_steps((("totp", bad),)), bad
    assert not al.valid_steps((("totp", 123456),))


def test_the_code_is_made_when_typed_typed_once_and_only_as_digits(tmp_path):
    rig = Rig()
    typed, asked = [], []
    steps = (("wait", 5), ("totp", "wealthfront"), ("key", "Return"))
    al.run(
        "wealthfront-dragos",
        str(tmp_path),
        steps,
        spawn=rig.spawn,
        send_key=rig.key,
        sleep=rig.sleep,
        close=rig.close,
        send_text=lambda t: typed.append(t) or rig.log.append(("type", len(t))),
        get_code=lambda name: asked.append(name) or "246810",
    )
    assert asked == ["wealthfront"] and typed == ["246810"]
    order = [e for e in rig.log if e[0] in ("wait", "type", "key")]
    assert order == [
        ("wait", 5),
        ("type", 6),
        ("key", "Return"),
    ]  # made after the wait, typed before Return
    assert "246810" not in repr(rig.log)  # only its length is ever recorded


@pytest.mark.parametrize(
    "bad", ["12 3456", "abcdef", "12345", "123456789", "", "123456\n"]
)
def test_a_code_that_is_not_a_short_number_is_never_typed(tmp_path, bad):
    rig, typed = Rig(), []
    with pytest.raises(al.AutoLoginError, match="not a number"):
        al.run(
            "wealthfront-dragos",
            str(tmp_path),
            (("totp", "wealthfront"),),
            spawn=rig.spawn,
            send_key=rig.key,
            sleep=rig.sleep,
            close=rig.close,
            send_text=typed.append,
            get_code=lambda name: bad,
        )
    assert (
        typed == [] and ("close", "google-chrome-stable") in rig.log
    )  # nothing typed, Chrome still closed properly


def test_chrome_is_closed_when_the_code_cannot_be_made(tmp_path):
    def broken(name):
        raise al.AutoLoginError("could not make the one-time code (CredentialsError)")

    rig = Rig()
    with pytest.raises(al.AutoLoginError, match="CredentialsError"):
        al.run(
            "wealthfront-dragos",
            str(tmp_path),
            (("key", "Down"), ("totp", "wealthfront"), ("key", "Return")),
            spawn=rig.spawn,
            send_key=rig.key,
            sleep=rig.sleep,
            close=rig.close,
            send_text=lambda t: None,
            get_code=broken,
        )
    assert [e for e in rig.log if e[0] == "key"] == [
        ("key", "Down")
    ]  # it stopped: Return was not pressed
    assert ("close", "google-chrome-stable") in rig.log


@pytest.fixture
def kdbx(tmp_path, monkeypatch):
    pytest.importorskip("pykeepass")
    from pykeepass import create_database

    path = tmp_path / "twofas.kdbx"
    db = create_database(str(path), password=MASTER)
    entry = db.add_entry(db.root_group, "Wealthfront", "", "")
    entry.otp = f"otpauth://totp/Wealthfront:me?secret={SECRET}&issuer=Wealthfront"
    db.add_entry(db.root_group, "NoCode", "u", "p")
    db.save()
    monkeypatch.setenv("KEEPASS_FILE", str(path))
    monkeypatch.setenv("KEEPASS_PASSWORD", MASTER)
    return path


def test_the_real_code_comes_from_the_keepass_entry_by_title_ignoring_case(kdbx):
    import pyotp

    expected = pyotp.TOTP(SECRET)
    code = al._keepass_code("wealthfront")
    assert code.isdigit() and len(code) == 6
    assert code in {
        expected.at(time.time() + d) for d in (-30, 0, 30)
    }  # the same code an authenticator app shows


def test_keepass_problems_are_named_without_any_secret(kdbx, monkeypatch):
    with pytest.raises(
        al.AutoLoginError, match="no one-time-code entry named 'nothing'"
    ):
        al._keepass_code("nothing")
    with pytest.raises(
        al.AutoLoginError, match="no one-time-code entry named 'nocode'"
    ):
        al._keepass_code("nocode")  # an entry without a one-time-code setting
    monkeypatch.setenv("KEEPASS_PASSWORD", "the wrong master password")
    with pytest.raises(al.AutoLoginError) as e:
        al._keepass_code("wealthfront")
    assert str(e.value).startswith("could not make the one-time code (")
    for secret in (MASTER, "the wrong master password", SECRET, str(kdbx)):
        assert secret not in str(e.value)
    monkeypatch.delenv("KEEPASS_PASSWORD")
    with pytest.raises(al.AutoLoginError, match="KEEPASS_PASSWORD is not set"):
        al._keepass_code("wealthfront")
    monkeypatch.setenv("KEEPASS_PASSWORD", MASTER)
    monkeypatch.setenv("KEEPASS_FILE", "/nonexistent/twofas.kdbx")
    with pytest.raises(al.AutoLoginError) as missing:
        al._keepass_code("wealthfront")
    # the underlying error ("No such file or directory: '<path>'") must not come through: only its type does
    assert str(missing.value) == "could not make the one-time code (FileNotFoundError)"
    assert "/nonexistent" not in str(missing.value)


def test_typing_without_xdotool_is_a_clean_error(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(al.AutoLoginError) as e:
        al._send_text("123456")
    assert str(
        e.value
    ) == "could not send keys (FileNotFoundError)" and "123456" not in str(e.value)
