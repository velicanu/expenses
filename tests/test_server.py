import json
import shutil
import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.settings import Settings

SAMPLES = Path(__file__).resolve().parent.parent / "sample-data"
ME = {"X-Email": "me@example.com"}
OTHER = {"X-Email": "other@example.com"}


def make_settings(root, **kw):
    base = {
        "data_root": root,
        "users": {"me@example.com": "me", "other@example.com": "other"},
        "trusted_proxies": frozenset(
            {"testclient"}
        ),  # what TestClient reports as the peer
    }
    return Settings(**{**base, **kw})


@pytest.fixture
def root(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def client(root):
    root.mkdir()
    return TestClient(create_app(make_settings(root)))


@pytest.fixture
def loaded(client, root):
    """The sample CSVs uploaded for user `me`, pipeline run."""
    files = [
        ("files", (p.name, p.read_bytes(), "text/csv"))
        for p in sorted(SAMPLES.glob("*.csv"))
    ]
    r = client.post("/api/files", files=files, headers=ME)
    assert r.status_code == 200 and not r.json()["failed"], r.text
    return client


def rows(client, headers=ME, **params):
    r = client.get("/api/transactions", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- who is calling ----------------------------------------------------------------------------------


def test_no_login_header_is_401(client):
    assert client.get("/api/me").status_code == 401


def test_unknown_email_is_403(client):
    assert (
        client.get("/api/me", headers={"X-Email": "stranger@example.com"}).status_code
        == 403
    )


def test_known_email_maps_to_its_user_case_insensitively(client):
    r = client.get("/api/me", headers={"X-Email": "  Me@Example.com "})
    assert r.json() == {"user": "me", "email": "me@example.com"}


def test_the_header_is_ignored_unless_the_peer_is_the_proxy(root):
    root.mkdir()
    app = create_app(make_settings(root, trusted_proxies=frozenset({"10.0.0.1"})))
    r = TestClient(app).get("/api/me", headers={**ME, "X-Forwarded-For": "10.0.0.1"})
    assert r.status_code == 403


def test_dev_user_skips_the_login(root):
    root.mkdir()
    app = create_app(
        make_settings(root, dev_user="dev", users={}, trusted_proxies=frozenset())
    )
    assert TestClient(app).get("/api/me").json()["user"] == "dev"


@pytest.mark.parametrize("bad", ["../etc", "A", "a/b", "", "x" * 40])
def test_user_names_must_be_plain(root, bad):
    with pytest.raises(ValueError):
        Settings(
            data_root=root, users={"a@example.com": bad}, trusted_proxies=frozenset()
        )


def test_settings_from_env(tmp_path):
    users = tmp_path / "users.json"
    users.write_text(json.dumps({"A@Example.com": "a"}))
    s = Settings.from_env(
        {
            "DATA_ROOT": str(tmp_path),
            "USERS_FILE": str(users),
            "TRUSTED_PROXIES": "1.1.1.1, 2.2.2.2",
        }
    )
    assert s.users == {"a@example.com": "a"} and s.trusted_proxies == {
        "1.1.1.1",
        "2.2.2.2",
    }
    assert s.bao is None


def test_users_do_not_see_each_others_data(loaded):
    assert rows(loaded)["total"] == 9
    assert rows(loaded, headers=OTHER)["total"] == 0
    assert loaded.get("/api/files", headers=OTHER).json() == []


# --- reading -----------------------------------------------------------------------------------------


def test_empty_user_reads_cleanly(client):
    assert rows(client)["rows"] == []
    meta = client.get("/api/meta", headers=ME).json()
    assert meta["count"] == 0 and meta["min_date"] is None
    assert client.get("/api/summary/over-time", headers=ME).json()["periods"] == []


def test_meta(loaded):
    meta = loaded.get("/api/meta", headers=ME).json()
    assert (meta["count"], meta["min_date"], meta["max_date"]) == (
        9,
        "2018-12-18",
        "2020-06-19",
    )
    assert {"Dining", "Groceries", "Shopping", "Rent"} <= set(meta["categories"])
    assert meta["colors"]["Rent"].startswith("#") and meta["plaid_configured"] is False
    assert "amex.csv" in meta["sources"]


def test_filters(loaded):
    assert rows(loaded, category_in="Groceries")["total"] == 3
    assert rows(loaded, category_not_in="Groceries")["total"] == 6
    assert rows(loaded, source="amex.csv")["total"] == 3
    # the end day is included
    assert rows(loaded, start="2019-06-15", end="2019-06-15")["total"] == 1
    assert rows(loaded, start="2020-01-01")["total"] == 2


def test_description_expressions(loaded):
    assert [r["description"] for r in rows(loaded, q="rei #80")["rows"]] == [
        "REI #80 BOSTON BOSTON MA"
    ]
    assert rows(loaded, q="rei+whole")["total"] >= rows(loaded, q="rei")["total"]
    assert rows(loaded, q="rei^zzzz")["total"] == 0
    assert rows(loaded, q="!rei")["total"] == 8
    assert rows(loaded, q="rei*boston")["total"] == 1


def test_description_cannot_inject_or_mix_operators(loaded):
    assert rows(loaded, q="' OR 1=1 --")["total"] == 0
    assert rows(loaded, q='"; DROP TABLE expenses; --')["total"] == 0
    assert rows(loaded)["total"] == 9
    assert (
        loaded.get("/api/transactions", params={"q": "a+b^c"}, headers=ME).status_code
        == 422
    )


def test_sorting_and_paging(loaded):
    asc = rows(loaded, sort="date", order="asc")["rows"]
    assert [r["date"] for r in asc] == sorted(r["date"] for r in asc)
    assert (
        rows(loaded, limit=2, offset=1)["rows"]
        == rows(loaded, sort="date", order="desc")["rows"][1:3]
    )
    assert (
        loaded.get(
            "/api/transactions", params={"sort": "pk; DROP"}, headers=ME
        ).status_code
        == 422
    )
    assert (
        loaded.get("/api/transactions", params={"limit": 5000}, headers=ME).status_code
        == 422
    )


def test_summaries_add_up(loaded):
    total = rows(loaded)["sum"]
    by_cat = loaded.get("/api/summary/by-category", headers=ME).json()
    assert by_cat["total"] == total
    assert round(sum(c["amount"] for c in by_cat["categories"]), 2) == total
    series = loaded.get(
        "/api/summary/over-time", params={"bin": "year"}, headers=ME
    ).json()
    assert series["bin"] == "year"
    assert round(sum(p["total"] for p in series["periods"]), 2) == total
    assert (
        loaded.get(
            "/api/summary/over-time", params={"bin": "decade"}, headers=ME
        ).status_code
        == 422
    )
    # filters apply to summaries too
    only = loaded.get(
        "/api/summary/by-category", params={"category_in": "Groceries"}, headers=ME
    ).json()
    assert [c["category"] for c in only["categories"]] == ["Groceries"]


# --- editing -----------------------------------------------------------------------------------------


def test_edit_a_transaction_and_it_survives_a_pipeline_rerun(loaded):
    pk = rows(loaded, q="rei #80")["rows"][0]["pk"]
    r = loaded.patch(
        f"/api/transactions/{pk}",
        json={"category": "Family", "amount": -10.5},
        headers=ME,
    )
    assert r.status_code == 200
    row = rows(loaded, q="rei #80")["rows"][0]
    assert (row["category"], row["amount"], row["edited"]) == ("Family", -10.5, True)
    assert loaded.post("/api/pipeline/run", json={}, headers=ME).json()["ran"] is True
    assert rows(loaded, q="rei #80")["rows"][0]["category"] == "Family"
    assert rows(loaded)["total"] == 9


def test_edit_the_date(loaded):
    pk = rows(loaded, q="rei #80")["rows"][0]["pk"]
    loaded.patch(f"/api/transactions/{pk}", json={"date": "2021-02-03"}, headers=ME)
    assert rows(loaded, q="rei #80")["rows"][0]["date"] == "2021-02-03"
    assert rows(loaded, start="2021-01-01")["total"] == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"amount": "lots"},
        {"category": ""},
        {"date": "tomorrow"},
        {"pk": "x"},
        {"amount": float("inf")},
    ],
)
def test_bad_edits_are_422(loaded, body):
    pk = rows(loaded)["rows"][0]["pk"]
    r = loaded.patch(
        f"/api/transactions/{pk}",
        content=json.dumps(body),
        headers={**ME, "Content-Type": "application/json"},
    )
    assert r.status_code == 422


