import pandas as pd

from analysis import (
    flag_high_dining,
    flag_recurring_in_catchall,
    identify_frequent_merchants,
    identify_recurring,
    monthly_outliers,
    normalize_merchant,
)


def test_normalize_merchant():
    s = pd.Series(["NETFLIX 12345", "  Lyft   *RIDE  ", "Trader Joe's"])
    out = normalize_merchant(s)
    assert out.iloc[0] == "netflix"
    assert "lyft" in out.iloc[1]
    assert out.iloc[2].startswith("trader")


def test_identify_recurring():
    # 3 transactions ~30 days apart, same amount -> recurring (subscription)
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-02-01", "2024-03-01"],
            "description": ["NETFLIX 123", "NETFLIX 456", "NETFLIX 789"],
            "category": ["Entertainment"] * 3,
            "amount": [15.0, 15.0, 15.0],
        }
    )
    out = identify_recurring(df, min_occurrences=3, interval_tolerance_days=7)
    assert len(out) == 1
    assert out.iloc[0]["transaction_count"] == 3
    assert out.iloc[0]["mean_interval_days"] >= 25


def test_identify_frequent_merchants():
    # 3 transactions ~30 days apart but varying amounts -> frequent, not recurring
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-02-01", "2024-03-01"],
            "description": ["COFFEE SHOP A", "COFFEE SHOP B", "COFFEE SHOP C"],
            "category": ["Dining"] * 3,
            "amount": [5.0, 12.0, 8.0],
        }
    )
    recurring = identify_recurring(df, min_occurrences=3, interval_tolerance_days=7)
    frequent = identify_frequent_merchants(
        df, min_occurrences=3, exclude_recurring=True
    )
    assert len(recurring) == 0
    assert len(frequent) == 1
    assert frequent.iloc[0]["transaction_count"] == 3


def test_flag_high_dining():
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "description": ["Fancy Restaurant", "Coffee Shop"],
            "category": ["Dining", "Dining"],
            "amount": [150.0, 8.0],
        }
    )
    out = flag_high_dining(df, threshold=100)
    assert len(out) == 1
    assert out.iloc[0]["amount"] == 150.0
    assert out.iloc[0]["category"] == "Dining"


def test_flag_recurring_in_catchall():
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-02-01"],
            "description": ["SOME MERCHANT 123", "SOME MERCHANT 456"],
            "category": ["Other", "Other"],
            "amount": [10.0, 10.0],
        }
    )
    out = flag_recurring_in_catchall(df, min_occurrences=2)
    assert len(out) >= 1
    assert out.iloc[0]["transaction_count"] == 2


def test_monthly_outliers_by_category():
    # One month much higher than others
    df = pd.DataFrame(
        {
            "date": ["2024-01-15", "2024-02-15", "2024-03-15", "2024-04-15"],
            "description": ["A", "A", "A", "A"],
            "category": ["Shopping", "Shopping", "Shopping", "Shopping"],
            "amount": [100.0, 100.0, 100.0, 500.0],
        }
    )
    out = monthly_outliers(df, group_by="category", method="iqr", k=1.5)
    assert not out.empty
    high = out[out["is_high_outlier"]]
    assert len(high) >= 1
    assert high.iloc[0]["monthly_amount"] == 500.0
