"""
Analysis helpers for expense data: recurring expenses, high dining,
recurring in catchall categories, and monthly outliers.
"""

import re
from typing import Sequence

import pandas as pd


def normalize_merchant(description_series: pd.Series, max_words: int = 4) -> pd.Series:
    """Normalize description to a stable merchant key for grouping."""
    def _norm(s):
        if pd.isna(s) or not isinstance(s, str):
            return ""
        s = s.lower().strip()
        s = re.sub(r"\s+", " ", s)
        # Drop trailing alphanumeric IDs (e.g. "NETFLIX 12345" -> "netflix")
        s = re.sub(r"\s*[\dA-Za-z]{6,}\s*$", "", s)
        # Drop trailing space + digits so "netflix 1" / "netflix 2" -> "netflix"
        s = re.sub(r"\s+\d+$", "", s)
        # Drop trailing space + short alphanumeric so "coffee a" / "coffee b" -> "coffee"
        s = re.sub(r"\s+[a-z0-9]+$", "", s)
        words = s.split()[:max_words]
        return " ".join(words).strip() or s[:50]

    return description_series.apply(_norm)


def _merchant_groups_with_schedule(
    df: pd.DataFrame,
    min_occurrences: int,
    interval_tolerance_days: int,
    normalize_description: bool,
) -> pd.DataFrame:
    """Group by merchant, keep only those with roughly monthly schedule. No amount constraint."""
    if df.empty or "date" not in df.columns or "description" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    if normalize_description:
        df["merchant"] = normalize_merchant(df["description"])
    else:
        df["merchant"] = df["description"].fillna("").astype(str)
    df = df[df["amount"] > 0]

    out = []
    for merchant, grp in df.groupby("merchant"):
        if merchant == "" or len(grp) < min_occurrences:
            continue
        dates = grp["date"].sort_values()
        deltas = dates.diff().dt.days.dropna()
        if deltas.empty:
            continue
        mean_interval = deltas.mean()
        if abs(mean_interval - 30) <= interval_tolerance_days or (
            mean_interval >= 25 and mean_interval <= 35
        ):
            out.append({
                "merchant": merchant,
                "transaction_count": len(grp),
                "mean_interval_days": round(mean_interval, 1),
                "last_date": dates.max().isoformat()[:10],
                "total_amount": round(grp["amount"].sum(), 2),
                "mean_amount": round(grp["amount"].mean(), 2),
            })
    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out)


def identify_recurring(
    df: pd.DataFrame,
    min_occurrences: int = 3,
    interval_tolerance_days: int = 7,
    normalize_description: bool = True,
    same_amount_ratio_threshold: float = 0.8,
) -> pd.DataFrame:
    """Recurring expenses / subscriptions: roughly monthly and same amount in >80% of cases."""
    scheduled = _merchant_groups_with_schedule(
        df, min_occurrences, interval_tolerance_days, normalize_description
    )
    if scheduled.empty:
        return pd.DataFrame()

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    if normalize_description:
        df["merchant"] = normalize_merchant(df["description"])
    else:
        df["merchant"] = df["description"].fillna("").astype(str)
    df = df[df["amount"] > 0]

    out = []
    for _, row in scheduled.iterrows():
        merchant = row["merchant"]
        grp = df[df["merchant"] == merchant]
        amounts = grp["amount"].round(2)
        # Most common amount (mode)
        mode_count = amounts.value_counts().iloc[0]
        if mode_count / len(grp) >= same_amount_ratio_threshold:
            out.append(row)

    if not out:
        return pd.DataFrame()
    result = pd.DataFrame(out)
    return result.sort_values("total_amount", ascending=False).reset_index(drop=True)


def identify_frequent_merchants(
    df: pd.DataFrame,
    min_occurrences: int = 3,
    interval_tolerance_days: int = 7,
    normalize_description: bool = True,
    exclude_recurring: bool = True,
    same_amount_ratio_threshold: float = 0.8,
) -> pd.DataFrame:
    """Frequent merchants: roughly monthly but varying amounts (not same charge every time)."""
    scheduled = _merchant_groups_with_schedule(
        df, min_occurrences, interval_tolerance_days, normalize_description
    )
    if scheduled.empty:
        return pd.DataFrame()

    if not exclude_recurring:
        return scheduled.sort_values("total_amount", ascending=False).reset_index(drop=True)

    df = df.copy()
    if normalize_description:
        df["merchant"] = normalize_merchant(df["description"])
    else:
        df["merchant"] = df["description"].fillna("").astype(str)
    df = df[df["amount"] > 0]

    out = []
    for _, row in scheduled.iterrows():
        merchant = row["merchant"]
        grp = df[df["merchant"] == merchant]
        amounts = grp["amount"].round(2)
        mode_count = amounts.value_counts().iloc[0]
        if mode_count / len(grp) < same_amount_ratio_threshold:
            out.append(row)

    if not out:
        return pd.DataFrame()
    result = pd.DataFrame(out)
    return result.sort_values("total_amount", ascending=False).reset_index(drop=True)