def test_editing_an_unknown_transaction_is_404(loaded):
    assert (
        loaded.patch(
            "/api/transactions/nope-1", json={"category": "Dining"}, headers=ME
        ).status_code
        == 404
    )


def test_edit_cannot_reach_other_columns_or_inject(loaded, root):
    pk = rows(loaded)["rows"][0]["pk"]
    loaded.patch(
        f"/api/transactions/{pk}",
        json={"description": "x'); DROP TABLE expenses; --"},
        headers=ME,
    )
    assert rows(loaded)["total"] == 9
    with sqlite3.connect(root / "me" / "changes.db") as conn:
        assert conn.execute("SELECT count(*) FROM expenses").fetchone()[0] == 1


def test_add_transactions_numbers_them_and_validates(loaded):
    body = {
        "date": "2024-05-01",
        "description": "cash",
        "amount": -12.0,
        "category": "Dining",
    }
    assert loaded.post("/api/transactions", json=body, headers=ME).json() == {
        "pk": "input-0"
    }
    assert loaded.post("/api/transactions", json=body, headers=ME).json() == {
        "pk": "input-1"
    }
    assert rows(loaded)["total"] == 11
    assert rows(loaded, source="input.csv")["total"] == 0
    assert (
        loaded.post(
            "/api/transactions", json={**body, "amount": 0}, headers=ME
        ).status_code
        == 422
    )
    assert (
        loaded.post(
            "/api/transactions", json={**body, "extra": 1}, headers=ME
        ).status_code
        == 422
    )


