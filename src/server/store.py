"""One user's data directory: expenses.db (rebuilt by the pipeline), changes.db (their edits), config.json,
and the raw CSVs.

Only the API process writes here, and only changes.db, config.json and raw/ by hand; expenses.db comes
from the pipeline, which swaps it into place atomically. Every query is parameterised, and column names
come from the table, never from a request.
"""

import math
import os
import re
import sqlite3
import threading
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd

from detect import save_file_if_valid
from fsutil import get_config, make_dirs, put_config
from pipeline import run as run_pipeline
from sql import apply_changes, get_create_table_string
from standardize import get_default_categories

COLUMNS = [
    "pk",
    "date",
    "description",
    "amount",
    "category",
    "source",
    "source_file",
    "old_category",
    "line",
]
INPUT_PK = re.compile(r"^input-(\d+)$")
FILE_NAME = re.compile(r"^[^/\\\x00]{1,200}$")


class NoData(Exception):
    """There is no expenses.db yet (nothing uploaded, or the pipeline has not run)."""


class PipelineBusy(Exception):
    pass


def _native(value):
    """numpy / NaN -> something json and sqlite accept."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _stamp(d: date) -> str:
    return d.isoformat() + " 00:00:00"


class UserStore:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.db = self.dir / "expenses.db"
        self.changes_db = self.dir / "changes.db"
        self.config_file = self.dir / "config.json"
        self.raw_dir = self.dir / "raw"
        self.cards_dir = self.dir / "cards"
        self._lock = threading.RLock()
        self._pipeline_lock = threading.Lock()
        self._cache = None  # (signature, frame)

    # --- reading -------------------------------------------------------------------------------------

    def _signature(self):
        sig = []
        for p in (self.db, self.changes_db):
            try:
                st = p.stat()
                sig.append((st.st_mtime_ns, st.st_size))
            except FileNotFoundError:
                sig.append(None)
        return tuple(sig)

    @staticmethod
    def _read_only(path: Path):
        return sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=30)

    def expenses(self) -> pd.DataFrame:
        """Every transaction with the user's edits applied and zero amounts (deleted) left out. Adds `ts`
        (parsed date) and `edited`. Cached until either database file changes."""
        with self._lock:
            sig = self._signature()
            if self._cache and self._cache[0] == sig:
                return self._cache[1]
            df = self._load()
            self._cache = (sig, df)
            return df

    def _load(self) -> pd.DataFrame:
        empty = pd.DataFrame(columns=[*COLUMNS, "ts", "edited"])
        if not self.db.exists():
            return empty
        try:
            with self._read_only(self.db) as conn:
                df = pd.read_sql("SELECT * FROM expenses", conn)
        except (sqlite3.DatabaseError, pd.errors.DatabaseError):
            return empty
        changed = set()
        if self.changes_db.exists():
            try:
                with self._read_only(self.changes_db) as conn:
                    chdf = pd.read_sql("SELECT * FROM expenses", conn)
            except (sqlite3.DatabaseError, pd.errors.DatabaseError):
                chdf = None
            if chdf is not None and not chdf.empty:
                changed = set(chdf["pk"])
                df = apply_changes(df, chdf)
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        df = df[
            df["amount"] != 0
        ].copy()  # an amount of 0 is how a transaction is deleted
        df["ts"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
        df["edited"] = df["pk"].isin(changed)
        return df.reset_index(drop=True)

    @staticmethod
    def to_rows(df: pd.DataFrame) -> list:
        return [
            {
                "pk": r.pk,
                "date": r.ts.date().isoformat() if pd.notna(r.ts) else None,
                "description": _native(r.description),
                "amount": round(float(r.amount), 2),
                "category": _native(r.category),
                "source": _native(r.source),
                "source_file": _native(r.source_file),
                "edited": bool(r.edited),
            }
            for r in df.itertuples()
        ]

    def meta(self) -> dict:
        df = self.expenses()
        rules = self.rules()
        categories = (
            set(df["category"].dropna())
            | get_default_categories()
            | set(rules["new_categories"])
        )
        valid = df["ts"].dropna()
        return {
            "min_date": valid.min().date().isoformat() if not valid.empty else None,
            "max_date": valid.max().date().isoformat() if not valid.empty else None,
            "count": int(len(df)),
            "categories": sorted(categories),
            "data_categories": sorted(df["category"].dropna().unique()),
            "sources": sorted(df["source_file"].dropna().unique()),
            "new_category_colors": rules["new_categories"],
        }

    # --- edits (changes.db) --------------------------------------------------------------------------

    def _changes_conn(self):
        if not self.changes_db.exists():
            if not self.db.exists():
                raise NoData("no data yet: upload a CSV first")
            with sqlite3.connect(self.db) as conn:
                create = get_create_table_string("expenses", conn)
            if not create:
                raise NoData("no data yet: run the pipeline first")
            make_dirs([self.dir])
            conn = sqlite3.connect(self.changes_db, timeout=30)
            conn.execute(create)
            conn.commit()
            return conn
        return sqlite3.connect(self.changes_db, timeout=30)

    def _write_change(self, row: dict):
        conn = self._changes_conn()
        try:
            columns = [c[1] for c in conn.execute("PRAGMA table_info(expenses)")]
            use = [c for c in columns if c in row]
            conn.execute(
                f"INSERT OR REPLACE INTO expenses({','.join(use)}) VALUES ({','.join('?' * len(use))})",
                [_native(row[c]) for c in use],
            )
            conn.commit()
        finally:
            conn.close()

    def _base_row(self, pk: str) -> dict:
        df = self.expenses()
        hit = df[df["pk"] == pk]
        if hit.empty:
            raise KeyError(pk)
        row = hit.iloc[0].to_dict()
        row.pop("ts", None)
        row.pop("edited", None)
        return {k: _native(v) for k, v in row.items()}

    def update_transaction(self, pk: str, updates: dict) -> dict:
        with self._lock:
            row = self._base_row(pk)
            for key, value in updates.items():
                row[key] = _stamp(value) if key == "date" else value
            self._write_change(row)
            return row

    def delete_transaction(self, pk: str):
        """Soft delete: the pipeline would bring a deleted row straight back, so it is kept with amount 0."""
        self.update_transaction(pk, {"amount": 0.0})

    def add_transaction(
        self, day: date, description: str, amount: float, category: str
    ) -> dict:
        with self._lock:
            n = 1 + max(
                (
                    int(m.group(1))
                    for pk in self.expenses()["pk"]
                    if (m := INPUT_PK.match(str(pk)))
                ),
                default=-1,
            )
            row = {
                "date": _stamp(day),
                "description": description,
                "amount": amount,
                "category": category,
                "source": "input",
                "source_file": "input",
                "old_category": "Other",
                "pk": f"input-{n}",
                "line": n,
            }
            self._write_change(row)
            return row

    def sql_frame(self) -> pd.DataFrame:
        """What the old app ran its queries over: every transaction with the user's edits applied and zero
        amounts left out, with the table's own columns (no parsed date, no `edited`)."""
        return self.expenses().drop(columns=["ts", "edited"]).reset_index(drop=True)

    # --- config and rules ----------------------------------------------------------------------------

    def config(self) -> dict:
        with self._lock:
            return get_config(self.config_file)

    def update_config(self, fn):
        with self._lock:
            cfg = get_config(self.config_file)
            fn(cfg)
            make_dirs([self.dir])
            put_config(self.config_file, cfg)

    def rules(self) -> dict:
        rules = self.config().get("rules") or {}
        return {
            k: dict(rules.get(k) or {})
            for k in ("description", "category", "new_categories")
        }

    def set_rules(self, rules: dict):
        self.update_config(lambda cfg: cfg.__setitem__("rules", rules))

    # The old app kept the sidebar's state in config.json under these keys and applied it on every load
    # (shared by every device, since it lives with the data). Same keys, so both UIs read each other's.
    STATE_KEYS = {
        "min_date": "min_date",
        "max_date": "max_date",
        "categories_in": "categories in",
        "categories_not_in": "categories not in",
        "show_sql": "show_sql",
        "rules_button": "rules_button",
    }

    def state(self) -> dict:
        cfg = self.config()
        return {
            "min_date": cfg.get("min_date"),
            "max_date": cfg.get("max_date"),
            "categories_in": list(cfg.get("categories in") or []),
            "categories_not_in": list(cfg.get("categories not in") or []),
            "show_sql": bool(cfg.get("show_sql", False)),
            "rules_button": bool(cfg.get("rules_button", False)),
        }

    def update_state(self, updates: dict) -> dict:
        def apply(cfg):
            for key, value in updates.items():
                cfg[self.STATE_KEYS[key]] = value

        self.update_config(apply)
        return self.state()

    def accounts(self) -> list:
        """Linked Plaid accounts, without their access tokens (those never leave this process)."""
        return [
            {
                "alias": a.get("alias", k),
                "institution": a.get("institution"),
                "start_date": a.get("start_date"),
            }
            for k, a in (self.config().get("linked_accounts") or {}).items()
        ]

    # --- raw files and the pipeline ------------------------------------------------------------------

    def raw_files(self) -> list:
        if not self.raw_dir.is_dir():
            return []
        out = []
        for p in sorted(self.raw_dir.iterdir()):
            if p.is_file():
                st = p.stat()
                out.append(
                    {"name": p.name, "size": st.st_size, "modified": int(st.st_mtime)}
                )
        return out

    def save_uploads(self, files) -> dict:
        """files: (name, bytes) pairs. Keeps the ones that match a known card layout."""
        make_dirs([self.raw_dir])
        saved, failed = [], []
        for name, data in files:
            name = os.path.basename(name or "")
            if (
                not FILE_NAME.match(name)
                or name.startswith(".")
                or not name.lower().endswith(".csv")
            ):
                failed.append(f"{name or '(no name)'}: not a .csv file name")
                continue
            try:
                status, msg = save_file_if_valid(_Upload(name, data), str(self.dir))
            except (
                Exception
            ) as e:  # a CSV nobody has seen before can fail in any parser step
                failed.append(f"{name}: could not be read ({type(e).__name__})")
                continue
            if status == "success":
                saved.append(msg)
            else:
                failed.append(f"{msg}: not a layout of any known card")
        return {"saved": saved, "failed": failed}

    def delete_raw(self, name: str):
        if not FILE_NAME.match(name) or name.startswith("."):
            raise KeyError(name)
        path = self.raw_dir / name
        if not path.is_file():
            raise KeyError(name)
        path.unlink()

    def run_pipeline(self, rules_only: bool = False) -> dict:
        if not self._pipeline_lock.acquire(blocking=False):
            raise PipelineBusy()
        try:
            make_dirs([self.dir])
            start = time.monotonic()
            ran = run_pipeline(
                str(self.dir), standardize_only=rules_only, config=self.config()
            )
            return {
                "ran": bool(ran),
                "seconds": round(time.monotonic() - start, 1),
                "count": int(len(self.expenses())),
            }
        finally:
            self._pipeline_lock.release()


class _Upload:
    """What detect.save_file_if_valid wants of an upload: .name and .read()."""

    def __init__(self, name, data):
        self.name = name
        self._data = data

    def read(self):
        return self._data


class Stores:
    """UserStore per user, created on first use."""

    def __init__(self, data_root: Path):
        self.root = Path(data_root).resolve()
        self._stores = {}
        self._lock = threading.Lock()

    def get(self, user: str) -> UserStore:
        with self._lock:
            if user not in self._stores:
                path = (self.root / user).resolve()
                if (
                    path.parent != self.root
                ):  # settings only allow plain names; belt and braces
                    raise ValueError(f"bad user {user!r}")
                self._stores[user] = UserStore(path)
            return self._stores[user]
