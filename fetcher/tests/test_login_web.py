import asyncio
import io
import json
import urllib.error

import pytest
from fake_bao import ADDR, WRITER, FakeBao
from fastapi.testclient import TestClient
from fetcher import vault as v
from fetcher import web
from starlette.websockets import WebSocketDisconnect

ORIGIN = "https://fetch.test"
ME = {"X-Email": "me@example.com"}
POST = {**ME, "Origin": ORIGIN, "Content-Type": "application/json"}
VNC_PASSWORD = "Ab3dEf7h"


class FakeBrowser:
    """Stands in for the browser container's control API."""

    def __init__(self):
        self.state, self.account, self.calls = "idle", None, []
        self.down = False

    def _check(self):
        if self.down:
            raise web.BrowserdError("cannot reach the browser service (URLError)")

    def status(self):
        self._check()
        running = self.state == "running"
        return {
            "state": self.state,
            "account": self.account,
            "remaining": 880 if running else 0,
            "result": None,
            "vnc_password": VNC_PASSWORD if running else None,
        }

    def start(self, account):
        self._check()
        self.calls.append(("start", account))
        if self.state == "running":
            raise web.BrowserdError("a login session is already running")
        self.state, self.account = "running", account
        return self.status()

    def stop(self):
        self._check()
        self.calls.append(("stop",))
        self.state = "idle"
        return {**self.status(), "result": "stopped"}


class FakeVnc:
    """A VNC server in memory (no sockets): greets like RFB, then echoes. `refuse` makes the connection fail."""

    def __init__(self):
        self.received, self.refuse, self.connections = [], False, 0

    async def __call__(self, host, port):
        if self.refuse:
            raise ConnectionRefusedError()
        self.connections += 1
        reader = asyncio.StreamReader()
        reader.feed_data(b"RFB 003.008\n")
        server = self

        class Writer:
            closed = False

            def write(self, data):
                server.received.append(data)
                reader.feed_data(b"echo:" + data)

            async def drain(self):
                pass

            def close(self):
                self.closed = True
                reader.feed_eof()

        return reader, Writer()


@pytest.fixture
def novnc(tmp_path):
    root = tmp_path / "novnc"
    (root / "core").mkdir(parents=True)
    (root / "core" / "rfb.js").write_text("export default class RFB {}")
    (tmp_path / "secret.txt").write_text("outside the noVNC directory")
    return root


def make(
    tmp_path,
    novnc,
    vnc=None,
    trusted=frozenset({"testclient"}),
    browser=None,
    expense_url="https://expense.test",
):
    audit = tmp_path / "audit.log"
    settings = web.Settings(
        trusted_proxies=trusted,
        allowed_emails=frozenset({"me@example.com"}),
        public_origin=ORIGIN,
        audit_log=str(audit),
        novnc_dir=str(novnc),
        expense_url=expense_url,
    )
    browser = browser or FakeBrowser()
    app = web.create_app(
        settings,
        v.Vault(ADDR, "", "", FakeBao(), token=WRITER),
        browser,
        vnc or FakeVnc(),
    )
    return TestClient(app), browser, audit


@pytest.fixture
def ctx(tmp_path, novnc):
    return make(tmp_path, novnc)


def post(client, path, payload=None):
    return client.post(path, headers=POST, content=json.dumps(payload or {}))


def test_every_login_route_needs_the_login_and_the_allowed_email(ctx):
    client, browser, _ = ctx
    for path in (
        "/login",
        "/login.js",
        "/novnc/core/rfb.js",
        "/api/login",
        "/api/login/session",
    ):
        assert client.get(path).status_code == 401, path
        assert (
            client.get(path, headers={"X-Email": "eve@example.com"}).status_code == 403
        ), path
    assert (
        client.post(
            "/api/login/venmo-dragos/start", headers={"Origin": ORIGIN}
        ).status_code
        == 401
    )
    assert client.post("/api/login/stop", headers={"Origin": ORIGIN}).status_code == 401
    assert browser.calls == []


def test_the_pages_and_the_novnc_client_are_served_to_the_signed_in_person(ctx):
    client, _, _ = ctx
    assert client.get("/login", headers=ME).status_code == 200
    assert (
        client.get("/login.js", headers=ME)
        .headers["content-type"]
        .startswith("text/javascript")
    )
    r = client.get("/novnc/core/rfb.js", headers=ME)
    assert (
        r.status_code == 200
        and "class RFB" in r.text
        and r.headers["cache-control"] == "no-store"
    )


@pytest.mark.parametrize(
    "path",
    [
        "%2e%2e/secret.txt",
        "core/%2e%2e/%2e%2e/secret.txt",
        "/secret.txt",
        "core",
        "missing.js",
    ],
)
def test_the_novnc_route_cannot_leave_its_directory(ctx, path):
    client, _, _ = ctx
    r = client.get("/novnc/" + path, headers=ME)
    assert r.status_code == 404 and "outside" not in r.text