def flag_high_dining(
    df: pd.DataFrame,
    category: str = "Dining",
    threshold: float = 100.0,
) -> pd.DataFrame:
    """Flag dining expenses over a threshold (default 100)."""
    if df.empty or "category" not in df.columns or "amount" not in df.columns:
        return pd.DataFrame()
    subset = df[(df["category"] == category) & (df["amount"].abs() > threshold)]
    return subset[["date", "description", "amount", "category"]].copy()


def flag_recurring_in_catchall(
    df: pd.DataFrame,
    catchall_categories: Sequence[str] = ("Other", "Transfer"),
    min_occurrences: int = 2,
) -> pd.DataFrame:
    """Flag recurring merchants in catchall categories (Other, Transfer)."""
    if df.empty or "category" not in df.columns or "description" not in df.columns:
        return pd.DataFrame()

    subset = df[df["category"].isin(catchall_categories)].copy()
    if subset.empty:
        return pd.DataFrame()

    subset["merchant"] = normalize_merchant(subset["description"])
    subset = subset[subset["merchant"] != ""]

    grp = subset.groupby(["merchant", "category"]).agg(
        transaction_count=("amount", "count"),
        total_amount=("amount", "sum"),
        date_min=("date", "min"),
        date_max=("date", "max"),
    ).reset_index()

    grp = grp[grp["transaction_count"] >= min_occurrences]
    grp["total_amount"] = grp["total_amount"].round(2)
    return grp.sort_values("total_amount", ascending=False).reset_index(drop=True)


def monthly_outliers(
    df: pd.DataFrame,
    group_by: str = "category",
    method: str = "iqr",
    k: float = 1.5,
    min_periods: int = 2,
    freq: str = "M",
) -> pd.DataFrame:
    """
    Identify outliers by time period: by category or by (normalized) merchant.
    freq: pandas period code for grouping ('M'=month, 'W'=week, 'Y'=year, 'D'=day).
    method: 'iqr' (Q1 - k*IQR, Q3 + k*IQR) or 'zscore' (|z| > 2).
    """
    if df.empty or "date" not in df.columns or "amount" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["period"] = df["date"].dt.to_period(freq).astype(str)
    df = df[df["amount"] > 0]

    if group_by == "merchant":
        df["merchant"] = normalize_merchant(df["description"])
        group_cols = ["period", "merchant"]
        name_col = "merchant"
    else:
        if "category" not in df.columns:
            return pd.DataFrame()
        group_cols = ["period", "category"]
        name_col = "category"

    agg = (
        df.groupby(group_cols)["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "period_amount"})
    )

    n_periods = agg["period"].nunique()
    if n_periods < min_periods:
        return pd.DataFrame()

    out = []
    for key, grp in agg.groupby(name_col):
        vals = grp["period_amount"]
        if len(vals) < min_periods:
            continue
        if method == "iqr":
            q1, q3 = vals.quantile(0.25), vals.quantile(0.75)
            iqr = q3 - q1
            lo, hi = q1 - k * iqr, q3 + k * iqr
        else:
            mean, std = vals.mean(), vals.std()
            if std == 0:
                continue
            lo = mean - 2 * std
            hi = mean + 2 * std

        for _, row in grp.iterrows():
            amt = row["period_amount"]
            if amt < lo or amt > hi:
                out.append({
                    "period": row["period"],
                    name_col: key,
                    "period_amount": round(amt, 2),
                    "is_high_outlier": amt > hi,
                })

    if not out:
        return pd.DataFrame()
    result = pd.DataFrame(out)
    result = result.sort_values(["period", "period_amount"], ascending=[True, False])
    return result.rename(columns={"period_amount": "monthly_amount", "period": "month"})