def test_adding_before_any_data_is_a_clear_409(client):
    body = {
        "date": "2024-05-01",
        "description": "cash",
        "amount": -12.0,
        "category": "Dining",
    }
    assert client.post("/api/transactions", json=body, headers=ME).status_code == 409


def test_delete_hides_the_transaction_and_a_rerun_keeps_it_hidden(loaded):
    pk = rows(loaded, q="rei #80")["rows"][0]["pk"]
    assert loaded.delete(f"/api/transactions/{pk}", headers=ME).status_code == 204
    assert rows(loaded)["total"] == 8
    loaded.post("/api/pipeline/run", json={}, headers=ME)
    assert rows(loaded)["total"] == 8
    assert loaded.delete("/api/transactions/nope", headers=ME).status_code == 404


# --- rules -------------------------------------------------------------------------------------------


def test_rules_roundtrip_and_apply(loaded):
    assert loaded.get("/api/rules", headers=ME).json() == {
        "description": {},
        "category": {},
        "new_categories": {},
    }
    new = {
        "description": {"rei": "Hobbies"},
        "category": {},
        "new_categories": {"Hobbies": "#12ab34"},
    }
    assert loaded.put("/api/rules", json=new, headers=ME).json() == new
    assert (
        rows(loaded, q="rei #80")["rows"][0]["category"] == "Shopping"
    )  # saved, not applied yet
    assert (
        loaded.post("/api/pipeline/run", json={"rules_only": True}, headers=ME).json()[
            "ran"
        ]
        is True
    )
    assert rows(loaded, q="rei #80")["rows"][0]["category"] == "Hobbies"
    meta = loaded.get("/api/meta", headers=ME).json()
    assert "Hobbies" in meta["categories"] and meta["colors"]["Hobbies"] == "#12ab34"


@pytest.mark.parametrize(
    "bad",
    [
        {"new_categories": {"X": "red"}},
        {"description": {"": "A"}},
        {"category": {"a": "b" * 65}},
        {"bogus": {}},
    ],
)
def test_bad_rules_are_422(client, bad):
    assert client.put("/api/rules", json=bad, headers=ME).status_code == 422