def test_starting_a_login_needs_origin_json_a_listed_account_and_a_sign_in_flow(ctx):
    client, browser, _ = ctx
    body = "{}"
    for headers, status in [
        ({**ME, "Content-Type": "application/json"}, 403),
        (
            {
                **ME,
                "Origin": "https://evil.example",
                "Content-Type": "application/json",
            },
            403,
        ),
        ({**ME, "Origin": ORIGIN, "Content-Type": "text/plain"}, 415),
    ]:
        assert (
            client.post(
                "/api/login/venmo-dragos/start", headers=headers, content=body
            ).status_code
            == status
        )
    assert (
        post(client, "/api/login/venmo-nobody/start").status_code == 404
    )  # not on the list
    assert (
        post(client, "/api/login/fidelity-dragos/start").status_code == 409
    )  # listed, but no flow yet
    assert browser.calls == []


def test_a_login_starts_once_audits_it_and_never_returns_the_vnc_password(ctx):
    client, browser, audit = ctx
    r = post(client, "/api/login/venmo-dragos/start")
    assert (
        r.status_code == 200
        and r.json()["state"] == "running"
        and r.json()["account"] == "venmo-dragos"
    )
    assert VNC_PASSWORD not in r.text and "vnc_password" not in r.text
    assert browser.calls == [("start", "venmo-dragos")]
    again = post(client, "/api/login/venmo-viral/start")
    assert again.status_code == 409 and "already running" in again.json()["error"]
    status = client.get("/api/login", headers=ME)
    assert (
        status.json()["account"] == "venmo-dragos" and VNC_PASSWORD not in status.text
    )
    lines = [json.loads(line) for line in audit.read_text().splitlines()]
    assert [(x["action"], x["account"], x["ok"]) for x in lines] == [
        ("login-start", "venmo-dragos", True),
        ("login-start", "venmo-viral", False),
    ]
    assert VNC_PASSWORD not in audit.read_text()


def test_the_vnc_password_goes_only_to_the_signed_in_person_while_a_session_runs(ctx):
    client, browser, _ = ctx
    assert client.get("/api/login/session", headers=ME).status_code == 404
    post(client, "/api/login/venmo-dragos/start")
    r = client.get("/api/login/session", headers=ME)
    assert r.json() == {"password": VNC_PASSWORD, "account": "venmo-dragos"}
    assert r.headers["cache-control"] == "no-store"
    assert client.get("/api/login/session").status_code == 401
    post(client, "/api/login/stop")
    assert client.get("/api/login/session", headers=ME).status_code == 404


def test_stopping_needs_origin_and_json_and_is_audited(ctx):
    client, browser, audit = ctx
    post(client, "/api/login/venmo-dragos/start")
    assert (
        client.post(
            "/api/login/stop", headers={**ME, "Content-Type": "application/json"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/login/stop",
            headers={**ME, "Origin": ORIGIN, "Content-Type": "text/plain"},
        ).status_code
        == 415
    )
    assert browser.state == "running"
    r = post(client, "/api/login/stop")
    assert (
        r.status_code == 200
        and r.json()["result"] == "stopped"
        and browser.state == "idle"
    )
    assert json.loads(audit.read_text().splitlines()[-1])["action"] == "login-stop"


def test_login_starts_are_rate_limited(ctx):
    client, browser, _ = ctx
    codes = []
    for _ in range(8):
        codes.append(post(client, "/api/login/venmo-dragos/start").status_code)
        post(client, "/api/login/stop")
    assert codes[:6] == [200] * 6 and codes[6:] == [429, 429]


def test_a_down_browser_service_is_a_clear_error(ctx):
    client, browser, _ = ctx
    browser.down = True
    r = client.get("/api/login", headers=ME)
    assert (
        r.status_code == 502
        and "cannot reach the browser service" in r.json()["detail"]
    )
    assert post(client, "/api/login/venmo-dragos/start").status_code == 409


def test_the_account_list_says_which_accounts_can_log_in_by_hand(ctx):
    client, _, _ = ctx
    by = {
        a["key"]: a["login"]
        for a in client.get("/api/accounts", headers=ME).json()["accounts"]
    }
    assert by["venmo-dragos"] is True and by["venmo-viral"] is True
    assert by["citi"] is False and by["fidelity-dragos"] is False


# --- the WebSocket bridge -----------------------------------------------------------------------------------------


def ws_headers(**over):
    return {**ME, "Origin": ORIGIN, **over}


def refused(client, headers):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws/vnc", headers=headers, subprotocols=["binary"]
        ):
            pass


