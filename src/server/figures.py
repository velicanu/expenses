"""The two charts, built with the same Plotly Express calls the Streamlit app used (src/main.py:
add_spending_by_category and add_spending_over_time), so the numbers, colors and layout are the old ones.
tests/test_parity.py compares them with what the old app drew, captured from the real thing.

The browser draws them with plotly.js (web/): plotly.py 6.5.2 emits what plotly.js 3.3.1 reads.
"""

import json
import warnings
from pathlib import Path

import dateutil.parser
import pandas as pd
import plotly.express as px

# the old app's fixed colors, by category (Plotly's and D3's qualitative palettes)
COLOR_DISCRETE_MAP = {
    "Rent": px.colors.qualitative.Plotly[0],
    "Shopping": px.colors.qualitative.Plotly[1],
    "Family": px.colors.qualitative.Plotly[2],
    "Dining": px.colors.qualitative.Plotly[3],
    "Travel": px.colors.qualitative.Plotly[4],
    "Groceries": px.colors.qualitative.Plotly[5],
    "Bills": px.colors.qualitative.Plotly[6],
    "Entertainment": px.colors.qualitative.Plotly[7],
    "Other": px.colors.qualitative.Plotly[8],
    "Car": px.colors.qualitative.Plotly[9],
    "Rideshare": px.colors.qualitative.D3[0],
    "Fees": px.colors.qualitative.D3[1],
    "Health": px.colors.qualitative.D3[2],
    "Services": px.colors.qualitative.D3[3],
}

# Streamlit's own Plotly template, as the old app's figures carried it (captured from them). Its colors are
# placeholders (#000001..#000010 ...) that Streamlit's browser code swaps for its theme palette: the colors of
# any category that has no color of its own come from there. The browser side (web/src/streamlitTheme.ts) does
# the same swap, so those colors are the old ones too.
STREAMLIT_TEMPLATE = json.loads(
    (Path(__file__).parent / "streamlit_plotly_template.json").read_text()
)

GROUPING = {"auto": "", "year": "YS", "month": "MS", "week": "W", "day": "D"}
GROUP_TITLES = {
    "YS": "Yearly spending",
    "MS": "Monthly spending",
    "W": "Weekly spending",
    "D": "Daily spending",
}


def _json(fig) -> dict:
    return json.loads(fig.to_json())


def category_chart(df: pd.DataFrame, new_categories: dict) -> dict:
    """Left: the category table. Right: the pie. `df` is the result of the query."""
    if "category" not in df or "amount" not in df:
        return {
            "message": "Missing category or amount columns.",
            "total": None,
            "table": [],
            "figure": None,
        }

    df2 = df.groupby(["category"], as_index=False)["amount"].agg("sum")
    total = df["amount"].sum()
    cdm = {**COLOR_DISCRETE_MAP, **new_categories}

    fig = px.pie(
        df2,
        values="amount",
        names="category",
        title=f"Spending by category, total: {total:.2f}",
        height=600,
        color="category",
        color_discrete_map=cdm,
        template=STREAMLIT_TEMPLATE,
    )
    fig.update_traces(textinfo="label+value")
    fig.update_layout(
        font={"size": 18, "color": "#7f7f7f"},
        title={"xanchor": "center", "x": 0.5},
    )
    return {
        "message": None,
        "total": float(total),
        "table": [
            {"category": r.category, "amount": float(r.amount)}
            for r in df2.itertuples()
        ],
        "figure": _json(fig),
    }


def resolve_group(df: pd.DataFrame, group_selection: str) -> str:
    """pandas frequency for the bars: the app's thresholds for 'auto', or the chosen bin."""
    max_date = dateutil.parser.parse(df["date"].max())
    min_date = dateutil.parser.parse(df["date"].min())
    n_days = (max_date - min_date).days
    if n_days >= 730:  # 2+ years
        group = "YS"
    elif n_days > 91:
        group = "MS"
    elif n_days > 31:
        group = "W"
    else:
        group = "D"
    return group if group_selection == "auto" else GROUPING[group_selection]


def over_time_chart(
    df: pd.DataFrame, new_categories: dict, group_selection: str = "auto"
) -> dict:
    if "date" not in df or "amount" not in df:
        return {
            "message": "Missing date or amount columns.",
            "group": group_selection,
            "figure": None,
        }
    if group_selection not in GROUPING:
        raise ValueError(f"unknown time bin {group_selection!r}")

    group = resolve_group(df, group_selection)
    df = df.set_index(pd.DatetimeIndex(df["date"]))
    with warnings.catch_warnings():
        # the old code resamples the grouping column too (pandas warns); the result is what the app drew
        warnings.simplefilter("ignore", FutureWarning)
        df_month = (
            df.groupby("category")
            .resample(group)
            .sum()
            .rename(columns={"date": "_date", "category": "_category"})
            .reset_index()
        )

    # totals per time bin, for the annotations above the bars
    df_totals = df_month.groupby("date")["amount"].sum().reset_index()

    fig = px.bar(
        df_month,
        x="date",
        y="amount",
        color="category",
        color_discrete_map={**COLOR_DISCRETE_MAP, **new_categories},
        template=STREAMLIT_TEMPLATE,
    )
    for _, row in df_totals.iterrows():
        fig.add_annotation(
            x=row["date"],
            y=row["amount"],
            text=f"{row['amount']:.0f}",
            showarrow=False,
            yshift=10,
            font={"size": 11},
        )
    fig.update_layout(
        title=GROUP_TITLES[group],
        xaxis_title="Date",
        yaxis_title="Amount",
    )
    fig.update_layout(
        font={"size": 16, "color": "#7f7f7f"},
        title={"xanchor": "center", "x": 0.5},
    )
    return {"message": None, "group": group_selection, "figure": _json(fig)}
