"""One-off: re-key a user's changes.db after standardize.ordered() changed how rows are numbered.

    python src/migrate_pks.py DATA_DIR            # dry run: report, change nothing
    python src/migrate_pks.py DATA_DIR --apply    # back up changes.db, then re-key it

Why: an edit in changes.db is keyed by pk (`<source_file>-<line>`). The old ordering broke ties between rows
on the same date with an unstable sort, so the line numbers inside those groups were arbitrary and changed
whenever a file grew. The new ordering is stable, so existing databases carry pks from the old numbering.

How: DATA_DIR/expenses.db is the base the edits were made against (run this BEFORE the first pipeline run
with the new code). The raw files are run through the new pipeline in a temp directory, and each old row is
matched to a new row by what it says (source_file, date, description, amount, original category) and its
occurrence number among identical rows, so that legitimate duplicates (the same fare twice in a day) pair up
in order. Each edit follows its row to the new pk. Nothing is written unless a check passes: every edit must land on a row that
says the same thing as the row it was made on, and show the same category, amount, description and date.

Left alone: edits for added rows (`input-N`), and edits whose row is already gone from the raw files (those
were orphaned before this and stay as they are).

After --apply, run the pipeline to rebuild expenses.db with the new numbering.
"""

import argparse
import collections
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import time

from fsutil import get_config
from pipeline import run as run_pipeline

SHOWN = ("category", "amount", "description", "date")


def row_key(row):
    """What a row says, independent of its number and of the rules (category is rule-dependent)."""
    return (
        row["source_file"],
        row["date"],
        row["description"],
        round(float(row["amount"]), 2),
        row["old_category"],
    )


def occurrences(rows):
    """[(key, n)] for rows in line order: n counts identical rows, so duplicates pair up in order."""
    seen = collections.Counter()
    out = []
    for row in sorted(rows, key=lambda r: (r["source_file"], r["line"])):
        key = row_key(row)
        out.append(((key, seen[key]), row["pk"]))
        seen[key] += 1
    return out


def build_mapping(old_rows, new_rows):
    """old pk -> new pk for every old row that still exists in the new numbering."""
    new_by_id = dict(occurrences(new_rows))
    return {
        old_pk: new_by_id[ident]
        for ident, old_pk in occurrences(old_rows)
        if ident in new_by_id
    }


def rekey(changes, mapping, old_pks, new_pks):
    """changes: {pk: row}. Returns (new_changes, report). Rows are re-keyed only if they follow an old base row
    that has a counterpart; `line` follows the new pk."""
    out, report = {}, collections.Counter()
    for pk, row in changes.items():
        if pk.startswith("input-"):
            out[pk] = row
            report["added rows (kept)"] += 1
        elif pk in mapping:
            new_pk = mapping[pk]
            out[new_pk] = {**row, "pk": new_pk, "line": int(new_pk.rsplit("-", 1)[1])}
            report["moved" if new_pk != pk else "unchanged"] += 1
        elif pk not in old_pks:
            out[pk] = row
            report["already orphaned (kept)"] += 1
        else:
            out[pk] = row
            report["row gone from raw (kept)"] += 1
            if pk in new_pks:
                report["row gone AND its pk now belongs to another row"] += 1
    if len(out) != len(changes):
        raise ValueError("two edits would end up on the same row")
    return out, report


def final_view(base, changes, pk):
    row = changes.get(pk) or base[pk]
    return tuple(round(float(row[c]), 2) if c == "amount" else row[c] for c in SHOWN)


def verify(old_base, old_changes, new_base, new_changes, mapping):
    """Edits that would not end up on a row saying the same thing, or would show differently. Must be empty.
    (Unedited rows are not compared: their category depends on the rules, which may have changed since.)"""
    bad = []
    for old_pk in old_changes:
        new_pk = mapping.get(old_pk)
        if new_pk is None:
            continue
        if row_key(old_base[old_pk]) != row_key(new_base[new_pk]) or final_view(
            old_base, old_changes, old_pk
        ) != final_view(new_base, new_changes, new_pk):
            bad.append((old_pk, new_pk))
    return bad


def read_table(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return {r["pk"]: dict(r) for r in conn.execute("SELECT * FROM expenses")}
    finally:
        conn.close()


def new_base_from_raw(data_dir):
    """Runs the current pipeline on a copy of raw/ in a temp directory and returns its expenses.db rows."""
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(os.path.join(data_dir, "raw"), os.path.join(tmp, "raw"))
        config = get_config(os.path.join(data_dir, "config.json"))
        if not run_pipeline(tmp, config={"rules": config.get("rules", {})}):
            raise SystemExit("the pipeline produced nothing from raw/")
        return read_table(os.path.join(tmp, "expenses.db"))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("data_dir")
    ap.add_argument(
        "--apply", action="store_true", help="write changes.db (after backing it up)"
    )
    args = ap.parse_args(argv)
    logging.disable(logging.CRITICAL)

    data_dir = args.data_dir
    changes_path = os.path.join(data_dir, "changes.db")
    old_base = read_table(os.path.join(data_dir, "expenses.db"))
    old_changes = read_table(changes_path)
    new_base = new_base_from_raw(data_dir)

    mapping = build_mapping(list(old_base.values()), list(new_base.values()))
    new_changes, report = rekey(old_changes, mapping, set(old_base), set(new_base))
    bad = verify(old_base, old_changes, new_base, new_changes, mapping)

    print(
        f"old base {len(old_base)} rows, new base {len(new_base)} rows, {len(mapping)} old rows found again"
    )
    print(f"changes.db: {len(old_changes)} rows")
    for what, n in sorted(report.items()):
        print(f"  {what}: {n}")
    print(f"edits that would not land on the same transaction: {len(bad)}")
    if bad:
        print("REFUSING: the re-keyed edits do not reproduce the current view", bad[:5])
        return 1
    if report["row gone AND its pk now belongs to another row"]:
        print(
            "REFUSING: an edit for a row that is gone would attach to a different row"
        )
        return 1
    if not args.apply:
        print("dry run: nothing written (add --apply to write)")
        return 0

    backup = os.path.join(
        data_dir, f"changes.pre-pk-migration-{time.strftime('%Y%m%d-%H%M%S')}.db"
    )
    shutil.copy2(changes_path, backup)
    conn = sqlite3.connect(changes_path, timeout=30)
    try:
        columns = [c[1] for c in conn.execute("PRAGMA table_info(expenses)")]
        with conn:  # one transaction: all of it or none of it
            conn.execute("DELETE FROM expenses")
            conn.executemany(
                f"INSERT INTO expenses({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
                [[row.get(c) for c in columns] for row in new_changes.values()],
            )
    finally:
        conn.close()
    print(f"written; the old file is kept as {backup}")
    print("now run the pipeline to rebuild expenses.db with the new numbering")
    return 0


if __name__ == "__main__":
    sys.exit(main())
