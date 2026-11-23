import json
from pathlib import Path

import pytest
from fake_bao import ADDR, PASSWORD, WRITER, FakeBao
from fastapi.testclient import TestClient
from fetcher import vault as v
from fetcher import web

ORIGIN = "https://fetch.test"
ME = {"X-Email": "me@example.com"}
POST = {**ME, "Origin": ORIGIN, "Content-Type": "application/json"}
SEED = "JBSWY3DPEHPK3PXP"


@pytest.fixture
def bao():
    b = FakeBao()
    b.kv["venmo-dragos"] = b.kv.pop("venmo")  # the account is a key like venmo-dragos
    b.totp = {"venmo-dragos"}
    return b


@pytest.fixture
def audit(tmp_path):
    return tmp_path / "audit.log"


def make_client(bao, audit, **kw):
    settings = web.Settings(
        trusted_proxies=kw.pop("trusted", frozenset({"testclient"})),
        allowed_emails=frozenset({"me@example.com"}),
        public_origin=ORIGIN,
        audit_log=str(audit),
        **kw,
    )
    app = web.create_app(settings, v.Vault(ADDR, "", "", bao, token=WRITER))
    return TestClient(app)


@pytest.fixture
def client(bao, audit):
    return make_client(bao, audit)


def test_only_the_login_proxy_and_the_allowed_email_get_in(bao, audit):
    c = make_client(bao, audit)
    assert c.get("/api/accounts").status_code == 401
    assert (
        c.get("/api/accounts", headers={"X-Email": "eve@example.com"}).status_code
        == 403
    )
    assert c.get("/", headers={"X-Email": "eve@example.com"}).status_code == 403
    assert c.get("/app.js").status_code == 401
    # the header is only believed from the proxy's address: anyone else on the LAN could send it
    stranger = make_client(bao, audit, trusted=frozenset({"192.168.1.232"}))
    assert stranger.get("/api/accounts", headers=ME).status_code == 403
    assert c.get("/api/accounts", headers=ME).status_code == 200
    assert c.get("/healthz").status_code == 200
    for method in (c.post, c.delete):  # every write path is behind the same checks
        path = "/api/accounts" if method == c.post else "/api/accounts/citi"
        assert (
            method(
                path, headers={"X-Email": "eve@example.com", "Origin": ORIGIN}
            ).status_code
            == 403
        )
        assert method(path).status_code == 401


def test_the_list_has_the_accounts_the_data_files_show_and_says_what_is_stored(
    client, bao
):
    body = client.get("/api/accounts", headers=ME).json()
    assert body["email"] == "me@example.com"
    by = {a["key"]: a for a in body["accounts"]}
    assert list(by) == [
        "venmo-dragos",
        "venmo-viral",
        "wealthfront-dragos",
        "barclays-viral",
        "citi",
        "fidelity-dragos",
    ]
    assert by["venmo-dragos"]["stored"] is True and by["venmo-dragos"]["totp"] is True
    assert by["venmo-dragos"]["saved_at"] == "2026-11-22T17:03:00Z"
    assert (
        by["venmo-dragos"]["label"] == "Venmo · dragos"
        and by["citi"]["label"] == "Citi credit card"
    )
    assert by["venmo-viral"]["stored"] is False and by["venmo-viral"]["totp"] is False
    assert {i["id"] for i in body["institutions"]} == {
        "venmo",
        "wealthfront",
        "fidelity",
        "barclays",
        "citi",
    }
    text = json.dumps(body)
    assert PASSWORD not in text and "someone@example.com" not in text
    # the list is kept in bao after first use, so the nightly job can read it too
    assert [a["key"] for a in bao.registry["accounts"]] == list(by)


