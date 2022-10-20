import pandas as pd

from utils import apply_changes


def test_apply_changes():
    df_initial = pd.DataFrame(
        [
            {"a": 123, "b": "abc", "pk": 1},
            {"a": 456, "b": "def", "pk": 2},
            {"a": 789, "b": "ghi", "pk": 3},
        ]
    )
    df_changes = pd.DataFrame(
        [
            {"a": 999, "b": "zzz", "pk": 2},
            {"a": 444, "b": "fff", "pk": 4},
        ]
    )
    actual_df = apply_changes(df_initial, df_changes)
    actual = sorted(actual_df.to_dict(orient="records"), key=lambda x: x["pk"])
    expected = [
        {"a": 123, "b": "abc", "pk": 1},
        {"a": 999, "b": "zzz", "pk": 2},
        {"a": 789, "b": "ghi", "pk": 3},
        {"a": 444, "b": "fff", "pk": 4},
    ]
    assert actual == expected
