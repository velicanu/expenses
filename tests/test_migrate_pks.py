import glob
import os

import pandas as pd
import pytest

import migrate_pks
import standardize
from server.store import UserStore

HEADER = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"


def write_chase(path, rows):
    """rows: (date 'MM/DD/YYYY', description, amount) in the order a newest-first export lists them."""
    with open(path, "w") as f:
        f.write(HEADER)
        for date, description, amount in rows:
            f.write(f"{date},{date},{description},Food & Drink,Sale,{amount:.2f},\n")


def make_rows(days=30, per_day=4):
    rows = []
    for d in range(days, 0, -1):  # newest first
        for n in range(per_day):
            rows.append((f"03/{d:02d}/2024", f"SHOP {d}-{n}", -(10 + n)))
    # a legitimate duplicate: the same fare twice on one day
    rows.insert(8, ("03/28/2024", "SUBWAY FARE", -2.90))
    rows.insert(9, ("03/28/2024", "SUBWAY FARE", -2.90))
    return rows


def old_ordered(records):
    """Stands in for the old numbering: same dates in order, but a different tie order from the real one
    (which keeps the file's order, reversed for a newest-first file: SHOP d-3 before d-0)."""
    df = pd.DataFrame(records).sort_values(
        by=["date", "description"], ascending=[True, True], kind="stable"
    )
    out = df.to_dict(orient="records")
    for line, record in enumerate(out):
        record["pk"] = f"{record['source_file']}-{line}"
        record["line"] = line
    return out


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "me"
    (d / "raw").mkdir(parents=True)
    write_chase(d / "raw" / "chase.csv", make_rows())
    monkeypatch.setattr(standardize, "ordered", old_ordered)
    store = UserStore(d)
    assert store.run_pipeline()["ran"]
    monkeypatch.undo()  # from here on the real, stable ordering
    return d


def edit_by_description(store, description, **updates):
    df = store.expenses()
    pks = list(df[df["description"] == description]["pk"])
    store.update_transaction(pks[0], updates)
    return pks[0]


def full_view(store):
    """Every visible transaction, whatever its pk: what the user sees. An edit is a full copy of its row, so a
    misplaced edit shows up here as one transaction missing and another one twice."""
    df = store.expenses()
    return sorted(
        (r.description, r.date, round(r.amount, 2), r.category) for r in df.itertuples()
    )


def edited_view(store):
    df = store.expenses()
    return sorted(
        (r.description, r.category, round(r.amount, 2), bool(r.edited))
        for r in df.itertuples()
        if r.edited
    )


# --- the pieces --------------------------------------------------------------------------------------


def row(
    pk,
    source="a.csv",
    line=0,
    date="2024-01-01",
    description="X",
    amount=-1.0,
    old="Food",
):
    return {
        "pk": pk,
        "source_file": source,
        "line": line,
        "date": date,
        "description": description,
        "amount": amount,
        "old_category": old,
        "category": "Other",
    }


def test_identical_rows_pair_up_in_order():
    old = [
        row("a.csv-0", line=0),
        row("a.csv-1", line=1),
        row("a.csv-2", line=2, description="Y"),
    ]
    new = [
        row("a.csv-0", line=0, description="Y"),
        row("a.csv-1", line=1),
        row("a.csv-2", line=2),
    ]
    assert migrate_pks.build_mapping(old, new) == {
        "a.csv-2": "a.csv-0",
        "a.csv-0": "a.csv-1",
        "a.csv-1": "a.csv-2",
    }


def test_a_row_that_is_gone_has_no_mapping():
    old = [row("a.csv-0"), row("a.csv-1", description="Z", line=1)]
    new = [row("a.csv-0")]
    assert migrate_pks.build_mapping(old, new) == {"a.csv-0": "a.csv-0"}


def test_rekey_moves_edits_keeps_the_rest_and_counts():
    changes = {
        "a.csv-1": row("a.csv-1", line=1),
        "input-0": row("input-0", source="input"),
        "a.csv-9": row("a.csv-9", line=9),  # was never in the base: orphaned already
        "a.csv-2": row("a.csv-2", line=2),  # in the base, gone from the new one
    }
    mapping = {"a.csv-1": "a.csv-5"}
    out, report = migrate_pks.rekey(
        changes, mapping, old_pks={"a.csv-1", "a.csv-2"}, new_pks={"a.csv-5"}
    )
    assert set(out) == {"a.csv-5", "input-0", "a.csv-9", "a.csv-2"}
    assert out["a.csv-5"]["line"] == 5 and out["a.csv-5"]["pk"] == "a.csv-5"
    assert (
        report["moved"] == 1
        and report["already orphaned (kept)"] == 1
        and report["row gone from raw (kept)"] == 1
    )
    assert "row gone AND its pk now belongs to another row" not in report