def test_saving_writes_to_bao_and_never_echoes_or_logs_the_secrets(client, bao, audit):
    r = client.post(
        "/api/accounts/wealthfront-dragos/credentials",
        headers=POST,
        content=json.dumps(
            {
                "username": "me-wf",
                "password": "pw-wf-123",
                "totp_seed": "JBSW Y3DP EHPK 3PXP",
            }
        ),
    )
    assert (
        r.status_code == 200 and r.json()["stored"] is True and r.json()["totp"] is True
    )
    assert bao.kv["wealthfront-dragos"] == {
        "username": "me-wf",
        "password": "pw-wf-123",
    }
    for secret in ("pw-wf-123", "me-wf", SEED, "JBSW"):
        assert secret not in r.text
    line = json.loads(audit.read_text().strip())
    assert (line["who"], line["action"], line["account"], line["ok"]) == (
        "me@example.com",
        "save-credentials",
        "wealthfront-dragos",
        True,
    )
    for secret in ("pw-wf-123", "me-wf", SEED):
        assert secret not in audit.read_text()


def test_a_cross_site_or_form_post_is_refused_and_stores_nothing(client, bao):
    body = json.dumps({"username": "u", "password": "p"})
    for headers, status in [
        ({**ME, "Content-Type": "application/json"}, 403),  # no Origin
        (
            {
                **ME,
                "Origin": "https://evil.example",
                "Content-Type": "application/json",
            },
            403,
        ),
        ({**ME, "Origin": ORIGIN, "Content-Type": "text/plain"}, 415),
        (
            {
                **ME,
                "Origin": ORIGIN,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            415,
        ),
    ]:
        r = client.post("/api/accounts/citi/credentials", headers=headers, content=body)
        assert r.status_code == status, headers
    assert "citi" in bao.kv and bao.kv["citi"] == {
        "username": "u"
    }  # unchanged seed data, nothing written


def test_unknown_accounts_and_invalid_fields_do_not_echo_the_input(client, bao):
    assert (
        client.post(
            "/api/accounts/capital-one/credentials", headers=POST, content="{}"
        ).status_code
        == 404
    )
    huge = "x" * 2000
    r = client.post(
        "/api/accounts/citi/credentials",
        headers=POST,
        content=json.dumps({"username": "u", "password": huge}),
    )
    assert (
        r.status_code == 422 and "password" in r.json()["error"] and huge not in r.text
    )
    r = client.post(
        "/api/accounts/citi/credentials",
        headers=POST,
        content=json.dumps({"password": "topsecret-pw"}),
    )
    assert r.status_code == 422 and "topsecret-pw" not in r.text


def test_a_bao_refusal_is_reported_without_the_typed_values_and_audited(
    client, bao, audit
):
    r = client.post(
        "/api/accounts/fidelity-dragos/credentials",
        headers=POST,
        content=json.dumps(
            {"username": "fid-user", "password": "fid-pass-9", "totp_seed": "ABC"}
        ),
    )
    assert r.status_code == 502 and "HTTP 400" in r.json()["error"]
    for secret in ("fid-user", "fid-pass-9", "ABC"):
        assert secret not in r.text and secret not in audit.read_text()
    assert json.loads(audit.read_text().strip())["ok"] is False


def test_writes_are_rate_limited(bao, audit):
    c = make_client(bao, audit, writes_per_minute=2)
    ok = json.dumps({"username": "u", "password": "p"})
    assert [
        c.post("/api/accounts/citi/credentials", headers=POST, content=ok).status_code
        for _ in range(3)
    ] == [200, 200, 429]


def test_responses_are_not_cached_and_carry_a_strict_policy(client):
    for path in ("/", "/api/accounts", "/healthz"):
        r = client.get(path, headers=ME)
        assert r.headers["cache-control"] == "no-store"
        assert "default-src 'self'" in r.headers["content-security-policy"]
        assert r.headers["x-content-type-options"] == "nosniff"


def test_the_page_never_puts_server_text_into_html():
    js = Path(web.__file__).parent.joinpath("static/app.js").read_text()
    for banned in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
    ):
        assert banned not in js


def post_json(client, path, payload):
    return client.post(path, headers=POST, content=json.dumps(payload))