def test_saving_rules_keeps_the_rest_of_config_json(client, root):
    (root / "me").mkdir()
    (root / "me" / "config.json").write_text(
        json.dumps({"linked_accounts": {"c": {"token": "t"}}, "min_date": "x"})
    )
    client.put("/api/rules", json={"description": {"a": "B"}}, headers=ME)
    cfg = json.loads((root / "me" / "config.json").read_text())
    assert cfg["linked_accounts"] == {"c": {"token": "t"}} and cfg["min_date"] == "x"
    assert cfg["rules"]["description"] == {"a": "B"}


# --- files and the pipeline --------------------------------------------------------------------------


def test_upload_keeps_known_cards_and_reports_the_rest(client, root):
    good = ("files", ("chase.csv", (SAMPLES / "chase.csv").read_bytes(), "text/csv"))
    junk = ("files", ("notes.csv", b"a,b\n1,2\n", "text/csv"))
    wrong = ("files", ("evil.txt", b"x", "text/plain"))
    r = client.post("/api/files", files=[good, junk, wrong], headers=ME).json()
    assert len(r["saved"]) == 1 and len(r["failed"]) == 2
    assert any(f.startswith("notes.csv") and "known card" in f for f in r["failed"])
    assert any(f.startswith("evil.txt") and ".csv" in f for f in r["failed"])
    assert r["pipeline"]["ran"] is True
    assert [f["name"] for f in client.get("/api/files", headers=ME).json()] == [
        "chase.csv"
    ]


def test_upload_filenames_cannot_escape_the_raw_directory(client, root):
    data = (SAMPLES / "chase.csv").read_bytes()
    client.post(
        "/api/files",
        files=[("files", ("../../escape.csv", data, "text/csv"))],
        headers=ME,
    )
    assert (
        not (root / "escape.csv").exists() and not (root / "me" / "escape.csv").exists()
    )
    assert [p.name for p in (root / "me" / "raw").iterdir()] == ["escape.csv"]


def test_upload_over_the_limit_is_413(root):
    root.mkdir()
    c = TestClient(create_app(make_settings(root, max_upload_bytes=10)))
    r = c.post(
        "/api/files",
        files=[("files", ("chase.csv", b"x" * 11, "text/csv"))],
        headers=ME,
    )
    assert r.status_code == 413


def test_delete_a_raw_file_and_rerun(loaded, root):
    assert loaded.delete("/api/files/chase.csv", headers=ME).status_code == 204
    assert not (root / "me" / "raw" / "chase.csv").exists()
    loaded.post("/api/pipeline/run", json={}, headers=ME)
    assert rows(loaded)["total"] < 9
    assert loaded.delete("/api/files/chase.csv", headers=ME).status_code == 404
    assert loaded.delete(
        "/api/files/..%2F..%2Fconfig.json", headers=ME
    ).status_code in (404, 405)


def test_running_pipeline_with_nothing_uploaded_says_so(client):
    assert client.post("/api/pipeline/run", json={}, headers=ME).json()["ran"] is False


def test_a_second_pipeline_run_while_one_is_going_is_409(loaded):
    store = loaded.app.state.stores.get("me")
    assert store._pipeline_lock.acquire(blocking=False)
    try:
        assert loaded.post("/api/pipeline/run", json={}, headers=ME).status_code == 409
    finally:
        store._pipeline_lock.release()


def test_expenses_db_is_swapped_atomically_and_failures_keep_the_old_one(
    loaded, root, monkeypatch
):
    from ingest import ingest

    db = root / "me" / "expenses.db"
    before = db.read_bytes()
    with pytest.raises((OSError, ValueError)):
        ingest([str(root / "nope.json")], "expenses", str(db))
    assert db.read_bytes() == before and not Path(str(db) + ".tmp").exists()
    loaded.post("/api/pipeline/run", json={}, headers=ME)
    assert not Path(str(db) + ".tmp").exists()


# --- browser safety ----------------------------------------------------------------------------------


