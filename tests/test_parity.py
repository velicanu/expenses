"""The new charts and SQL box against what the OLD Streamlit app drew and built, scenario by scenario.

tests/golden/old_ui.json was captured from src/main.py itself (python tests/golden/make_golden.py), over the
synthetic data in tests/golden/synthetic.py. These tests rebuild the same data with the same pipeline and require
the same figures (data, colors, layout: everything the browser is sent) and the same SQL text, so "the numbers
and colors are the old ones" is checked, not claimed. The goldens stay valid after src/main.py is deleted.
"""

import base64
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
sys.path.insert(0, str(GOLDEN_DIR))

import synthetic  # noqa: E402

from server import figures, sqlview  # noqa: E402
from server.store import UserStore  # noqa: E402

GOLDEN = json.loads((GOLDEN_DIR / "old_ui.json").read_text())
SIDEBAR_WARNING = "invalid description, only one of + or ^ supported at a time"

# the widget values each sidebar scenario set (see make_golden.SCENARIOS)
SIDEBAR = {
    "side_dates": {"dates": (date(2024, 3, 1), date(2024, 9, 30))},
    "side_not_in_two": {"not_in": ["Income", "Payment"]},
    "side_in": {"in": ["Dining", "Groceries", "Rent"], "not_in": []},
    "side_description_or": {"description": "coffee+sweetgreen", "not_in": []},
    "side_description_and": {"description": "whole*market^!zzz", "not_in": []},
    "side_description_single_not": {"description": "!rent", "not_in": []},
    "side_description_invalid": {"description": "a+b^c"},
    "side_description_star": {"description": "air*lines", "not_in": []},
    "side_source": {"sources": ["chase.csv"], "not_in": []},
}


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    d = tmp_path_factory.mktemp("golden") / "golden"
    d.mkdir()
    synthetic.write(d)
    s = UserStore(d)
    assert s.run_pipeline()["ran"]
    return s


def normalize(x):
    """plotly 6 packs numeric arrays as {dtype, bdata}: unpack them, and round floats, so two figures compare."""
    if isinstance(x, dict):
        if set(x) >= {"dtype", "bdata"}:
            return normalize(
                np.frombuffer(
                    base64.b64decode(x["bdata"]), dtype=np.dtype(x["dtype"])
                ).tolist()
            )
        return {k: normalize(v) for k, v in x.items()}
    if isinstance(x, list):
        return [normalize(v) for v in x]
    if isinstance(x, float):
        return round(x, 6)
    return x


def widgets_default(store, overrides):
    """The sidebar as the old app builds it on load, then the scenario's changes."""
    state, meta = store.state(), store.meta()
    lo = max(
        date.fromisoformat(meta["min_date"]), date.fromisoformat(state["min_date"])
    )
    hi = min(
        date.fromisoformat(meta["max_date"]), date.fromisoformat(state["max_date"])
    )
    valid = set(meta["data_categories"])
    w = {
        "start": lo,
        "end": hi,
        "category_in": [c for c in state["categories_in"] if c in valid],
        "category_not_in": [c for c in state["categories_not_in"] if c in valid],
        "description": "",
        "sources": [],
    }
    if "dates" in overrides:
        w["start"], w["end"] = overrides["dates"]
    if "in" in overrides:
        w["category_in"] = overrides["in"]
    if "not_in" in overrides:
        w["category_not_in"] = overrides["not_in"]
    if "description" in overrides:
        w["description"] = overrides["description"]
    if "sources" in overrides:
        w["sources"] = overrides["sources"]
    return w


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_the_sql_the_sidebar_builds_is_the_old_sql(store, name):
    w = widgets_default(store, SIDEBAR.get(name, {}))
    query, warning = sqlview.default_query(
        store.sql_frame(),
        w["start"],
        w["end"],
        w["category_in"],
        w["category_not_in"],
        w["description"],
        w["sources"],
    )
    assert query == GOLDEN[name]["default_sql"]
    assert (warning == SIDEBAR_WARNING) == (
        SIDEBAR_WARNING in GOLDEN[name]["sidebar_warnings"]
    )


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_the_charts_are_the_old_charts(store, name):
    g = GOLDEN[name]
    query = g["sql"] or g["default_sql"]
    df = sqlview.run_query(store.sql_frame(), query)
    new_categories = store.rules()["new_categories"]
    if df.empty:
        assert g["figures"] == [], "the old app drew charts for an empty selection"
        assert "Current selection is empty." in g["main_warnings"]
        return
    pie = figures.category_chart(df, new_categories)["figure"]
    bars = figures.over_time_chart(df, new_categories, g["group"])["figure"]
    assert len(g["figures"]) == 2
    assert normalize(pie) == normalize(g["figures"][0]), (
        f"{name}: the pie differs from the old app's"
    )
    assert normalize(bars) == normalize(g["figures"][1]), (
        f"{name}: the bars differ from the old app's"
    )


def test_the_category_table_and_total(store):
    g = GOLDEN["default"]
    df = sqlview.run_query(store.sql_frame(), g["default_sql"])
    out = figures.category_chart(df, store.rules()["new_categories"])
    assert out["total"] == pytest.approx(float(df["amount"].sum()))
    assert [r["category"] for r in out["table"]] == sorted(df["category"].unique())
    assert f"total: {out['total']:.2f}" in out["figure"]["layout"]["title"]["text"]


def test_unmapped_categories_get_plotly_express_colors_like_before(store):
    """Payment and Mystery are in neither color map: the old app left their color to Plotly Express."""
    g = GOLDEN["all_data"]
    pie = normalize(g["figures"][0])["data"][0]
    colors = dict(zip(pie["labels"], pie["marker"]["colors"], strict=True))
    assert "Payment" in colors and "Mystery" in colors
    df = sqlview.run_query(store.sql_frame(), "SELECT * FROM expenses")
    ours = normalize(
        figures.category_chart(df, store.rules()["new_categories"])["figure"]
    )["data"][0]
    assert dict(zip(ours["labels"], ours["marker"]["colors"], strict=True)) == colors
    assert (
        colors["Income"] == "#00ff00" and colors["Rent"] == "#636EFA"
    )  # custom and mapped, as before