def test_adding_an_account_lists_it_and_lets_credentials_be_saved_for_it(
    client, bao, audit
):
    r = post_json(client, "/api/accounts", {"institution": "venmo", "owner": "Hemangi"})
    assert r.status_code == 200 and r.json()["account"] == {
        "key": "venmo-hemangi",
        "institution": "venmo",
        "owner": "hemangi",
        "label": "Venmo · hemangi",
    }
    keys = [
        a["key"] for a in client.get("/api/accounts", headers=ME).json()["accounts"]
    ]
    assert keys[-1] == "venmo-hemangi" and keys.count("venmo-dragos") == 1
    ok = post_json(
        client,
        "/api/accounts/venmo-hemangi/credentials",
        {"username": "h", "password": "p"},
    )
    assert ok.status_code == 200 and bao.kv["venmo-hemangi"] == {
        "username": "h",
        "password": "p",
    }
    assert any(
        json.loads(line)["action"] == "add-account"
        for line in audit.read_text().splitlines()
    )


def test_bad_or_duplicate_accounts_are_refused(client, bao):
    before = json.dumps(client.get("/api/accounts", headers=ME).json()["accounts"])
    for payload, status in [
        ({"institution": "paypal", "owner": "x"}, 422),  # not an institution we know
        ({"institution": "venmo", "owner": "../etc"}, 422),  # cannot name another path
        ({"institution": "venmo", "owner": "Has Space"}, 422),
        ({"institution": "venmo", "owner": "x" * 25}, 422),
        ({"institution": "venmo", "owner": "dragos"}, 409),  # already there
        ({"institution": "citi", "owner": ""}, 409),
        ({"institution": "citi"}, 409),
    ]:
        assert post_json(client, "/api/accounts", payload).status_code == status, (
            payload
        )
    assert (
        json.dumps(client.get("/api/accounts", headers=ME).json()["accounts"]) == before
    )


def test_removing_takes_it_off_the_list_and_keeps_its_credentials(client, bao, audit):
    client.get("/api/accounts", headers=ME)
    r = client.delete("/api/accounts/venmo-dragos", headers={**ME, "Origin": ORIGIN})
    assert r.status_code == 200
    keys = [
        a["key"] for a in client.get("/api/accounts", headers=ME).json()["accounts"]
    ]
    assert "venmo-dragos" not in keys and "venmo-viral" in keys
    assert (
        bao.kv["venmo-dragos"]["password"] == PASSWORD
    )  # nothing is deleted from the vault
    # no longer listed, so nothing can be saved for it
    assert (
        post_json(
            client,
            "/api/accounts/venmo-dragos/credentials",
            {"username": "u", "password": "p"},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            "/api/accounts/venmo-dragos", headers={**ME, "Origin": ORIGIN}
        ).status_code
        == 404
    )
    # re-adding finds the stored credentials again
    post_json(client, "/api/accounts", {"institution": "venmo", "owner": "dragos"})
    assert {
        a["key"]: a for a in client.get("/api/accounts", headers=ME).json()["accounts"]
    }["venmo-dragos"]["stored"] is True


def test_deleting_needs_the_sites_own_origin(client, bao):
    client.get("/api/accounts", headers=ME)
    assert client.delete("/api/accounts/citi", headers=ME).status_code == 403
    assert (
        client.delete(
            "/api/accounts/citi", headers={**ME, "Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert "citi" in [
        a["key"] for a in client.get("/api/accounts", headers=ME).json()["accounts"]
    ]


def test_a_hand_edited_list_cannot_name_an_arbitrary_path(client, bao):
    bao.registry = {
        "accounts": [
            {"institution": "venmo", "owner": "../../x"},
            {"institution": "nope"},
            "junk",
            {"institution": "citi"},
        ]
    }
    keys = [
        a["key"] for a in client.get("/api/accounts", headers=ME).json()["accounts"]
    ]
    assert keys == ["citi"]


def test_adding_an_account_needs_the_sites_own_origin_and_json(client, bao):
    body = json.dumps({"institution": "venmo", "owner": "mallory"})
    for headers, status in [
        ({**ME, "Content-Type": "application/json"}, 403),  # no Origin
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
            client.post("/api/accounts", headers=headers, content=body).status_code
            == status
        ), headers
    keys = [
        a["key"] for a in client.get("/api/accounts", headers=ME).json()["accounts"]
    ]
    assert "venmo-mallory" not in keys
