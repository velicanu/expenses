import json
import threading

import pytest
from fastapi.testclient import TestClient
from fetcher import browserd, venmo
from fetcher import fetch as fetch_mod
from fetcher import institutions as inst
from test_browserd import AUTH, TOKEN, World


def runner_returning(result, calls=None):
    def run(account, months, profiles):
        if calls is not None:
            calls.append((account, list(months), profiles))
        return result

    return run


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def sessions(world, runner):
    return world.sessions(fetch_runner=runner)


# --- the browser service's /fetch ----------------------------------------------------------------------------------


def test_a_fetch_runs_on_the_account_and_returns_what_the_runner_found(world):
    calls = []
    result = {"state": "logged_in", "files": [{"month": "2026-11", "csv": "x"}]}
    s = sessions(world, runner_returning(result, calls))
    assert s.fetch("venmo-dragos", ["2026-10", "2026-11"]) == result
    assert calls == [("venmo-dragos", ["2026-10", "2026-11"], "/profiles")]


@pytest.mark.parametrize(
    "account,months",
    [
        ("fidelity-dragos", ["2026-11"]),  # no sign-in flow
        ("venmo-dragos", []),
        ("venmo-dragos", ["2026-13"]),
        ("venmo-dragos", ["2026-1"]),
        ("venmo-dragos", ["November 2026"]),
        ("venmo-dragos", ["2026-11; rm -rf /"]),
        ("venmo-dragos", [f"2024-{m:02d}" for m in range(1, 13)] * 3),  # too many
        ("../x", ["2026-11"]),
    ],
)
def test_bad_requests_run_nothing(world, account, months):
    calls = []
    s = sessions(world, runner_returning({"state": "logged_in", "files": []}, calls))
    with pytest.raises(browserd.StartError):
        s.fetch(account, months)
    assert calls == []


def test_a_fetch_and_a_hand_login_never_overlap(world):
    gate, entered = threading.Event(), threading.Event()
    result = {"state": "logged_in", "files": []}

    def slow(account, months, profiles):
        entered.set()
        gate.wait(5)
        return result

    s = sessions(world, slow)
    t = threading.Thread(target=lambda: s.fetch("venmo-dragos", ["2026-11"]))
    t.start()
    assert entered.wait(5)
    with pytest.raises(browserd.StartError, match="fetch is already running"):
        s.fetch("venmo-dragos", ["2026-11"])
    with pytest.raises(browserd.StartError, match="fetch is running"):
        s.start("venmo-dragos")  # the browser profile is in use
    gate.set()
    t.join(5)
    s.start("venmo-dragos")  # free again afterwards
    with pytest.raises(browserd.StartError, match="login session is open"):
        s.fetch("venmo-dragos", ["2026-11"])


def test_a_crashing_fetch_releases_the_lock(world):
    def boom(account, months, profiles):
        raise RuntimeError("boom")

    s = sessions(world, boom)
    with pytest.raises(RuntimeError):
        s.fetch("venmo-dragos", ["2026-11"])
    s._fetch_runner = runner_returning({"state": "logged_in", "files": []})
    assert s.fetch("venmo-dragos", ["2026-11"])["state"] == "logged_in"


def test_the_fetch_endpoint_needs_the_token_and_reports_conflicts(world):
    result = {"state": "logged_in", "files": []}
    c = TestClient(
        browserd.create_app(TOKEN, sessions(world, runner_returning(result)))
    )
    body = {"account": "venmo-dragos", "months": ["2026-11"]}
    assert c.post("/fetch", json=body).status_code == 401
    assert (
        c.post(
            "/fetch", json=body, headers={"Authorization": "Bearer nope"}
        ).status_code
        == 401
    )
    assert c.post("/fetch", json=body, headers=AUTH).json() == result
    assert (
        c.post(
            "/fetch", json={"account": "venmo-dragos", "months": ["bad"]}, headers=AUTH
        ).status_code
        == 409
    )
    c.post("/start", headers=AUTH, json={"account": "venmo-dragos"})
    r = c.post("/fetch", json=body, headers=AUTH)
    assert r.status_code == 409 and "login session is open" in r.json()["detail"]


