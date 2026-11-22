"""Linking a bank through Plaid Link, reconnecting one, and the nightly pull: against a fake Plaid client."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from server import cli
from server.app import create_app
from server.settings import Settings
from server.store import PipelineBusy, Stores

ME = {"X-Email": "me@example.com"}
OTHER = {"X-Email": "other@example.com"}
TOKEN = "access-production-11111111-2222-3333-4444-555555555555"
NEW_TOKEN = "access-production-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class PlaidApiError(Exception):
    """What the plaid SDK raises: the response body is a JSON string."""

    def __init__(self, code, message="a message"):
        self.body = json.dumps(
            {"error_type": "ITEM_ERROR", "error_code": code, "error_message": message}
        )


class FakeItem(dict):
    pass


class FakePlaid:
    def __init__(self):
        self.calls = []
        self.item_error = {}  # access token -> error code
        self.fail = {}  # method name -> error code

    def _maybe_fail(self, name):
        if name in self.fail:
            raise PlaidApiError(self.fail[name])

    def link_token_create(self, req):
        self._maybe_fail("link_token_create")
        self.calls.append(("link_token_create", req))
        return {"link_token": "link-production-abc"}

    def item_public_token_exchange(self, req):
        self._maybe_fail("item_public_token_exchange")
        self.calls.append(("exchange", req))
        return {"access_token": NEW_TOKEN}

    def item_get(self, req):
        self._maybe_fail("item_get")
        code = self.item_error.get(req.access_token)
        item = {
            "institution_id": "ins_1",
            "error": {"error_code": code} if code else None,
        }
        item["consent_expiration_time"] = None
        return {"item": item}

    def institutions_get_by_id(self, req):
        self._maybe_fail("institutions_get_by_id")
        return {"institution": {"name": "Capital One"}}


@pytest.fixture
def plaid():
    return FakePlaid()


def make_app(root, plaid, **kw):
    settings = Settings(
        data_root=root,
        users={"me@example.com": "me", "other@example.com": "other"},
        trusted_proxies=frozenset({"testclient"}),
        plaid_redirect_uri="https://expense.example/plaid-oauth",
        **kw,
    )
    app = create_app(settings, plaid_client_factory=lambda keys: plaid)
    app.state.plaid = type(
        "Keys",
        (),
        {"configured": True, "get": lambda self: {"client_id": "i", "secret": "s"}},
    )()
    return app


@pytest.fixture
def client(tmp_path, plaid):
    root = tmp_path / "data"
    root.mkdir()
    return TestClient(make_app(root, plaid))


def link_account(root, alias="card", token=TOKEN, user="me"):
    d = root / user
    d.mkdir(parents=True, exist_ok=True)
    cfg = {
        "linked_accounts": {
            alias: {
                "alias": alias,
                "institution": "Capital One",
                "start_date": "2025-12-31",
                "token": token,
            }
        }
    }
    (d / "config.json").write_text(json.dumps(cfg))


# --- link tokens ---------------------------------------------------------------------------------------


def test_a_new_link_asks_for_transactions_and_two_years_of_history(client, plaid):
    r = client.post("/api/plaid/link-token", json={}, headers=ME)
    assert r.status_code == 200 and r.json() == {
        "link_token": "link-production-abc",
        "mode": "new",
    }
    req = plaid.calls[0][1]
    assert [str(p) for p in req.products] == ["transactions"]
    assert req.transactions.days_requested == 730  # Plaid's default is 90 days
    assert req.redirect_uri == "https://expense.example/plaid-oauth"
    assert req.user.client_user_id == "me" and not hasattr(req, "access_token")


def test_reconnecting_uses_update_mode_with_the_stored_token(client, plaid, tmp_path):
    link_account(tmp_path / "data")
    r = client.post("/api/plaid/link-token", json={"alias": "card"}, headers=ME)
    assert r.json() == {"link_token": "link-production-abc", "mode": "update"}
    req = plaid.calls[0][1]
    assert req.access_token == TOKEN
    assert not hasattr(req, "products") and not hasattr(
        req, "transactions"
    )  # the item already has them
    assert TOKEN not in r.text


def test_an_older_alias_with_capitals_can_still_be_reconnected(client, plaid, tmp_path):
    link_account(tmp_path / "data", alias="Old_Card")
    assert (
        client.post(
            "/api/plaid/link-token", json={"alias": "Old_Card"}, headers=ME
        ).json()["mode"]
        == "update"
    )


def test_link_token_errors(client, plaid, tmp_path):
    assert (
        client.post(
            "/api/plaid/link-token", json={"alias": "nope"}, headers=ME
        ).status_code
        == 404
    )
    assert (
        client.post("/api/plaid/link-token", json={"alias": ""}, headers=ME).status_code
        == 422
    )
    assert (
        client.post(
            "/api/plaid/link-token", json={"alias": "x" * 65}, headers=ME
        ).status_code
        == 422
    )
    assert (
        client.post("/api/plaid/link-token", json={"x": 1}, headers=ME).status_code
        == 422
    )
    plaid.fail["link_token_create"] = "INVALID_FIELD"
    r = client.post("/api/plaid/link-token", json={}, headers=ME)
    assert r.status_code == 502 and r.json()["code"] == "INVALID_FIELD"


def test_without_bao_keys_linking_is_a_clear_503(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    app = make_app(root, FakePlaid())
    app.state.plaid = type(
        "Keys",
        (),
        {
            "configured": False,
            "get": lambda self: (_ for _ in ()).throw(
                __import__("server.bao", fromlist=["x"]).PlaidUnavailable(
                    "bao is not configured"
                )
            ),
        },
    )()
    r = TestClient(app).post("/api/plaid/link-token", json={}, headers=ME)
    assert r.status_code == 503 and "Plaid is unavailable" in r.json()["detail"]


# --- exchanging the public token -----------------------------------------------------------------------


def test_exchange_stores_the_account_and_never_returns_the_token(
    client, plaid, tmp_path
):
    root = tmp_path / "data"
    r = client.post(
        "/api/plaid/exchange",
        json={
            "public_token": "public-production-xyz",
            "alias": "capital-one-new",
            "start_date": "2026-01-01",
        },
        headers=ME,
    )
    assert r.status_code == 201
    assert r.json() == {
        "alias": "capital-one-new",
        "institution": "Capital One",
        "start_date": "2026-01-01",
    }
    cfg = json.loads((root / "me" / "config.json").read_text())
    assert cfg["linked_accounts"]["capital-one-new"] == {
        "alias": "capital-one-new",
        "institution": "Capital One",
        "start_date": "2026-01-01",
        "token": NEW_TOKEN,
    }
    for path in ("/api/accounts", "/api/meta"):
        assert NEW_TOKEN not in client.get(path, headers=ME).text
    assert NEW_TOKEN not in r.text
    assert client.get("/api/accounts", headers=ME).json() == [
        {
            "alias": "capital-one-new",
            "institution": "Capital One",
            "start_date": "2026-01-01",
        }
    ]


def test_exchange_defaults_to_the_old_apps_start_date(client, tmp_path):
    r = client.post(
        "/api/plaid/exchange",
        json={"public_token": "public-production-xyz", "alias": "card"},
        headers=ME,
    )
    assert r.json()["start_date"] == date(date.today().year, 1, 1).isoformat()


def test_exchange_keeps_other_config_and_refuses_an_alias_in_use(
    client, plaid, tmp_path
):
    root = tmp_path / "data"
    link_account(root)
    cfg = json.loads((root / "me" / "config.json").read_text())
    cfg["rules"] = {"description": {"a": "B"}}
    (root / "me" / "config.json").write_text(json.dumps(cfg))
    r = client.post(
        "/api/plaid/exchange",
        json={"public_token": "public-production-xyz", "alias": "card"},
        headers=ME,
    )
    assert r.status_code == 409 and "Reconnect" in r.json()["detail"]
    assert (
        json.loads((root / "me" / "config.json").read_text())["linked_accounts"][
            "card"
        ]["token"]
        == TOKEN
    )
    ok = client.post(
        "/api/plaid/exchange",
        json={"public_token": "public-production-xyz", "alias": "second"},
        headers=ME,
    )
    assert ok.status_code == 201
    after = json.loads((root / "me" / "config.json").read_text())
    assert after["rules"] == {"description": {"a": "B"}} and set(
        after["linked_accounts"]
    ) == {"card", "second"}


@pytest.mark.parametrize(
    "alias", ["", "UPPER", "has space", "-leading", "x" * 49, "../etc"]
)
def test_exchange_validates_the_alias(client, alias):
    r = client.post(
        "/api/plaid/exchange",
        json={"public_token": "public-production-xyz", "alias": alias},
        headers=ME,
    )
    assert r.status_code == 422


def test_exchange_failure_is_reported_by_code_and_stores_nothing(
    client, plaid, tmp_path
):
    plaid.fail["item_public_token_exchange"] = "INVALID_PUBLIC_TOKEN"
    r = client.post(
        "/api/plaid/exchange",
        json={"public_token": "public-production-xyz", "alias": "card"},
        headers=ME,
    )
    assert r.status_code == 502 and r.json()["code"] == "INVALID_PUBLIC_TOKEN"
    assert "public-production-xyz" not in r.text
    assert not (tmp_path / "data" / "me" / "config.json").exists()


def test_a_failed_institution_lookup_still_links_the_account(client, plaid):
    plaid.fail["institutions_get_by_id"] = "INTERNAL_SERVER_ERROR"
    r = client.post(
        "/api/plaid/exchange",
        json={"public_token": "public-production-xyz", "alias": "card"},
        headers=ME,
    )
    assert r.status_code == 201 and r.json()["institution"] is None


# --- status and reconnect ------------------------------------------------------------------------------


def test_status_says_which_connection_needs_a_reconnect(client, plaid, tmp_path):
    root = tmp_path / "data"
    link_account(root)
    assert client.post("/api/accounts/status", headers=ME).json() == [
        {
            "alias": "card",
            "institution": "Capital One",
            "start_date": "2025-12-31",
            "ok": True,
            "error_code": None,
            "needs_reconnect": False,
            "consent_expires": None,
        }
    ]
    plaid.item_error[TOKEN] = "ITEM_LOGIN_REQUIRED"
    s = client.post("/api/accounts/status", headers=ME).json()[0]
    assert (s["ok"], s["error_code"], s["needs_reconnect"]) == (
        False,
        "ITEM_LOGIN_REQUIRED",
        True,
    )
    plaid.item_error[TOKEN] = "INSTITUTION_DOWN"
    s = client.post("/api/accounts/status", headers=ME).json()[0]
    assert (s["ok"], s["needs_reconnect"]) == (
        False,
        False,
    )  # the bank is down: reconnecting would not help
    assert TOKEN not in client.post("/api/accounts/status", headers=ME).text


def test_status_survives_a_plaid_error_per_account(client, plaid, tmp_path):
    link_account(tmp_path / "data")
    plaid.fail["item_get"] = "ITEM_LOGIN_REQUIRED"
    s = client.post("/api/accounts/status", headers=ME).json()[0]
    assert s["needs_reconnect"] is True and s["error_code"] == "ITEM_LOGIN_REQUIRED"
    assert (
        client.post("/api/accounts/status", headers=OTHER).json() == []
    )  # nothing linked for them


def test_a_pull_that_hits_an_expired_login_says_to_reconnect(client, plaid, tmp_path):
    link_account(tmp_path / "data")
    plaid.transactions_get = lambda req: (_ for _ in ()).throw(
        PlaidApiError("ITEM_LOGIN_REQUIRED", "login required")
    )
    out = client.post("/api/accounts/pull", headers=ME).json()
    assert (
        out["accounts"][0]["needs_reconnect"] is True
        and out["accounts"][0]["code"] == "ITEM_LOGIN_REQUIRED"
    )
    assert TOKEN not in json.dumps(out) and out["pipeline"] is None


# --- the page Plaid returns to, and the CSP -------------------------------------------------------------


def test_the_oauth_return_address_serves_the_web_app(tmp_path, plaid):
    root, web = tmp_path / "data", tmp_path / "web"
    root.mkdir()
    web.mkdir()
    (web / "index.html").write_text("<div id=root>app</div>")
    c = TestClient(make_app(root, plaid, static_dir=web))
    r = c.get("/plaid-oauth", params={"oauth_state_id": "abc"})
    assert (
        r.status_code == 200
        and "app" in r.text
        and r.headers["content-type"].startswith("text/html")
    )
    assert (
        TestClient(make_app(root, plaid)).get("/plaid-oauth").status_code == 404
    )  # no web app configured


def test_the_csp_lets_plaid_link_load_and_nothing_else_new(client):
    csp = client.get("/api/me", headers=ME).headers["content-security-policy"]
    assert (
        "script-src 'self' https://cdn.plaid.com" in csp
        and "frame-src https://cdn.plaid.com" in csp
    )
    assert (
        "default-src 'self'" in csp
        and "frame-ancestors 'none'" in csp
        and "unsafe-eval" not in csp
    )


def test_meta_says_whether_oauth_banks_can_return(client, tmp_path):
    assert client.get("/api/meta", headers=ME).json()["plaid_oauth_ready"] is True
    root = tmp_path / "other"
    root.mkdir()
    settings = Settings(
        data_root=root,
        users={"me@example.com": "me"},
        trusted_proxies=frozenset({"testclient"}),
    )
    assert (
        TestClient(create_app(settings))
        .get("/api/meta", headers=ME)
        .json()["plaid_oauth_ready"]
        is False
    )


def test_the_new_endpoints_need_the_login(client):
    for path, body in [
        ("/api/plaid/link-token", {}),
        ("/api/plaid/exchange", {"public_token": "x" * 12, "alias": "a"}),
        ("/api/accounts/status", None),
    ]:
        assert (
            client.post(
                path, **({"json": body} if body is not None else {})
            ).status_code
            == 401
        ), path


def test_users_cannot_reconnect_each_others_accounts(client, tmp_path):
    link_account(tmp_path / "data", user="me")
    assert (
        client.post(
            "/api/plaid/link-token", json={"alias": "card"}, headers=OTHER
        ).status_code
        == 404
    )


# --- one pull at a time, and the nightly command -------------------------------------------------------


def test_a_second_pull_at_the_same_time_is_refused(client, tmp_path, plaid):
    link_account(tmp_path / "data")
    store = client.app.state.stores.get("me")
    with store.exclusive("pull"):
        r = client.post("/api/accounts/pull", headers=ME)
        assert r.status_code == 409
        with pytest.raises(PipelineBusy), store.exclusive("pull"):
            pass
    with store.exclusive("pull"):  # released afterwards
        pass


def test_the_lock_is_per_name(tmp_path):
    store = Stores(tmp_path).get("me")
    with store.exclusive("pull"), store.exclusive("pipeline"):
        pass


def cli_settings(root):
    return Settings(
        data_root=root,
        users={
            "me@example.com": "me",
            "other@example.com": "other",
            "me2@example.com": "me",
        },
        trusted_proxies=frozenset(),
    )


class FakeTx:
    def __init__(self, i):
        self.i = i

    def to_dict(self):
        return {
            "transaction_id": f"t{self.i}",
            "category": ["Food"],
            "name": f"SHOP {self.i}",
            "amount": 2.5,
            "date": date(2026, 3, 1),
            "authorized_date": None,
        }


def test_the_nightly_pull_pulls_each_user_with_accounts_and_reports(
    tmp_path, capsys, monkeypatch
):
    root = tmp_path / "data"
    link_account(root)  # only "me" has an account
    plaid = FakePlaid()
    plaid.transactions_get = lambda req: {
        "transactions": [FakeTx(i) for i in range(3)],
        "total_transactions": 3,
    }
    monkeypatch.setattr(
        "server.cli.PlaidKeys",
        lambda bao: type(
            "K", (), {"get": lambda self: {"client_id": "i", "secret": "s"}}
        )(),
    )
    assert cli.pull(cli_settings(root), client_factory=lambda keys: plaid) == 0
    out = capsys.readouterr().out
    assert (
        "me/card: pulled 3" in out and "rebuilt" in out and "other" not in out
    )  # users without accounts are skipped
    assert (root / "me" / "cards" / "card.json").exists()
    assert TOKEN not in out


def test_the_nightly_pull_exits_nonzero_and_says_when_a_reconnect_is_needed(
    tmp_path, capsys, monkeypatch
):
    root = tmp_path / "data"
    link_account(root)
    plaid = FakePlaid()
    plaid.transactions_get = lambda req: (_ for _ in ()).throw(
        PlaidApiError("ITEM_LOGIN_REQUIRED", "login")
    )
    monkeypatch.setattr(
        "server.cli.PlaidKeys",
        lambda bao: type(
            "K", (), {"get": lambda self: {"client_id": "i", "secret": "s"}}
        )(),
    )
    assert cli.pull(cli_settings(root), client_factory=lambda keys: plaid) == 1
    out = capsys.readouterr().out
    assert (
        "FAILED" in out
        and "ITEM_LOGIN_REQUIRED" in out
        and "reconnect it in the app" in out
        and TOKEN not in out
    )


def test_the_nightly_pull_without_bao_fails_clearly_and_when_busy_skips(
    tmp_path, capsys, monkeypatch
):
    root = tmp_path / "data"
    link_account(root)
    assert cli.pull(cli_settings(root)) == 1  # no bao settings: Plaid unavailable
    assert "Plaid unavailable" in capsys.readouterr().out
    monkeypatch.setattr(
        "server.cli.PlaidKeys",
        lambda bao: type(
            "K", (), {"get": lambda self: {"client_id": "i", "secret": "s"}}
        )(),
    )
    store = Stores(root).get("me")
    with store.exclusive("pull"):
        assert (
            cli.pull(cli_settings(root), client_factory=lambda keys: FakePlaid()) == 0
        )
    assert "already running; skipped" in capsys.readouterr().out
