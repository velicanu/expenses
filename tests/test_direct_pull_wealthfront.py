import csv
import io
from datetime import date

import pytest

from server import direct_pull as dp
from server.store import UserStore

NOW = 1_800_000_000.0
H = dp.WF_HEADER


def export(rows):
    """Wealthfront's export: the header, then rows newest first."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(H)
    w.writerows(rows)
    return out.getvalue()


@pytest.fixture
def store(tmp_path):
    s = UserStore(tmp_path / "me")
    s.raw_dir.mkdir(parents=True)
    return s


def legacy(store, rows):
    (store.raw_dir / "wealthfront-dragos.csv").write_text(export(rows))


def direct(store):
    return list(
        csv.reader(open(store.raw_dir / "wealthfront-dragos-direct.csv", newline=""))
    )


LEGACY = [
    ["1/3/2024", "Deposit", "Transfer", "100.00"],
    ["1/2/2024", "Interest", "Interest", "0.50"],
    ["1/2/2024", "Interest", "Interest", "0.50"],
]


def test_it_rejects_another_layout():
    for bad in [
        "",
        "<html>login</html>",
        "Date,Description,Type,Amount\n1/1/2024,a,b,1",
    ]:
        with pytest.raises(dp.DirectPullError):
            dp.parse_wealthfront(bad)
    with pytest.raises(dp.DirectPullError, match="layout"):
        dp.parse_wealthfront(export([["not a date", "x", "y", "1.00"]]))


def test_relabelled_rows_are_not_new_and_duplicates_count(store):
    legacy(store, LEGACY)
    header, rows = dp.parse_wealthfront(
        export(
            [
                ["1/5/2024", "New thing", "Transfer", "-20.00"],
                [
                    "1/3/2024",
                    "Deposit (reworded)",
                    "Other",
                    "100.00",
                ],  # same day and amount: the same row
                ["1/2/2024", "Interest", "Relabelled", "0.50"],
                ["1/2/2024", "Interest", "Interest", "0.50"],
                [
                    "1/2/2024",
                    "Interest",
                    "Interest",
                    "0.50",
                ],  # a third equal row is a new one
                ["12/31/2023", "Before the file began", "Transfer", "5.00"],
            ]
        )
    )
    assert (
        dp.append_new_wealthfront(store.raw_dir, "wealthfront-dragos", header, rows)
        == 2
    )
    got = direct(store)
    assert got[0] == H
    assert [(r[0], r[3]) for r in got[1:]] == [
        ("1/2/2024", "0.50"),
        ("1/5/2024", "-20.00"),
    ]  # oldest first
    # asking again adds nothing
    assert (
        dp.append_new_wealthfront(store.raw_dir, "wealthfront-dragos", header, rows)
        == 0
    )


def test_an_account_with_nothing_yet_takes_everything_oldest_first(store):
    header, rows = dp.parse_wealthfront(
        export([["2/1/2024", "b", "t", "2.00"], ["1/1/2024", "a", "t", "1.00"]])
    )
    assert (
        dp.append_new_wealthfront(store.raw_dir, "wealthfront-dragos", header, rows)
        == 2
    )
    assert [r[0] for r in direct(store)[1:]] == ["1/1/2024", "2/1/2024"]


def test_existing_lines_stay_byte_for_byte(store):
    legacy(store, LEGACY)
    header, rows = dp.parse_wealthfront(export([["2/1/2024", "b", "t", "2.00"]]))
    dp.append_new_wealthfront(store.raw_dir, "wealthfront-dragos", header, rows)
    first = (store.raw_dir / "wealthfront-dragos-direct.csv").read_bytes()
    header, rows = dp.parse_wealthfront(
        export([["3/1/2024", "c", "t", "3.00"], ["2/1/2024", "b", "t", "2.00"]])
    )
    assert (
        dp.append_new_wealthfront(store.raw_dir, "wealthfront-dragos", header, rows)
        == 1
    )
    assert (
        (store.raw_dir / "wealthfront-dragos-direct.csv").read_bytes().startswith(first)
    )


class Browser:
    login_url = "https://fetch.test"

    def __init__(self, csv_text):
        self.csv_text, self.asked = csv_text, []

    def login_link(self, account):
        return f"{self.login_url}/login?account={account}"

    def fetch(self, account, months, autologin=False):
        self.asked.append((account, autologin))
        return {
            "state": "logged_in",
            "auto_login": "ok",
            "files": [{"month": "all", "csv": self.csv_text}],
        }


def test_refresh_pulls_wealthfront_through_the_pipeline_and_keeps_keys_and_edits(store):
    legacy(store, LEGACY)
    store.add_direct_account("wealthfront-dragos", "wealthfront", autologin=True)
    store.run_pipeline()
    before = {r["pk"]: r for r in store.to_rows(store.expenses())}
    assert len(before) == 3
    edited = sorted(before)[1]
    store.update_transaction(edited, {"category": "Mine"})
    browser = Browser(export([["1/9/2024", "Fresh", "Transfer", "-7.00"], *LEGACY]))
    out = dp.refresh_direct(store, browser, date(2026, 11, 24), now=NOW)
    assert out == [
        {"alias": "wealthfront-dragos", "pulled": 1, "months": 1, "auto_login": "ok"}
    ]
    assert browser.asked == [("wealthfront-dragos", True)]  # it may log itself in
    store.run_pipeline()
    after = {r["pk"]: r for r in store.to_rows(store.expenses())}
    assert len(after) == 4
    for pk, row in before.items():
        assert (
            after[pk]["description"] == row["description"]
            and after[pk]["date"] == row["date"]
        )
    assert after[edited]["category"] == "Mine"
    # a second click inside the interval makes no visit
    again = dp.refresh_direct(store, browser, date(2026, 11, 24), now=NOW + 60)
    assert "skipped" in again[0] and len(browser.asked) == 1


def test_one_day_keeps_its_order_oldest_first(store):
    header, rows = (
        dp.parse_wealthfront(  # newest first, as exported: "second" happened after "first"
            export(
                [
                    ["2/1/2024", "second", "t", "2.00"],
                    ["2/1/2024", "first", "t", "1.00"],
                ]
            )
        )
    )
    dp.append_new_wealthfront(store.raw_dir, "wealthfront-dragos", header, rows)
    assert [r[1] for r in direct(store)[1:]] == ["first", "second"]
