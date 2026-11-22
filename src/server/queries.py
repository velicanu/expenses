"""Filtering and summaries over the expenses frame. Pure pandas, no I/O and no SQL strings.

(The Streamlit app built SQL by pasting the description box into a LIKE '%...%'; this does the same job on
the frame, so there is nothing to inject into.)
"""

import re
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

BINS = {"year": "YS", "month": "MS", "week": "W", "day": "D"}
SORTABLE = {"date", "amount", "category", "description", "source"}


@dataclass
class Filters:
    start: date | None = None
    end: date | None = None
    category_in: list = field(default_factory=list)
    category_not_in: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    description: str = ""


def description_mask(series: pd.Series, expr: str) -> pd.Series:
    """The description box. `a+b` is a or b, `a^b` is a and b (not both kinds at once), `!a` is not a, and
    `*` matches anything. Case-insensitive; every other character is literal."""
    expr = expr.strip()
    if not expr:
        return pd.Series(True, index=series.index)
    if "+" in expr and "^" in expr:
        raise ValueError("use either + (or) or ^ (and) in the description, not both")
    op = "+" if "+" in expr else "^" if "^" in expr else None
    terms = [t.strip() for t in (expr.split(op) if op else [expr])]
    masks = []
    for term in terms:
        negate = term.startswith("!")
        term = term[1:] if negate else term
        if not term:
            continue
        pattern = ".*".join(re.escape(p) for p in term.split("*"))
        hit = series.str.contains(pattern, case=False, regex=True, na=False)
        masks.append(~hit if negate else hit)
    if not masks:
        return pd.Series(True, index=series.index)
    out = masks[0]
    for m in masks[1:]:
        out = (out | m) if op == "+" else (out & m)
    return out


def apply_filters(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    if f.start:
        mask &= df["ts"] >= pd.Timestamp(f.start)
    if f.end:
        mask &= df["ts"] < pd.Timestamp(f.end) + pd.Timedelta(
            days=1
        )  # the end day is included
    if f.category_in:
        mask &= df["category"].isin(f.category_in)
    if f.category_not_in:
        mask &= ~df["category"].isin(f.category_not_in)
    if f.sources:
        mask &= df["source_file"].isin(f.sources)
    mask &= description_mask(df["description"].astype(str), f.description)
    return df[mask]


def page(
    df: pd.DataFrame, sort: str, descending: bool, offset: int, limit: int
) -> pd.DataFrame:
    if sort not in SORTABLE:
        raise ValueError(f"cannot sort by {sort!r}")
    key = "ts" if sort == "date" else sort
    out = df.sort_values([key, "pk"], ascending=[not descending, True], kind="stable")
    return out.iloc[offset : offset + limit]


def by_category(df: pd.DataFrame) -> dict:
    sums = df.groupby("category")["amount"].sum().sort_values()
    return {
        "total": round(float(df["amount"].sum()), 2),
        "categories": [
            {"category": c, "amount": round(float(v), 2)} for c, v in sums.items()
        ],
    }


def auto_bin(df: pd.DataFrame) -> str:
    if df.empty:
        return "month"
    days = (df["ts"].max() - df["ts"].min()).days
    if days >= 730:
        return "year"
    if days > 91:
        return "month"
    if days > 31:
        return "week"
    return "day"


def over_time(df: pd.DataFrame, bin_: str = "auto") -> dict:
    if bin_ != "auto" and bin_ not in BINS:
        raise ValueError(f"unknown bin {bin_!r}")
    chosen = auto_bin(df) if bin_ == "auto" else bin_
    if df.empty:
        return {"bin": chosen, "categories": [], "periods": []}
    grouped = (
        df.groupby([pd.Grouper(key="ts", freq=BINS[chosen]), "category"])["amount"]
        .sum()
        .reset_index()
    )
    grouped = grouped[grouped["amount"] != 0]
    periods = []
    for ts, rows in grouped.groupby("ts"):
        values = {r.category: round(float(r.amount), 2) for r in rows.itertuples()}
        periods.append(
            {
                "period": ts.date().isoformat(),
                "total": round(sum(values.values()), 2),
                "values": values,
            }
        )
    return {
        "bin": chosen,
        "categories": sorted(grouped["category"].unique()),
        "periods": periods,
    }
