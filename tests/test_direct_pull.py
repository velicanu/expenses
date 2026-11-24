import csv
import io
import json
import urllib.error
from datetime import date

import pytest
from fastapi.testclient import TestClient

from server import direct_pull as dp
from server.app import create_app
from server.bao import PlaidUnavailable
from server.plaid_pull import pull_all
from server.settings import FetcherSettings, Settings
from server.store import UserStore

HEADER = dp.schema("venmo")
ME = {"X-Email": "me@example.com"}
TODAY = date(2026, 11, 22)
NOW = 1_800_000_000.0


def txn(tid, when, note="lunch", status="Complete", kind="Payment", amount="- $5.00"):
    row = [""] * len(HEADER)
    for col, value in {
        "ID": tid,
        "Datetime": when,
        "Type": kind,
        "Status": status,
        "Note": note,
        "From": "Some One",
        "To": "Another Person",
        "Amount (total)": amount,
        "Funding Source": "Venmo balance",
    }.items():
        row[HEADER.index(col)] = value
    return row


def statement(rows, preamble=True, summaries=True):
    """A monthly statement as Venmo exports it: two preamble lines, the header, a beginning-balance row, the
    transactions, then an ending-balance row whose disclaimer spans several lines."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    if preamble:
        out.write("Account Statement - (@someone) ," + "," * 20 + "\n")
        out.write("Account Activity," + "," * 20 + "\n")
    w.writerow(HEADER)
    if summaries:
        begin = [""] * len(HEADER)
        begin[HEADER.index("Beginning Balance")] = "$10.00"
        w.writerow(begin)
    w.writerows(rows)
    if summaries:
        end = [""] * len(HEADER)
        end[HEADER.index("Ending Balance")] = "$12.00"
        end[HEADER.index("Disclaimer")] = "In case of errors\nor questions, contact us."
        w.writerow(end)
    return out.getvalue()


def raw_file(rows):
    """The legacy raw layout: header on line 1, no preamble, no summaries."""
    return statement(rows, preamble=False, summaries=False)


@pytest.fixture
def store(tmp_path):
    s = UserStore(tmp_path / "me")
    s.raw_dir.mkdir(parents=True)
    return s


# --- reading a statement ------------------------------------------------------------------------------------------


def test_a_statement_loses_its_preamble_and_balance_rows(store):
    text = statement(
        [txn("1001", "2026-11-02T10:00:00"), txn("1002", "2026-11-03T11:00:00")]
    )
    header, rows = dp.parse_statement(text)
    assert header == HEADER
    assert [r[HEADER.index("ID")] for r in rows] == ["1001", "1002"]


def test_a_statement_that_is_not_the_known_layout_fails_loudly():
    with pytest.raises(dp.DirectPullError, match="not a Venmo statement"):
        dp.parse_statement("<html>please log in</html>")
    changed = statement([txn("1", "2026-11-02T10:00:00")]).replace(
        "Amount (total)", "Total"
    )
    with pytest.raises(dp.DirectPullError, match="changed the columns"):
        dp.parse_statement(changed)


# --- what is already known ----------------------------------------------------------------------------------------


def test_known_ids_come_from_the_accounts_own_statement_files_only(store):
    (store.raw_dir / "venmo-dragos-2024.csv").write_text(
        raw_file([txn("A1", "2025-12-30T09:00:00"), txn("A2", "2025-06-01T09:00:00")])
    )
    (store.raw_dir / "venmo-dragos.csv").write_text(
        "transaction_id,amount\nPLAID1,3\n"
    )  # another layout
    (store.raw_dir / "venmo-viral-2024.csv").write_text(
        raw_file([txn("V1", "2026-01-05T09:00:00")])
    )  # someone else's
    (store.raw_dir / "venmo-dragosx.csv").write_text(
        raw_file([txn("X1", "2026-02-02T09:00:00")])
    )  # a prefix lookalike
    ids, latest = dp.known(store.raw_dir, "venmo-dragos")
    assert ids == {"A1", "A2"} and latest == date(2025, 12, 30)
    assert dp.known(store.raw_dir, "venmo-nobody") == (set(), None)


# --- which months ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "latest,today,expected",
    [
        (
            None,
            date(2026, 11, 22),
            ["2025-12", *[f"2026-{m:02d}" for m in range(1, 12)]],
        ),  # nothing yet: the last 12
        (
            date(2026, 11, 20),
            date(2026, 11, 22),
            ["2026-10", "2026-11"],
        ),  # up to date: previous and current
        (date(2026, 11, 1), date(2026, 11, 22), ["2026-10", "2026-11"]),
        (date(2026, 10, 5), date(2026, 11, 22), ["2026-10", "2026-11"]),
        (
            date(2025, 12, 30),
            date(2026, 11, 22),
            ["2025-12", *[f"2026-{m:02d}" for m in range(1, 12)]],
        ),  # the gap to fill
        (
            date(2026, 11, 22),
            date(2027, 1, 3),
            ["2026-11", "2026-12", "2027-01"],
        ),  # across a year end
        (date(2026, 12, 31), date(2027, 1, 1), ["2026-12", "2027-01"]),
    ],
)
def test_months_to_fetch(latest, today, expected):
    assert dp.months_to_fetch(latest, today) == expected


def test_months_to_fetch_is_capped():
    months = dp.months_to_fetch(date(2015, 1, 1), date(2026, 11, 22))
    assert (
        len(months) == dp.MAX_MONTHS
        and months[-1] == "2026-11"
        and months[0] == "2024-12"
    )


# --- appending ---------------------------------------------------------------------------------------------------


def test_new_rows_go_to_a_file_of_their_own_oldest_first(store):
    (store.raw_dir / "venmo-dragos-2024.csv").write_text(
        raw_file([txn("A1", "2025-12-30T09:00:00")])
    )
    header, rows = dp.parse_statement(
        statement(
            [
                txn("B2", "2026-01-05T09:00:00"),
                txn("B1", "2026-01-02T09:00:00"),
                txn("A1", "2025-12-30T09:00:00"),
            ]
        )
    )
    assert (
        dp.append_new(store.raw_dir, "venmo-dragos", header, rows) == 2
    )  # A1 is already known
    text = (store.raw_dir / "venmo-dragos-direct.csv").read_text()
    assert [r[1] for r in csv.reader(io.StringIO(text))] == ["ID", "B1", "B2"]
    assert (store.raw_dir / "venmo-dragos-2024.csv").read_text() == raw_file(
        [txn("A1", "2025-12-30T09:00:00")]
    )  # untouched


def test_a_file_that_only_grows_keeps_every_earlier_line_exactly(store):
    header, first = dp.parse_statement(
        statement([txn("C1", "2026-02-01T09:00:00"), txn("C2", "2026-02-02T09:00:00")])
    )
    dp.append_new(store.raw_dir, "venmo-dragos", header, first)
    path = store.raw_dir / "venmo-dragos-direct.csv"
    before = path.read_bytes()
    header, more = dp.parse_statement(
        statement([txn("C2", "2026-02-02T09:00:00"), txn("C3", "2026-02-03T09:00:00")])
    )
    assert dp.append_new(store.raw_dir, "venmo-dragos", header, more) == 1
    after = path.read_bytes()
    assert after.startswith(before) and after[len(before) :].count(b"\n") == 1
    # a file whose last line lacks a newline (hand-edited) still gets the new row on its own line
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    header, latest = dp.parse_statement(statement([txn("C4", "2026-02-04T09:00:00")]))
    dp.append_new(store.raw_dir, "venmo-dragos", header, latest)
    assert [r[1] for r in csv.reader(io.StringIO(path.read_text()))] == [
        "ID",
        "C1",
        "C2",
        "C3",
        "C4",
    ]


def test_pending_and_repeated_rows_are_not_added_and_nothing_new_writes_nothing(store):
    header, rows = dp.parse_statement(
        statement(
            [
                txn("P1", "2026-03-01T09:00:00", status="Pending"),
                txn("P2", "2026-03-02T09:00:00"),
                txn("P2", "2026-03-02T09:00:00"),
            ]
        )
    )
    assert dp.append_new(store.raw_dir, "venmo-dragos", header, rows) == 1
    # the pending one arrives later, final; it is added then, once
    header, later = dp.parse_statement(
        statement([txn("P1", "2026-03-01T09:00:00", status="Complete")])
    )
    assert dp.append_new(store.raw_dir, "venmo-dragos", header, later) == 1
    assert dp.append_new(store.raw_dir, "venmo-dragos", header, later) == 0
    empty = store.raw_dir.parent / "empty"
    empty.mkdir()
    assert (
        dp.append_new(empty, "venmo-dragos", header, []) == 0
        and list(empty.iterdir()) == []
    )


# --- the whole thing through the real pipeline ------------------------------------------------------------------


def pks(store):
    return {r["pk"]: r for r in store.to_rows(store.expenses())}


def test_a_pull_keeps_every_existing_key_and_edit_and_adds_the_new_rows(store):
    legacy = [
        txn(f"L{i}", f"2025-12-{i:02d}T10:00:00", note=f"legacy {i}")
        for i in range(1, 6)
    ]
    (store.raw_dir / "venmo-dragos-2024.csv").write_text(raw_file(legacy))
    store.add_direct_account("venmo-dragos", "venmo")
    store.mark_direct_session(
        "venmo-dragos", NOW - 60
    )  # its login was seen working a minute ago
    store.run_pipeline()
    before = pks(store)
    assert len(before) == 5
    edited_pk = sorted(before)[2]
    store.update_transaction(edited_pk, {"category": "My Own Category"})

    class Browser:
        login_url = "https://fetch.test"

        def __init__(self):
            self.asked = []

        def login_link(self, account):
            return f"{self.login_url}/login?account={account}"

        def fetch(self, account, months, autologin=False):
            self.asked.append((account, months))
            return {
                "state": "logged_in",
                "files": [
                    {
                        "month": "2026-01",
                        "csv": statement(
                            [
                                txn("N1", "2026-01-03T10:00:00", note="new one"),
                                txn("L5", "2025-12-05T10:00:00"),
                            ]
                        ),
                    },
                    {
                        "month": "2025-12",
                        "csv": statement(
                            [
                                txn("L5", "2025-12-05T10:00:00"),
                                txn("N0", "2025-12-31T10:00:00", note="new zero"),
                            ]
                        ),
                    },
                ],
            }

    browser = Browser()
    keys = type(
        "K",
        (),
        {
            "get": lambda self: (_ for _ in ()).throw(
                AssertionError("bao must not be needed")
            )
        },
    )()
    out = pull_all(
        store, keys, fetcher=browser, today=lambda: date(2026, 1, 15), now=NOW
    )
    assert out["accounts"] == [{"alias": "venmo-dragos", "pulled": 2, "months": 2}]
    assert out["pipeline"]["ran"] is True
    assert browser.asked == [
        ("venmo-dragos", ["2025-12", "2026-01"])
    ]  # from the month of the latest known row
    after = pks(store)
    assert len(after) == 7
    for pk, row in before.items():  # every earlier row is where it was
        assert (
            after[pk]["description"] == row["description"]
            and after[pk]["date"] == row["date"]
        ), pk
    assert (
        after[edited_pk]["category"] == "My Own Category"
    )  # and the edit is still on it
    assert {after[pk]["description"] for pk in set(after) - set(before)} == {
        "Some One --> Another Person: new one",
        "Some One --> Another Person: new zero",
    }
    # a second pull within the minimum interval makes no visit at all
    again = pull_all(
        store, keys, fetcher=browser, today=lambda: date(2026, 1, 15), now=NOW + 60
    )
    assert (
        "skipped" in again["accounts"][0]
        and again["pipeline"] is None
        and len(browser.asked) == 1
    )


# --- refresh_account ---------------------------------------------------------------------------------------------


class Fake:
    login_url = "https://fetch.test"

    def __init__(self, result=None, error=None):
        self.result, self.error, self.asked = result, error, []

    def login_link(self, account):
        return f"{self.login_url}/login?account={account}"

    def fetch(self, account, months, autologin=False):
        self.asked.append((account, months))
        if self.error:
            raise self.error
        return self.result


LOGGED_IN = {"state": "logged_in", "files": []}


def account(**kw):
    """A direct account whose login was seen working a moment ago, unless a test says otherwise."""
    return {"alias": "venmo-dragos", "institution": "venmo", "last_ok": NOW - 30, **kw}


def no_visit():
    return Fake(error=AssertionError("must not visit the bank"))


def registered(store, **kw):
    store.add_direct_account("venmo-dragos", "venmo")
    if "last_ok" in kw:
        store.mark_direct_session("venmo-dragos", kw["last_ok"])
    return store


@pytest.mark.parametrize("state", ["login_required", "challenge", "unknown"])
def test_a_lapsed_login_is_information_with_a_link_and_is_not_visited_again(
    store, state
):
    registered(store, last_ok=NOW - 30)
    r = dp.refresh_account(
        store, account(), Fake({"state": state, "files": []}), TODAY, NOW
    )
    assert (
        "error" not in r and "pulled" not in r
    )  # not a failure: the accounts whose login persists are pulled
    assert (
        r["login_needed"].endswith("log in by hand to fetch it") and r["state"] == state
    )
    assert r["login_url"] == "https://fetch.test/login?account=venmo-dragos"
    assert (
        store.direct_accounts()[0]["last_ok"] is None
        and store.direct_accounts()[0]["last_success"] is None
    )
    # known to be logged out now: a plain refresh a moment later does not visit again...
    again = dp.refresh_account(
        store, store.direct_accounts()[0], no_visit(), TODAY, NOW + 60
    )
    assert "login_needed" in again
    # ...but right after a person logs in (the fresh path) it fetches at once
    ok = dp.refresh_account(
        store, store.direct_accounts()[0], Fake(LOGGED_IN), TODAY, NOW + 90, fresh=True
    )
    assert ok == {"alias": "venmo-dragos", "pulled": 0, "months": 0}


def test_an_account_whose_login_is_not_believed_to_persist_is_not_visited(store):
    registered(store)
    for last_ok in (None, NOW - dp.SESSION_TRUST - 1, NOW - 3 * 3600):
        r = dp.refresh_account(store, account(last_ok=last_ok), no_visit(), TODAY, NOW)
        assert (
            "login_needed" in r
            and "error" not in r
            and r["login_url"].endswith("account=venmo-dragos")
        )
    assert dp.refresh_account(
        store, account(last_ok=NOW - 3 * 3600), no_visit(), TODAY, NOW
    )["login_needed"].startswith(
        "the saved login has probably expired (last seen logged in 3 h ago)"
    )
    # inside the window it is visited
    fake = Fake(LOGGED_IN)
    assert (
        dp.refresh_account(
            store, account(last_ok=NOW - dp.SESSION_TRUST), fake, TODAY, NOW
        )["pulled"]
        == 0
    )
    assert len(fake.asked) == 1


def test_a_fresh_login_fetches_whatever_the_interval_or_the_window(store):
    registered(store)
    stale_and_recent = account(
        last_ok=None, last_success=NOW - 5
    )  # no login on record, fetched 5 s ago
    r = dp.refresh_account(
        store, stale_and_recent, Fake(LOGGED_IN), TODAY, NOW, fresh=True
    )
    assert r == {"alias": "venmo-dragos", "pulled": 0, "months": 0}
    assert (
        store.direct_accounts()[0]["last_ok"] == NOW
    )  # and the login is now known good
    # but a plain refresh of the same account is held to the interval and the window
    assert "skipped" in dp.refresh_account(
        store, store.direct_accounts()[0], no_visit(), TODAY, NOW + 5
    )


def test_a_fresh_login_that_was_not_completed_is_login_needed_not_an_error(store):
    registered(store)
    r = dp.refresh_account(
        store,
        account(last_ok=None),
        Fake(
            {
                "state": "login_required",
                "files": [],
                "detail": "HTTP 200 at id.venmo.com/signin",
            }
        ),
        TODAY,
        NOW,
        fresh=True,
    )
    assert (
        r["login_needed"]
        == "Venmo is asking for a login (HTTP 200 at id.venmo.com/signin); log in by hand to fetch it"
    )
    assert "error" not in r


def test_a_success_starts_the_clock_and_a_failure_does_not(store):
    registered(store, last_ok=NOW - 30)
    bad = Fake(
        {
            "state": "logged_in",
            "files": [{"month": "2026-11", "csv": "<html>oops</html>"}],
        }
    )
    assert "error" in dp.refresh_account(store, account(), bad, TODAY, NOW)
    assert store.direct_accounts()[0]["last_success"] is None
    dp.refresh_account(store, account(), Fake(LOGGED_IN), TODAY, NOW)
    assert store.direct_accounts()[0]["last_success"] == NOW
    fresh = store.direct_accounts()[0]
    assert fresh["last_ok"] == NOW  # a success also renews "its login is working"
    assert "skipped" in dp.refresh_account(
        store, fresh, no_visit(), TODAY, NOW + dp.MIN_INTERVAL - 1
    )
    again = dp.refresh_account(
        store, fresh, Fake(LOGGED_IN), TODAY, NOW + dp.MIN_INTERVAL + 1
    )
    assert (
        "skipped" not in again and "login_needed" not in again
    )  # past the interval, still inside the window


def test_service_problems_are_reported_per_account_without_secrets(store):
    registered(store, last_ok=NOW - 30)
    r = dp.refresh_account(
        store,
        account(),
        Fake(error=dp.FetcherError("cannot reach the browser service (URLError)")),
        TODAY,
        NOW,
    )
    assert r == {
        "alias": "venmo-dragos",
        "error": "cannot reach the browser service (URLError)",
    }
    assert (
        dp.refresh_account(store, account(), None, TODAY, NOW)["error"]
        == "the browser service is not configured"
    )
    assert (
        store.direct_accounts()[0]["last_ok"] == NOW - 30
    )  # a service problem says nothing about the login


# --- the client ---------------------------------------------------------------------------------------------------


class Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self, *a):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_client_sends_the_token_and_never_echoes_it():
    seen = []

    def opener(req, timeout=None):
        seen.append(
            (
                req.get_method(),
                req.full_url,
                req.get_header("Authorization"),
                json.loads(req.data),
                timeout,
            )
        )
        if "busy" in req.data.decode():
            raise urllib.error.HTTPError(
                req.full_url,
                409,
                "x",
                {},
                io.BytesIO(b'{"detail": "a login session is running"}'),
            )
        if "boom" in req.data.decode():
            raise urllib.error.HTTPError(
                req.full_url,
                500,
                "x",
                {},
                io.BytesIO(b"Bearer SECRETTOKEN-0123456789abcdef"),
            )
        return Resp({"state": "logged_in", "files": []})

    c = dp.FetcherClient(
        "http://127.0.0.1:8097/",
        "SECRETTOKEN-0123456789abcdef",
        "https://fetch.test/",
        opener,
    )
    assert c.fetch("venmo-dragos", ["2026-11"]) == {"state": "logged_in", "files": []}
    assert seen[0][:4] == (
        "POST",
        "http://127.0.0.1:8097/fetch",
        "Bearer SECRETTOKEN-0123456789abcdef",
        {"account": "venmo-dragos", "months": ["2026-11"]},
    )
    assert (
        c.login_link("venmo-dragos") == "https://fetch.test/login?account=venmo-dragos"
    )
    with pytest.raises(dp.FetcherError, match="login session is running"):
        c.fetch("busy", [])
    with pytest.raises(dp.FetcherError) as e:
        c.fetch("boom", [])
    assert "HTTP 500" in str(e.value) and "SECRETTOKEN" not in str(e.value)

    def down(req, timeout=None):
        raise urllib.error.URLError("refused SECRETTOKEN")

    with pytest.raises(dp.FetcherError) as e:
        dp.FetcherClient("http://x", "SECRETTOKEN-0123456789abcdef", "", down).fetch(
            "a", []
        )
    assert "URLError" in str(e.value) and "SECRETTOKEN" not in str(e.value)


# --- Refresh data with both kinds of account -------------------------------------------------------------------


def keys_that_must_not_be_used():
    return type(
        "K",
        (),
        {
            "get": lambda self: (_ for _ in ()).throw(
                AssertionError("Plaid must not be touched")
            )
        },
    )()


def test_a_plaid_outage_does_not_stop_the_browser_accounts(store):
    store.update_config(
        lambda c: c.update(
            {
                "linked_accounts": {
                    "card": {
                        "alias": "card",
                        "institution": "B",
                        "start_date": "2026-01-01",
                        "token": "T",
                    }
                }
            }
        )
    )
    registered(store, last_ok=NOW - 30)
    keys = type(
        "K",
        (),
        {"get": lambda self: (_ for _ in ()).throw(PlaidUnavailable("bao is down"))},
    )()
    out = pull_all(store, keys, fetcher=Fake(LOGGED_IN), today=lambda: TODAY, now=NOW)
    by = {a["alias"]: a for a in out["accounts"]}
    assert by["card"]["error"] == "bao is down" and by["venmo-dragos"]["pulled"] == 0
    # with nothing else to pull, the outage is still an error, as before
    store.update_config(lambda c: c.pop("direct_accounts"))
    with pytest.raises(PlaidUnavailable):
        pull_all(store, keys, today=lambda: TODAY)


def test_refreshing_one_account_touches_nothing_else(store):
    store.update_config(
        lambda c: c.update(
            {
                "linked_accounts": {
                    "card": {
                        "alias": "card",
                        "institution": "B",
                        "start_date": "2026-01-01",
                        "token": "T",
                    }
                }
            }
        )
    )
    store.add_direct_account("venmo-dragos", "venmo")
    store.add_direct_account("venmo-viral", "venmo")
    fake = Fake(LOGGED_IN)
    out = pull_all(
        store,
        keys_that_must_not_be_used(),
        fetcher=fake,
        today=lambda: TODAY,
        now=NOW,
        only="venmo-dragos",
        fresh_login=True,
    )
    assert out["accounts"] == [{"alias": "venmo-dragos", "pulled": 0, "months": 0}]
    assert [a for a, _ in fake.asked] == [
        "venmo-dragos"
    ]  # not the other Venmo account, not Plaid
    assert pull_all(
        store,
        keys_that_must_not_be_used(),
        fetcher=fake,
        today=lambda: TODAY,
        now=NOW,
        only="nobody",
    )["accounts"] == [{"alias": "nobody", "error": "no such account to refresh"}]


def test_fresh_login_means_nothing_without_naming_the_account(store):
    store.add_direct_account("venmo-dragos", "venmo")  # no login on record
    out = pull_all(
        store,
        keys_that_must_not_be_used(),
        fetcher=no_visit(),
        today=lambda: TODAY,
        now=NOW,
        fresh_login=True,
    )
    assert "login_needed" in out["accounts"][0] and out["pipeline"] is None


def settings_for(root):
    return Settings(
        data_root=root,
        users={"me@example.com": "me"},
        trusted_proxies=frozenset({"testclient"}),
        fetcher=FetcherSettings("http://127.0.0.1:1", "t" * 32, "https://fetch.test"),
    )


def endpoint_app(tmp_path, fake, last_ok=None):
    root = tmp_path / "data"
    (root / "me").mkdir(parents=True)
    direct = {
        "alias": "venmo-dragos",
        "institution": "venmo",
        **({"last_ok": last_ok} if last_ok else {}),
    }
    (root / "me" / "config.json").write_text(
        json.dumps({"direct_accounts": {"venmo-dragos": direct}})
    )
    app = create_app(settings_for(root))
    app.state.fetcher = fake
    return TestClient(app)


def test_the_refresh_endpoint_reports_a_lapsed_login_as_information(tmp_path):
    c = endpoint_app(tmp_path, no_visit())  # no login on record: not visited
    r = c.post("/api/accounts/pull", headers=ME)
    assert r.status_code == 200
    (acct,) = r.json()["accounts"]
    assert acct["alias"] == "venmo-dragos" and "error" not in acct
    assert acct[
        "login_url"
    ] == "https://fetch.test/login?account=venmo-dragos" and acct[
        "login_needed"
    ].startswith("the saved login has probably expired")
    assert r.json()["pipeline"] is None


def test_after_login_only_counts_when_an_account_is_named(tmp_path):
    fake = Fake(LOGGED_IN)
    c = endpoint_app(tmp_path, fake)
    plain = c.post(
        "/api/accounts/pull", headers=ME, json={"after_login": True}
    )  # no `only`: it cannot skip the checks
    assert "login_needed" in plain.json()["accounts"][0] and fake.asked == []
    done = c.post(
        "/api/accounts/pull",
        headers=ME,
        json={"only": "venmo-dragos", "after_login": True},
    )
    assert done.json()["accounts"] == [
        {"alias": "venmo-dragos", "pulled": 0, "months": 0}
    ]
    assert len(fake.asked) == 1
    assert (
        c.post("/api/accounts/pull", headers=ME, json={"only": "x" * 100}).status_code
        == 422
    )
    assert (
        c.post("/api/accounts/pull", headers=ME).status_code == 200
    )  # no body at all still works, as before


# --- the command line ---------------------------------------------------------------------------------------------


def test_add_direct_registers_an_account_once_and_refuses_unknown_ones(
    tmp_path, capsys
):
    from server import cli

    root = tmp_path / "data"
    settings = Settings(
        data_root=root, users={"me@example.com": "me"}, trusted_proxies=frozenset()
    )
    assert cli.add_direct(settings, "me", "venmo-dragos") == 0
    assert cli.add_direct(settings, "me", "venmo-dragos") == 0  # again: still one entry
    assert [a["alias"] for a in UserStore(root / "me").direct_accounts()] == [
        "venmo-dragos"
    ]
    assert UserStore(root / "me").direct_accounts()[0]["institution"] == "venmo"
    assert cli.add_direct(settings, "me", "paypal-me") == 2  # no export layout for it
    assert cli.add_direct(settings, "nobody", "venmo-dragos") == 2
    assert cli.add_direct(settings, "me") == 2
    assert [a["alias"] for a in UserStore(root / "me").direct_accounts()] == [
        "venmo-dragos"
    ]


def test_the_pull_command_prints_a_line_for_each_kind_of_result(tmp_path, capsys):
    import time

    from server import cli

    root = tmp_path / "data"
    store = UserStore(root / "me")
    store.add_direct_account("venmo-dragos", "venmo")
    settings = settings_for(root)
    # no login on record: information, not a failure, and no visit
    assert cli.pull(settings, fetcher=no_visit()) == 0
    out = capsys.readouterr().out
    assert (
        "me/venmo-dragos: login needed, the saved login has probably expired" in out
        and "https://fetch.test/login?account=venmo-dragos" in out
    )
    # a login seen working a moment ago but a browser service that cannot be reached: a failure
    store.mark_direct_session("venmo-dragos", time.time())
    down = Fake(error=dp.FetcherError("cannot reach the browser service (URLError)"))
    assert cli.pull(settings, fetcher=down) == 1
    assert (
        "me/venmo-dragos: FAILED cannot reach the browser service (URLError)"
        in capsys.readouterr().out
    )
    # a login that lapsed meanwhile: information again
    assert (
        cli.pull(settings, fetcher=Fake({"state": "login_required", "files": []})) == 0
    )
    assert "login needed, Venmo is asking for a login" in capsys.readouterr().out
    # a recent fetch is reported as skipped, not as a failure
    store.mark_direct_success("venmo-dragos", time.time())
    assert cli.pull(settings, fetcher=no_visit()) == 0
    assert "venmo-dragos: skipped, fetched moments ago" in capsys.readouterr().out


# --- what a failed visit says -------------------------------------------------------------------------------------


def test_a_crashed_fetch_is_an_error_not_a_login_problem(store):
    registered(store, last_ok=NOW - 30)
    r = dp.refresh_account(
        store,
        account(),
        Fake(
            {"state": "error", "message": "the month field did not appear", "files": []}
        ),
        TODAY,
        NOW,
    )
    assert r == {
        "alias": "venmo-dragos",
        "error": "the month field did not appear",
    }  # no login link, not login_needed
    assert (
        dp.refresh_account(
            store, account(), Fake({"state": "error", "files": []}), TODAY, NOW
        )["error"]
        == "the fetch failed"
    )
    assert (
        store.direct_accounts()[0]["last_success"] is None
        and store.direct_accounts()[0]["last_ok"] == NOW - 30
    )


def test_a_bot_check_is_named_as_one_with_where_it_happened(store):
    registered(store, last_ok=NOW - 30)
    r = dp.refresh_account(
        store,
        account(),
        Fake(
            {
                "state": "challenge",
                "files": [],
                "detail": "HTTP 403 at id.venmo.com/signin",
            }
        ),
        TODAY,
        NOW,
    )
    assert r["state"] == "challenge" and "error" not in r
    assert (
        r["login_needed"]
        == "Venmo showed its bot check (HTTP 403 at id.venmo.com/signin); log in by hand to fetch it"
    )
    registered(store, last_ok=NOW - 30)
    plain = dp.refresh_account(
        store,
        account(),
        Fake(
            {
                "state": "login_required",
                "files": [],
                "detail": "HTTP 200 at id.venmo.com/signin",
            }
        ),
        TODAY,
        NOW,
    )
    assert (
        plain["login_needed"]
        == "Venmo is asking for a login (HTTP 200 at id.venmo.com/signin); log in by hand to fetch it"
    )


# --- automatic login: who may try, how often, and what each outcome says ----------------------------------------------


class Recorder(Fake):
    """A Fake that remembers whether each fetch was allowed to log in by itself."""

    def __init__(self, *results):
        super().__init__(None)
        self.queue, self.allowed = list(results), []

    def fetch(self, account, months, autologin=False):
        self.allowed.append(autologin)
        self.asked.append((account, months))
        return self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]


def auto_account(**kw):
    return {
        "alias": "wealthfront-dragos",
        "institution": "wealthfront",
        "autologin": True,
        **kw,
    }


def wf_store(store, **kw):
    store.add_direct_account("wealthfront-dragos", "wealthfront", autologin=True)
    return store


def test_only_an_account_set_up_for_it_is_ever_allowed_to_log_in_by_itself(store):
    wf_store(store)
    plain = Recorder(LOGGED_IN)
    dp.refresh_account(
        store, account(last_ok=NOW - 30), plain, TODAY, NOW
    )  # Venmo: no autologin flag
    assert plain.allowed == [False]
    auto = Recorder(LOGGED_IN)
    dp.refresh_account(store, auto_account(last_ok=NOW - 30), auto, TODAY, NOW)
    assert auto.allowed == [True]


def test_an_account_that_can_log_in_is_visited_even_when_its_saved_login_looks_stale(
    store,
):
    wf_store(store)
    rec = Recorder({"state": "logged_in", "files": [], "auto_login": "ok"})
    out = dp.refresh_account(
        store, auto_account(last_ok=None), rec, TODAY, NOW
    )  # no login on record at all
    assert rec.allowed == [True]  # the login lapses within minutes; trying is the point
    assert out == {
        "alias": "wealthfront-dragos",
        "pulled": 0,
        "months": 0,
        "auto_login": "ok",
    }
    assert (
        store.direct_accounts()[0]["last_ok"] == NOW
        and store.direct_accounts()[0]["autologin_failed"] is None
    )


def test_a_fresh_login_by_a_person_never_asks_for_an_automatic_one(store):
    wf_store(store)
    rec = Recorder(LOGGED_IN)
    dp.refresh_account(store, auto_account(), rec, TODAY, NOW, fresh=True)
    assert rec.allowed == [False]


def test_a_failed_automatic_login_is_named_recorded_and_not_retried_for_a_while(store):
    wf_store(store)
    failed = {
        "state": "login_required",
        "files": [],
        "detail": "HTTP 200 at www.wealthfront.com/login",
        "auto_login": "failed",
    }
    rec = Recorder(failed)
    out = dp.refresh_account(store, auto_account(), rec, TODAY, NOW)
    assert "error" not in out and out["auto_login"] == "failed"
    assert out["login_needed"] == (
        "the automatic login did not get in (Wealthfront is asking for a login, HTTP 200 at www.wealthfront.com/login); "
        "log in by hand to fetch it"
    )
    assert out["login_url"] == "https://fetch.test/login?account=wealthfront-dragos"
    state = store.direct_accounts()[0]
    assert (
        state["autologin_failed"] == NOW
        and state["last_ok"] is None
        and state["last_success"] is None
    )
    # a moment later: no visit at all, and it says why
    soon = dp.refresh_account(store, state, no_visit(), TODAY, NOW + 120)
    assert soon["login_needed"].startswith(
        "the automatic login failed 2 min ago and is not retried yet; "
    )
    # past the pause it may try again
    again = Recorder(LOGGED_IN | {"auto_login": "ok"})
    ok = dp.refresh_account(
        store, store.direct_accounts()[0], again, TODAY, NOW + dp.AUTOLOGIN_RETRY + 1
    )
    assert again.allowed == [True] and ok["auto_login"] == "ok"
    assert (
        store.direct_accounts()[0]["autologin_failed"] is None
    )  # a success clears the failure


def test_inside_the_pause_a_login_a_person_just_did_is_still_fetched_without_another_attempt(
    store,
):
    wf_store(store)
    store.mark_direct_autologin("wealthfront-dragos", NOW - 60)
    store.mark_direct_session(
        "wealthfront-dragos", NOW - 30
    )  # they logged in by hand a moment ago
    rec = Recorder(LOGGED_IN)
    out = dp.refresh_account(store, store.direct_accounts()[0], rec, TODAY, NOW)
    assert rec.allowed == [False] and out["pulled"] == 0


def test_a_site_without_login_steps_is_not_marked_as_failed(store):
    wf_store(store)
    rec = Recorder(
        {"state": "login_required", "files": [], "auto_login": "unsupported"}
    )
    out = dp.refresh_account(store, auto_account(), rec, TODAY, NOW)
    assert "login_needed" in out and "auto_login" not in out
    assert (
        store.direct_accounts()[0]["autologin_failed"] is None
    )  # nothing was attempted, so nothing is held back


def test_a_crash_during_an_automatic_login_attempt_is_an_error_not_a_login_problem(
    store,
):
    wf_store(store)
    rec = Recorder(
        {
            "state": "error",
            "message": "the fetch took too long",
            "files": [],
            "auto_login": "failed",
        }
    )
    out = dp.refresh_account(store, auto_account(), rec, TODAY, NOW)
    assert out == {"alias": "wealthfront-dragos", "error": "the fetch took too long"}


def test_the_client_asks_for_an_automatic_login_only_when_allowed():
    sent = []

    def opener(req, timeout=None):
        sent.append(json.loads(req.data))
        return Resp({"state": "logged_in", "files": []})

    c = dp.FetcherClient("http://127.0.0.1:8097", "t" * 32, "", opener)
    c.fetch("a", ["2026-11"])
    c.fetch("a", ["2026-11"], autologin=True)
    assert sent == [
        {"account": "a", "months": ["2026-11"]},
        {"account": "a", "months": ["2026-11"], "autologin": True},
    ]


def test_add_direct_can_turn_automatic_login_on(tmp_path, monkeypatch):
    from server import cli

    root = tmp_path / "data"
    settings = Settings(
        data_root=root, users={"me@example.com": "me"}, trusted_proxies=frozenset()
    )
    assert cli.add_direct(settings, "me", "venmo-dragos") == 0
    assert cli.add_direct(settings, "me", "wealthfront-dragos", autologin=True) == 0
    by = {a["alias"]: a for a in UserStore(root / "me").direct_accounts()}
    assert (
        by["venmo-dragos"]["autologin"] is False
        and by["wealthfront-dragos"]["autologin"] is True
    )
    # and the command line accepts the flag (main reads its settings from the environment)
    users = tmp_path / "users.json"
    users.write_text(json.dumps({"me@example.com": "me"}))
    monkeypatch.setenv("USERS_FILE", str(users))
    monkeypatch.setenv("DATA_ROOT", str(root))
    UserStore(root / "me").update_config(
        lambda c: c["direct_accounts"].pop("wealthfront-dragos")
    )
    assert cli.main(["add-direct", "me", "wealthfront-dragos", "--autologin"]) == 0
    assert {
        a["alias"]: a["autologin"] for a in UserStore(root / "me").direct_accounts()
    }["wealthfront-dragos"] is True
