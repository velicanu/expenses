"""Regenerates the golden files from the OLD Streamlit app (src/main.py). Needs streamlit installed.

    python tests/golden/make_golden.py

It builds the synthetic data dir with the pipeline, runs the real old app over it with Streamlit's AppTest
for each scenario, and saves what the app drew (the plotly figures as it sent them to the browser) and the
SQL its sidebar built. tests/test_parity.py checks that src/server/figures.py and sqlview.py give the same.
"""

import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import synthetic  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from server.store import UserStore  # noqa: E402

USER = "golden"
DATA = ROOT / "data" / USER  # where src/main.py looks: <repo>/data/<EXPENSES_USER>

# name -> (sql override or None, time bin or None, sidebar widget setup)
SCENARIOS = {
    "default": (None, None, {}),
    "default_week": (None, "week", {}),
    "default_year": (None, "year", {}),
    "default_day": (None, "day", {}),
    "all_data": ("SELECT * FROM expenses", None, {}),
    "all_data_month": ("SELECT * FROM expenses", "month", {}),
    "coffee_sql": (
        "SELECT * FROM expenses WHERE description LIKE '%coffee%'",
        None,
        {},
    ),
    "empty": ("SELECT * FROM expenses WHERE 1=0", None, {}),
    "side_dates": (None, None, {"dates": (date(2024, 3, 1), date(2024, 9, 30))}),
    "side_not_in_two": (None, None, {"not_in": ["Income", "Payment"]}),
    "side_in": (None, None, {"in": ["Dining", "Groceries", "Rent"], "not_in": []}),
    "side_description_or": (
        None,
        None,
        {"description": "coffee+sweetgreen", "not_in": []},
    ),
    "side_description_and": (
        None,
        None,
        {"description": "whole*market^!zzz", "not_in": []},
    ),
    "side_description_single_not": (None, None, {"description": "!rent", "not_in": []}),
    "side_description_invalid": (None, None, {"description": "a+b^c"}),
    "side_description_star": (None, None, {"description": "air*lines", "not_in": []}),
    "side_source": (None, None, {"sources": ["chase.csv"], "not_in": []}),
}


def figures(at):
    out = []
    for el in at.get("plotly_chart"):
        out.append(json.loads(el.proto.spec or el.proto.figure.spec))
    return out


def run(name, sql, group, widgets):
    os.environ["EXPENSES_USER"] = USER
    at = AppTest.from_file(str(ROOT / "src" / "main.py"), default_timeout=180)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    if widgets:
        side = at.sidebar
        by_label = {
            w.label: w
            for w in list(side.multiselect)
            + list(side.text_input)
            + list(side.date_input)
        }
        if "dates" in widgets:
            by_label["Date range"].set_value(widgets["dates"])
        if "in" in widgets:
            by_label["Categories in"].set_value(widgets["in"])
        if "not_in" in widgets:
            by_label["Categories not in"].set_value(widgets["not_in"])
        if "description" in widgets:
            by_label["Description"].set_value(widgets["description"])
        if "sources" in widgets:
            by_label["Source file"].set_value(widgets["sources"])
        side.button[0].click()  # the form's Submit
        at.run()
        assert not at.exception, [e.value for e in at.exception]
    sql_box = next(t for t in at.text_input if t.label == "Input sql")
    default_sql = sql_box.value
    if sql:
        sql_box.set_value(sql)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
    if group:
        at.select_slider[0].set_value(group)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
    warnings = (
        [w.value for w in at.sidebar.warning] if hasattr(at.sidebar, "warning") else []
    )
    return {
        "default_sql": default_sql,
        "sql": sql,
        "group": group or "auto",
        "figures": figures(at),
        "main_warnings": [w.value for w in at.warning],
        "sidebar_warnings": warnings,
        "table": [
            df.value.to_dict(orient="records") for df in at.get("arrow_data_frame")
        ][-1:]
        if at.get("arrow_data_frame")
        else [],
    }


def main():
    if DATA.exists():
        shutil.rmtree(DATA)
    DATA.mkdir(parents=True)
    synthetic.write(DATA)
    store = UserStore(DATA)
    assert store.run_pipeline()["ran"]
    original_config = (DATA / "config.json").read_text()
    golden = {}
    for name, (sql, group, widgets) in SCENARIOS.items():
        (DATA / "config.json").write_text(
            original_config
        )  # the old app rewrites it on every run
        golden[name] = run(name, sql, group, widgets)
        print(
            f"{name:30} figures={len(golden[name]['figures'])} default_sql={golden[name]['default_sql'][:90]!r}"
        )
    (HERE / "old_ui.json").write_text(json.dumps(golden, indent=1, sort_keys=True))
    shutil.rmtree(DATA)  # was under the gitignored <repo>/data
    print("wrote", HERE / "old_ui.json")


if __name__ == "__main__":
    main()