def test_cross_site_writes_are_refused_and_same_site_ones_work(loaded):
    body = {"rules_only": True}
    evil = {**ME, "Origin": "https://evil.example"}
    assert loaded.post("/api/pipeline/run", json=body, headers=evil).status_code == 403
    same = {**ME, "Origin": "http://testserver"}
    assert loaded.post("/api/pipeline/run", json=body, headers=same).status_code == 200


def test_security_headers(loaded):
    r = loaded.get("/api/me", headers=ME)
    assert (
        r.headers["x-content-type-options"] == "nosniff"
        and r.headers["cache-control"] == "no-store"
    )
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_the_web_app_is_served_from_static_dir(root, tmp_path):
    root.mkdir()
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<h1>hi</h1>")
    c = TestClient(create_app(make_settings(root, static_dir=web)))
    assert "<h1>hi</h1>" in c.get("/").text
    assert c.get("/api/me").status_code == 401  # the API is still behind the login
    (web / "assets").mkdir()
    (web / "assets" / "app-abc123.js").write_text("x")
    assert "immutable" in c.get("/assets/app-abc123.js").headers["cache-control"]
    assert "immutable" not in c.get("/").headers.get("cache-control", "")


# --- Plaid -------------------------------------------------------------------------------------------


def link(root, **extra):
    (root / "me").mkdir(parents=True, exist_ok=True)
    cfg = {
        "linked_accounts": {
            "card": {
                "alias": "card",
                "institution": "Bank",
                "start_date": "2024-01-01",
                "token": "ACCESS-SECRET",
                **extra,
            }
        }
    }
    (root / "me" / "config.json").write_text(json.dumps(cfg))


def test_accounts_never_expose_the_access_token(client, root):
    link(root)
    r = client.get("/api/accounts", headers=ME)
    assert r.json() == [
        {"alias": "card", "institution": "Bank", "start_date": "2024-01-01"}
    ]
    assert (
        "ACCESS-SECRET" not in r.text
        and "ACCESS-SECRET" not in client.get("/api/meta", headers=ME).text
    )


def test_pull_without_bao_is_503_and_leaks_nothing(client, root):
    link(root)
    r = client.post("/api/accounts/pull", headers=ME)
    assert r.status_code == 503 and "ACCESS-SECRET" not in r.text


class FakeTx:
    def __init__(self, i):
        self.i = i

    def to_dict(self):
        from datetime import date

        return {
            "transaction_id": f"t{self.i}",
            "category": ["Food"],
            "name": f"SHOP {self.i}",
            "amount": 1.5,
            "date": date(2024, 3, 1),
            "authorized_date": None,
        }


class FakePlaid:
    def __init__(self, total):
        self.total = total
        self.offsets = []

    def transactions_get(self, request):
        offset = request.options.offset
        self.offsets.append(offset)
        return {
            "transactions": [
                FakeTx(i) for i in range(offset, min(offset + 500, self.total))
            ],
            "total_transactions": self.total,
        }


def test_pull_pages_through_every_transaction_and_rebuilds(client, root):
    from datetime import date

    from server.plaid_pull import pull_all

    link(root)
    plaid = FakePlaid(total=1203)
    keys = type("K", (), {"get": lambda self: {"client_id": "i", "secret": "s"}})()
    out = pull_all(
        client.app.state.stores.get("me"),
        keys,
        client_factory=lambda k: plaid,
        today=lambda: date(2024, 6, 1),
    )
    assert plaid.offsets == [
        0,
        500,
        1000,
    ]  # the Streamlit version stopped after the first page
    assert out["accounts"] == [{"alias": "card", "pulled": 1203}]
    assert out["pipeline"]["ran"] is True
    cfg = json.loads((root / "me" / "config.json").read_text())
    assert cfg["linked_accounts"]["card"]["start_date"] == "2024-05-02"
    assert rows(client)["total"] == 1203 or rows(client)["total"] > 0


def test_one_failing_account_does_not_stop_the_others(client, root):
    from datetime import date

    from server.plaid_pull import pull_all

    link(root)

    class Broken:
        def transactions_get(self, request):
            raise RuntimeError("boom ACCESS-SECRET")

    keys = type("K", (), {"get": lambda self: {"client_id": "i", "secret": "s"}})()
    out = pull_all(
        client.app.state.stores.get("me"),
        keys,
        client_factory=lambda k: Broken(),
        today=lambda: date(2024, 6, 1),
    )
    assert out["accounts"] == [{"alias": "card", "error": "RuntimeError"}]
    assert out["pipeline"] is None and "ACCESS-SECRET" not in json.dumps(out)