def test_rekey_flags_an_edit_that_would_attach_to_another_row():
    changes = {"a.csv-2": row("a.csv-2", line=2)}
    _, report = migrate_pks.rekey(changes, {}, old_pks={"a.csv-2"}, new_pks={"a.csv-2"})
    assert report["row gone AND its pk now belongs to another row"] == 1


# --- end to end --------------------------------------------------------------------------------------


def test_edits_stay_on_their_transactions_through_the_migration(
    data_dir, monkeypatch, capsys
):
    store = UserStore(data_dir)
    for description in ("SHOP 5-2", "SHOP 17-0", "SHOP 17-3", "SHOP 30-1"):
        edit_by_description(store, description, category="Hobbies")
    subway = edit_by_description(store, "SUBWAY FARE", category="Travel", amount=-3.0)
    before = edited_view(store)
    assert len(before) == 5
    view_before = full_view(store)
    changes_before = open(data_dir / "changes.db", "rb").read()

    # dry run: reports, writes nothing
    assert migrate_pks.main([str(data_dir)]) == 0
    out = capsys.readouterr().out
    assert "moved:" in out and "dry run" in out
    assert open(data_dir / "changes.db", "rb").read() == changes_before

    assert migrate_pks.main([str(data_dir), "--apply"]) == 0
    assert len(glob.glob(str(data_dir / "changes.pre-pk-migration-*.db"))) == 1
    assert (
        open(glob.glob(str(data_dir / "changes.pre-pk-migration-*.db"))[0], "rb").read()
        == changes_before
    )

    UserStore(data_dir).run_pipeline()  # rebuild with the new numbering
    after_store = UserStore(data_dir)
    assert edited_view(after_store) == before
    assert (
        full_view(after_store) == view_before
    )  # not one transaction missing, none twice
    df = after_store.expenses()
    assert df[df["edited"]]["pk"].isin(set(df["pk"])).all() and df["pk"].is_unique
    # the duplicate pair: both rows still there, exactly one carries the edit
    fares = df[df["description"] == "SUBWAY FARE"]
    assert len(fares) == 2 and sorted(fares["edited"]) == [False, True]
    assert subway  # (the pk it had before; it may well differ now)


def test_running_it_again_has_nothing_to_move(data_dir, capsys):
    edit_by_description(UserStore(data_dir), "SHOP 5-2", category="Hobbies")
    assert migrate_pks.main([str(data_dir), "--apply"]) == 0
    UserStore(data_dir).run_pipeline()
    capsys.readouterr()
    assert migrate_pks.main([str(data_dir)]) == 0
    assert "moved" not in capsys.readouterr().out


def test_it_refuses_when_an_edit_would_attach_to_another_row(data_dir, capsys):
    store = UserStore(data_dir)
    edit_by_description(
        store, "SHOP 1-0", category="Hobbies"
    )  # the oldest row, a high line number later
    # drop that row from the raw file: its edit's pk now belongs to some other row
    rows = [r for r in make_rows() if r[1] != "SHOP 1-0"]
    write_chase(data_dir / "raw" / "chase.csv", rows)
    before = open(data_dir / "changes.db", "rb").read()
    capsys.readouterr()
    assert migrate_pks.main([str(data_dir), "--apply"]) == 1
    assert "REFUSING" in capsys.readouterr().out
    assert open(data_dir / "changes.db", "rb").read() == before
    assert not glob.glob(str(data_dir / "changes.pre-pk-migration-*.db"))
    assert os.path.exists(data_dir / "expenses.db")


def test_without_the_migration_a_rebuild_puts_edits_on_the_wrong_rows(data_dir):
    """The problem the tool exists for: the same rebuild, no migration."""
    store = UserStore(data_dir)
    for description in ("SHOP 5-2", "SHOP 17-0", "SHOP 17-3", "SHOP 30-1"):
        edit_by_description(store, description, category="Hobbies")
    before = full_view(store)
    assert len(before) == 122
    UserStore(data_dir).run_pipeline()  # new numbering, old keys
    after = full_view(UserStore(data_dir))
    assert len(after) == 122  # same number of rows...
    assert after != before  # ...but some transaction is gone and another shows twice