def test_the_real_runner_reduces_a_missing_browser_to_a_clear_error(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PATH", str(tmp_path))  # no xvfb-run on the path
    out = browserd._run_fetch("venmo-dragos", ["2026-11"], "/profiles", timeout=5)
    assert (
        out["state"] == "error"
        and "FileNotFoundError" in out["message"]
        and out["files"] == []
    )


def test_the_real_runner_parses_the_childs_last_json_line_and_enforces_a_timeout(
    tmp_path, monkeypatch
):
    import stat

    fake = tmp_path / "xvfb-run"
    fake.write_text(
        '#!/bin/sh\nshift 2\necho \'warning: noise\'\necho \'{"state": "logged_in", "files": []}\'\n'
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    assert browserd._run_fetch(
        "venmo-dragos", ["2026-11"], "/profiles", timeout=10
    ) == {"state": "logged_in", "files": []}
    fake.write_text("#!/bin/sh\necho 'no json here'\n")
    assert (
        browserd._run_fetch("venmo-dragos", ["2026-11"], "/profiles", timeout=10)[
            "state"
        ]
        == "error"
    )
    fake.write_text("#!/bin/sh\nsleep 30\n")
    out = browserd._run_fetch("venmo-dragos", ["2026-11"], "/profiles", timeout=1)
    assert out == {"state": "error", "message": "the fetch took too long", "files": []}


# --- venmo.py with a fake page -------------------------------------------------------------------------------------


class FakeLocator:
    def __init__(self, page, kind):
        self.page, self.kind = page, kind

    def count(self):
        return 0 if self.page.missing == self.kind else 1

    def click(self):
        if self.kind == "button":
            self.page.events.append(("download", self.page.value))

    def fill(self, text):
        self.page.typed = text

    def input_value(self):
        return self.page.value


class FakePage:
    def __init__(self, missing=None, ignore_typing=False):
        self.events, self.value, self.typed, self.missing, self.ignore = (
            [],
            "November 2026",
            None,
            missing,
            ignore_typing,
        )
        outer = self

        class Keyboard:
            def press(self, key):
                outer.events.append(("press", key))
                if key == "Enter" and not outer.ignore:
                    outer.value = outer.typed

        self.keyboard = Keyboard()

    def locator(self, selector):
        assert selector == "input[placeholder='MMMM YYYY']"
        return FakeLocator(self, "field")

    def get_by_role(self, role, name):
        assert (role, name) == ("button", "Download CSV")
        return FakeLocator(self, "button")

    def wait_for_timeout(self, ms):
        pass

    def expect_download(self, timeout):
        page = self

        class Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            @property
            def value(self_inner):
                class D:
                    def path(self_d):
                        return page.csv_path

                return D()

        return Ctx()


def test_month_labels():
    assert venmo.month_label("2025-12") == "December 2025"
    assert venmo.month_label("2026-01") == "January 2026"
    assert venmo.month_label("2026-09") == "September 2026"


def test_each_month_is_typed_selected_and_downloaded_in_order_with_a_pause(tmp_path):
    page = FakePage()
    csv_file = tmp_path / "s.csv"
    csv_file.write_text("﻿Account Statement\n,ID,Datetime\n")
    page.csv_path = str(csv_file)
    pauses = []
    files = venmo.fetch_statements(
        page, ["2026-01", "2026-02", "2026-03"], pause=4, sleep=pauses.append
    )
    assert [f["month"] for f in files] == ["2026-01", "2026-02", "2026-03"]
    assert files[0]["csv"].startswith(
        "Account Statement"
    )  # the byte-order mark is dropped
    assert [e for e in page.events if e[0] == "download"] == [
        ("download", "January 2026"),
        ("download", "February 2026"),
        ("download", "March 2026"),
    ]
    assert pauses == [4, 4]  # between downloads, not before the first


def test_a_page_that_changed_fails_loudly_instead_of_downloading_the_wrong_month(
    tmp_path,
):
    with pytest.raises(venmo.VenmoPageError, match="month field"):
        venmo.fetch_statements(FakePage(missing="field"), ["2026-01"])
    with pytest.raises(venmo.VenmoPageError, match="Download CSV"):
        venmo.fetch_statements(FakePage(missing="button"), ["2026-01"])
    stuck = FakePage(ignore_typing=True)
    with pytest.raises(venmo.VenmoPageError, match="could not select January 2026"):
        venmo.fetch_statements(stuck, ["2026-01"])
    assert not [
        e for e in stuck.events if e[0] == "download"
    ]  # nothing was downloaded for the wrong month


# --- fetch.py: the login check -----------------------------------------------------------------------------------


def test_every_login_verdict_has_a_state_name():
    assert fetch_mod.STATES == {
        inst.LOGGED_IN: "logged_in",
        inst.LOGIN_REQUIRED: "login_required",
        inst.CHALLENGE: "challenge",
        inst.UNKNOWN: "unknown",
    }


def test_main_prints_one_json_line_and_never_a_traceback(capsys, monkeypatch):
    monkeypatch.setattr(
        fetch_mod,
        "fetch",
        lambda account, months: {"state": "login_required", "files": []},
    )
    assert fetch_mod.main("venmo-dragos", ["2026-11"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "state": "login_required",
        "files": [],
    }

    def broken(account, months):
        raise RuntimeError("secret page text 123")

    monkeypatch.setattr(fetch_mod, "fetch", broken)
    fetch_mod.main("venmo-dragos", ["2026-11"])
    out = json.loads(capsys.readouterr().out)
    assert out == {
        "state": "error",
        "message": "RuntimeError",
        "files": [],
    } and "secret" not in json.dumps(out)

    def page_changed(account, months):
        raise venmo.VenmoPageError(
            "the month field is not on the page (Venmo changed it?)"
        )

    monkeypatch.setattr(fetch_mod, "fetch", page_changed)
    fetch_mod.main("venmo-dragos", ["2026-11"])
    assert "month field" in json.loads(capsys.readouterr().out)["message"]


# --- fetch(): the login check, with a fake Playwright ----------------------------------------------------------------


class _Resp:
    def __init__(self, status):
        self.status = status


class _FakeChromePage:
    def __init__(self, url, status, text="", password_field=False, title="Venmo"):
        self.url, self._status, self._text, self._pw, self._title = (
            url,
            status,
            text,
            password_field,
            title,
        )

    def goto(self, url, **kw):
        return _Resp(self._status)

    def wait_for_timeout(self, ms):
        pass

    def title(self):
        return self._title

    def inner_text(self, selector):
        return self._text

    def query_selector(self, selector):
        return object() if self._pw else None


class _FakeContext:
    def __init__(self, page):
        self.pages, self.closed = [page], False

    def close(self):
        self.closed = True


def _with_fake_playwright(monkeypatch, page):
    import sys
    import types

    ctx = _FakeContext(page)

    class Chromium:
        def launch_persistent_context(self, *a, **kw):
            return ctx

    class PW:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    module = types.ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: PW()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    return ctx


def test_a_bot_challenge_is_reported_with_its_status_and_page_but_no_query_or_text(
    monkeypatch, tmp_path
):
    page = _FakeChromePage(
        "https://id.venmo.com/signin?country.x=US&secret=abc",
        403,
        text="Confirm you're human",
        title="venmo.com",
    )
    ctx = _with_fake_playwright(monkeypatch, page)
    out = fetch_mod.fetch("venmo-dragos", ["2026-11"], profiles=str(tmp_path))
    assert out == {
        "state": "challenge",
        "files": [],
        "detail": "HTTP 403 at id.venmo.com/signin",
    }
    assert "secret" not in json.dumps(out) and "human" not in json.dumps(out)
    assert ctx.closed  # Chrome is closed properly in every case


def test_a_login_page_is_login_required_and_a_logged_in_page_downloads(
    monkeypatch, tmp_path
):
    login = _FakeChromePage(
        "https://id.venmo.com/signin", 200, text="Log in", password_field=True
    )
    ctx = _with_fake_playwright(monkeypatch, login)
    out = fetch_mod.fetch("venmo-dragos", ["2026-11"], profiles=str(tmp_path))
    assert (
        out["state"] == "login_required"
        and out["detail"] == "HTTP 200 at id.venmo.com/signin"
        and ctx.closed
    )

    good = _FakeChromePage(
        "https://account.venmo.com/statement?month=11",
        200,
        text="Account Statement",
        title="Venmo | Account Statement",
    )
    ctx = _with_fake_playwright(monkeypatch, good)
    monkeypatch.setattr(
        fetch_mod.venmo,
        "fetch_statements",
        lambda page, months: [{"month": m, "csv": "c"} for m in months],
    )
    assert fetch_mod.fetch(
        "venmo-dragos", ["2026-10", "2026-11"], profiles=str(tmp_path)
    ) == {
        "state": "logged_in",
        "files": [{"month": "2026-10", "csv": "c"}, {"month": "2026-11", "csv": "c"}],
    }
    assert ctx.closed


def test_chrome_is_closed_even_when_a_download_fails(monkeypatch, tmp_path):
    good = _FakeChromePage(
        "https://account.venmo.com/statement",
        200,
        text="Account Statement",
        title="Venmo | Account Statement",
    )
    ctx = _with_fake_playwright(monkeypatch, good)

    def boom(page, months):
        raise venmo.VenmoPageError(
            "the month field is not on the page (Venmo changed it?)"
        )

    monkeypatch.setattr(fetch_mod.venmo, "fetch_statements", boom)
    with pytest.raises(venmo.VenmoPageError):
        fetch_mod.fetch("venmo-dragos", ["2026-11"], profiles=str(tmp_path))
    assert ctx.closed