# --- bao ---------------------------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, *a):
        return json.dumps(self.payload).encode()


def test_plaid_keys_login_then_read_and_cache():
    from server.bao import PlaidKeys
    from server.settings import BaoSettings

    calls = []

    def opener(req, timeout):
        calls.append((req.full_url, req.get_header("X-vault-token")))
        if req.full_url.endswith("/v1/auth/approle/login"):
            assert json.loads(req.data) == {"role_id": "r", "secret_id": "s"}
            return FakeResponse({"auth": {"client_token": "tok"}})
        return FakeResponse({"data": {"data": {"client_id": "cid", "secret": "sec"}}})

    keys = PlaidKeys(
        BaoSettings("http://bao", "r", "s", "kv/data/expenses/plaid"), opener=opener
    )
    assert keys.get() == {"client_id": "cid", "secret": "sec"}
    assert keys.get() == {"client_id": "cid", "secret": "sec"}
    assert calls == [
        ("http://bao/v1/auth/approle/login", None),
        ("http://bao/v1/kv/data/expenses/plaid", "tok"),
    ]


def test_plaid_keys_failure_is_unavailable_and_does_not_echo_the_response():
    import urllib.error

    from server.bao import PlaidKeys, PlaidUnavailable
    from server.settings import BaoSettings

    def opener(req, timeout):
        raise urllib.error.URLError("connection refused: s.SECRET-TOKEN")

    keys = PlaidKeys(BaoSettings("http://bao", "r", "s", "p"), opener=opener)
    with pytest.raises(PlaidUnavailable) as e:
        keys.get()
    assert "SECRET-TOKEN" not in str(e.value)
    with pytest.raises(PlaidUnavailable):
        PlaidKeys(None).get()


def test_concurrent_edits_do_not_lose_rows(loaded):
    body = {
        "date": "2024-05-01",
        "description": "x",
        "amount": -1.0,
        "category": "Dining",
    }
    errors = []

    def add():
        try:
            assert (
                loaded.post("/api/transactions", json=body, headers=ME).status_code
                == 201
            )
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=add) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and rows(loaded)["total"] == 17
    pks = [r["pk"] for r in rows(loaded, limit=500)["rows"] if r["source"] == "input"]
    assert sorted(pks) == sorted(
        f"input-{i}" for i in range(8)
    )  # eight rows, eight distinct numbers


def test_amounts_survive_a_roundtrip_to_the_cent(loaded):
    pk = rows(loaded)["rows"][0]["pk"]
    loaded.patch(f"/api/transactions/{pk}", json={"amount": 1234.56}, headers=ME)
    assert [r["amount"] for r in rows(loaded)["rows"] if r["pk"] == pk] == [1234.56]


def _other_filesystem(like: Path):
    """A directory on a different filesystem from `like` (a container's /tmp tmpfs vs the data volume),
    or None where there is no such thing (then the test is skipped)."""
    for candidate in ("/dev/shm", "/run/user", "/tmp"):
        p = Path(candidate)
        if p.is_dir() and p.stat().st_dev != like.stat().st_dev:
            return p
    return None


def test_upload_and_pipeline_work_when_the_temp_dir_is_on_another_filesystem(
    root, tmp_path, monkeypatch
):
    """In the container /tmp is a tmpfs and the data is a bind mount: os.replace between them is EXDEV."""
    root.mkdir()
    other = _other_filesystem(root)
    if other is None:
        pytest.skip("no second filesystem to test with")
    scratch = other / f"expenses-test-{tmp_path.name}"
    scratch.mkdir()
    try:
        monkeypatch.setattr("tempfile.tempdir", str(scratch))
        c = TestClient(create_app(make_settings(root)))
        files = [
            ("files", (p.name, p.read_bytes(), "text/csv"))
            for p in sorted(SAMPLES.glob("*.csv"))
        ]
        r = c.post("/api/files", files=files, headers=ME)
        assert r.status_code == 200 and not r.json()["failed"], r.text
        assert r.json()["pipeline"]["count"] == 9
        assert c.post("/api/pipeline/run", json={}, headers=ME).json()["ran"] is True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# --- the old sidebar's saved state, its SQL box, and its charts ---------------------------------------