def test_the_socket_is_refused_without_login_origin_session_or_a_trusted_peer(
    tmp_path, novnc
):
    client, browser, _ = make(tmp_path, novnc)
    post(client, "/api/login/venmo-dragos/start")
    refused(client, {"Origin": ORIGIN})  # no login header
    refused(client, ws_headers(**{"X-Email": "eve@example.com"}))
    refused(
        client, {**ME}
    )  # no Origin: a page on another site cannot set this, a script of ours always does
    refused(client, ws_headers(Origin="https://evil.example"))
    stranger, sbrowser, _ = make(tmp_path, novnc, trusted=frozenset({"192.168.1.232"}))
    sbrowser.start("venmo-dragos")  # a session IS running; only the peer is wrong
    assert sbrowser.state == "running"
    refused(stranger, ws_headers())  # the login header is only believed from the proxy
    idle, _, _ = make(tmp_path, novnc)
    refused(idle, ws_headers())  # no session running


def test_the_socket_carries_bytes_both_ways_and_allows_one_viewer(ctx):
    client, browser, _ = ctx
    post(client, "/api/login/venmo-dragos/start")
    with client.websocket_connect(
        "/ws/vnc", headers=ws_headers(), subprotocols=["binary"]
    ) as ws:
        assert ws.receive_bytes() == b"RFB 003.008\n"
        ws.send_bytes(b"\x01\x02hello")
        assert ws.receive_bytes() == b"echo:\x01\x02hello"
        refused(
            client, ws_headers()
        )  # a second viewer is turned away while this one is connected
    # once it disconnects another can connect
    with client.websocket_connect(
        "/ws/vnc", headers=ws_headers(), subprotocols=["binary"]
    ) as ws:
        assert ws.receive_bytes() == b"RFB 003.008\n"


def test_a_vnc_server_that_is_not_there_closes_the_socket_cleanly(tmp_path, novnc):
    refusing = FakeVnc()
    refusing.refuse = True
    client, browser, _ = make(tmp_path, novnc, vnc=refusing)
    post(client, "/api/login/venmo-dragos/start")
    refused(client, ws_headers())


# --- the client for the browser container ------------------------------------------------------------------------


class Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self, *a):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_browser_client_sends_the_token_and_reports_refusals_without_it():
    seen = []

    def opener(req, timeout=None):
        seen.append(
            (req.get_method(), req.full_url, req.get_header("Authorization"), req.data)
        )
        if req.full_url.endswith("/start"):
            raise urllib.error.HTTPError(
                req.full_url,
                409,
                "x",
                {},
                io.BytesIO(b'{"detail": "a login session is already running"}'),
            )
        if req.full_url.endswith("/stop"):
            raise urllib.error.HTTPError(
                req.full_url,
                500,
                "x",
                {},
                io.BytesIO(b"Bearer SECRETTOKEN-0123456789abcdef"),
            )
        return Resp({"state": "idle"})

    b = web.Browserd("http://127.0.0.1:8097/", "SECRETTOKEN-0123456789abcdef", opener)
    assert b.status() == {"state": "idle"}
    assert seen[0][:3] == (
        "GET",
        "http://127.0.0.1:8097/status",
        "Bearer SECRETTOKEN-0123456789abcdef",
    )
    with pytest.raises(web.BrowserdError, match="already running"):
        b.start("venmo-dragos")
    assert json.loads(seen[1][3]) == {"account": "venmo-dragos"}
    with pytest.raises(web.BrowserdError) as e:
        b.stop()
    assert "HTTP 500" in str(e.value) and "SECRETTOKEN" not in str(e.value)

    def down(req, timeout=None):
        raise urllib.error.URLError("refused for SECRETTOKEN")

    with pytest.raises(web.BrowserdError) as e:
        web.Browserd("http://x", "SECRETTOKEN-0123456789abcdef", down).status()
    assert "URLError" in str(e.value) and "SECRETTOKEN" not in str(e.value)


# --- Done sends the person to the expense app ---------------------------------------------------------------------


def test_the_login_status_and_the_stop_reply_say_where_done_goes(ctx):
    client, browser, _ = ctx
    assert (
        client.get("/api/login", headers=ME).json()["expense_url"]
        == "https://expense.test"
    )
    post(client, "/api/login/venmo-dragos/start")
    stopped = post(client, "/api/login/stop")
    assert (
        stopped.json()["expense_url"] == "https://expense.test"
        and stopped.json()["result"] == "stopped"
    )
    assert VNC_PASSWORD not in stopped.text


def test_without_an_expense_url_done_just_stops(tmp_path, novnc):
    client, _, _ = make(tmp_path, novnc, expense_url="")
    assert client.get("/api/login", headers=ME).json()["expense_url"] == ""


def test_the_expense_url_comes_only_from_the_servers_own_setting(monkeypatch):
    assert (
        web.Settings.from_env(
            {"EXPENSE_URL": "https://expense.velicanu.com/"}
        ).expense_url
        == "https://expense.velicanu.com"
    )
    assert web.Settings.from_env({}).expense_url == ""