def test_state_roundtrip_uses_the_old_config_keys_and_keeps_the_rest(client, root):
    (root / "me").mkdir()
    (root / "me" / "config.json").write_text(
        json.dumps(
            {
                "linked_accounts": {"c": {"token": "t"}},
                "show_sql": True,
                "min_date": "2026-01-01",
            }
        )
    )
    assert client.get("/api/state", headers=ME).json() == {
        "min_date": "2026-01-01",
        "max_date": None,
        "categories_in": [],
        "categories_not_in": [],
        "show_sql": True,
        "rules_button": False,
    }
    body = {
        "max_date": "2026-06-26",
        "categories_not_in": ["Transfer", "Income"],
        "rules_button": True,
    }
    out = client.put("/api/state", json=body, headers=ME).json()
    assert out["max_date"] == "2026-06-26" and out["categories_not_in"] == [
        "Transfer",
        "Income",
    ]
    assert (
        out["show_sql"] is True and out["min_date"] == "2026-01-01"
    )  # untouched keys stay
    cfg = json.loads((root / "me" / "config.json").read_text())
    # the keys the Streamlit app used, so both UIs read each other's state
    assert (
        cfg["categories not in"] == ["Transfer", "Income"]
        and cfg["max_date"] == "2026-06-26"
    )
    assert cfg["rules_button"] is True and cfg["linked_accounts"] == {
        "c": {"token": "t"}
    }
    cleared = client.put("/api/state", json={"min_date": None}, headers=ME).json()
    assert cleared["min_date"] is None


@pytest.mark.parametrize(
    "bad",
    [
        {"min_date": "soon"},
        {"bogus": 1},
        {"categories_in": [""]},
        {"show_sql": "maybe"},
    ],
)
def test_bad_state_is_422(client, bad):
    assert client.put("/api/state", json=bad, headers=ME).status_code == 422


def test_meta_lists_the_categories_present_in_the_data(loaded):
    meta = loaded.get("/api/meta", headers=ME).json()
    assert meta["data_categories"] == sorted(meta["data_categories"])
    assert set(meta["data_categories"]) <= set(meta["categories"])
    assert (
        "Rent" in meta["categories"] and "Rent" not in meta["data_categories"]
    )  # a default, not in this data


def test_default_sql_is_what_the_old_sidebar_built(loaded):
    body = {
        "start": "2019-06-16",
        "end": "2020-06-18",
        "category_not_in": ["Dining"],
        "description": "kohl*",
    }
    out = loaded.post("/api/sql/default", json=body, headers=ME).json()
    assert out == {
        "query": (
            'SELECT * FROM expenses WHERE date >= "2019-06-16" AND date <= "2020-06-18" '
            "AND category not in ('Dining') AND description LIKE '%kohl%%'"
        ),
        "description_warning": None,
    }
    assert (
        loaded.post("/api/sql/default", json={}, headers=ME).json()["query"]
        == "SELECT * FROM expenses"
    )
    warn = loaded.post(
        "/api/sql/default", json={"description": "a+b^c"}, headers=ME
    ).json()
    assert "only one of + or ^" in warn["description_warning"]


def test_the_sql_box_runs_selects_over_the_data(loaded):
    out = loaded.post(
        "/api/sql/run",
        json={"query": "SELECT date, amount, pk FROM expenses ORDER BY pk LIMIT 3"},
        headers=ME,
    ).json()
    assert (
        out["columns"] == ["date", "amount", "pk"]
        and len(out["rows"]) == 3
        and out["count"] == 3
    )
    total = loaded.post(
        "/api/sql/run", json={"query": "SELECT * FROM expenses"}, headers=ME
    ).json()
    assert total["count"] == 9 and "pk" in total["columns"]


@pytest.mark.parametrize(
    "query",
    [
        "ATTACH DATABASE '/tmp/x.db' AS x",
        "PRAGMA table_info(expenses)",
        "DROP TABLE expenses",
        "DELETE FROM expenses",
        "INSERT INTO expenses(pk) VALUES ('x')",
        "SELECT 1; DROP TABLE expenses",
        "SELECT load_extension('x')",
        "",
        "SELEC nonsense",
    ],
)
def test_the_sql_box_is_read_only_and_errors_are_422(loaded, query):
    r = loaded.post("/api/sql/run", json={"query": query}, headers=ME)
    assert r.status_code == 422 and r.json()["detail"], query
    assert rows(loaded)["total"] == 9  # nothing happened to the data


def test_the_sql_box_cannot_write_files(loaded, tmp_path):
    target = tmp_path / "escaped.db"
    loaded.post(
        "/api/sql/run", json={"query": f"ATTACH DATABASE '{target}' AS x"}, headers=ME
    )
    assert not target.exists()


def test_a_runaway_query_is_stopped(loaded, monkeypatch):
    from server import sqlview

    monkeypatch.setattr(sqlview, "MAX_SECONDS", 0.2)
    slow = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 100000000) SELECT count(*) FROM c"
    r = loaded.post("/api/sql/run", json={"query": slow}, headers=ME)
    assert r.status_code == 422 and "longer than" in r.json()["detail"]


def test_figures_come_ready_made_for_a_query(loaded):
    out = loaded.post(
        "/api/figures",
        json={"query": "SELECT * FROM expenses", "group": "auto"},
        headers=ME,
    ).json()
    assert out["rows"] == 9
    cat, time = out["category"], out["over_time"]
    assert cat["message"] is None and cat["figure"]["data"][0]["type"] == "pie"
    assert (
        "Spending by category, total: 143.94"
        in cat["figure"]["layout"]["title"]["text"]
    )
    assert [r["category"] for r in cat["table"]] == [
        "Dining",
        "Groceries",
        "Other",
        "Shopping",
    ]
    assert time["figure"]["data"][0]["type"] == "bar" and time["group"] == "auto"
    yearly = loaded.post(
        "/api/figures",
        json={"query": "SELECT * FROM expenses", "group": "year"},
        headers=ME,
    ).json()
    assert yearly["over_time"]["figure"]["layout"]["title"]["text"] == "Yearly spending"


def test_figures_for_nothing_and_for_the_wrong_columns(loaded):
    empty = loaded.post(
        "/api/figures", json={"query": "SELECT * FROM expenses WHERE 1=0"}, headers=ME
    ).json()
    assert (
        empty["rows"] == 0
        and empty["category"]["figure"] is None
        and empty["over_time"]["figure"] is None
    )
    missing = loaded.post(
        "/api/figures", json={"query": "SELECT description FROM expenses"}, headers=ME
    ).json()
    assert missing["category"]["message"] == "Missing category or amount columns."
    assert missing["over_time"]["message"] == "Missing date or amount columns."


def test_figures_reject_unknown_bins_and_oversized_queries(loaded):
    assert (
        loaded.post(
            "/api/figures",
            json={"query": "SELECT * FROM expenses", "group": "decade"},
            headers=ME,
        ).status_code
        == 422
    )
    assert (
        loaded.post("/api/figures", json={"query": "x" * 6000}, headers=ME).status_code
        == 422
    )


def test_new_endpoints_need_the_login(client):
    for method, path, body in [
        ("get", "/api/state", None),
        ("put", "/api/state", {}),
        ("post", "/api/sql/default", {}),
        ("post", "/api/sql/run", {"query": "SELECT 1"}),
        ("post", "/api/figures", {"query": "SELECT 1"}),
    ]:
        r = getattr(client, method)(
            path, **({"json": body} if body is not None else {})
        )
        assert r.status_code == 401, path


def test_users_cannot_query_each_others_data(loaded):
    out = loaded.post(
        "/api/sql/run", json={"query": "SELECT * FROM expenses"}, headers=OTHER
    ).json()
    assert out["count"] == 0
