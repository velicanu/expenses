import base64
import os
import sqlite3

import dateutil.parser
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Needed for st.State() , TODO: remove when streamlit supports it natively
import st_state_patch

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
RAW_DATA_DIR = os.path.join(SCRIPT_DIR, "data", "raw")
state = st.State()
if not state:
    state.delete_files = set()

conn = sqlite3.connect("data/expenses.db")


def extend_sql_statement(statement):
    return (
        statement + " WHERE "
        if " where " not in statement.lower()
        else statement + " AND "
    )


def add_date_range_widget(df):
    min_ = dateutil.parser.parse(df["date"].min())
    max_ = dateutil.parser.parse(df["date"].max())
    date_range = st.sidebar.date_input(
        "Date range", value=(min_, max_), min_value=min_, max_value=max_
    )
    min_ = min_.isoformat().replace("T00:00:00", "")
    max_ = max_.isoformat().replace("T00:00:00", "")
    min_selected = date_range[0].isoformat()
    max_selected = date_range[1].isoformat() if len(date_range) == 2 else None

    default_user_input = "SELECT * FROM expenses"

    if min_selected != min_:
        default_user_input = (
            extend_sql_statement(default_user_input) + f'date >= "{min_selected}"'
        )
    if max_selected and max_selected != max_:
        default_user_input = (
            extend_sql_statement(default_user_input) + f'date <= "{max_selected}"'
        )
    return default_user_input


def add_category_widget(df, default_user_input):
    selected = st.sidebar.multiselect("Categories", df["category"].unique())
    if selected:
        default_user_input = extend_sql_statement(default_user_input) + "category in "
        default_user_input = (
            default_user_input + f"{tuple(c for c in selected)}"
            if len(selected) > 1
            else default_user_input + f"('{selected[0]}')"
        )
    return default_user_input


def add_description_widget(default_user_input):
    title = st.sidebar.text_input("Description", "")
    return (
        extend_sql_statement(default_user_input) + f"description LIKE '%{title}%'"
        if title
        else default_user_input
    )


def add_include_payment_widget(default_user_input):
    if not st.sidebar.checkbox("Include Payments"):
        return extend_sql_statement(default_user_input) + "category != 'Payment'"
    return default_user_input


def add_download_csv_widget(df):
    if st.sidebar.button("Download csv"):
        csv = df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        st.sidebar.markdown(
            f'<a href="data:file/csv;base64,{b64}">Download csv file</a>',
            unsafe_allow_html=True,
        )


def add_delete_files_widget():
    if st.sidebar.checkbox("Delete files"):
        if st.sidebar.checkbox("Confirm delete files"):
            # This is where saving state is needed, to know which files are checked below
            for filename in state.delete_files:
                os.remove(filename)

        for file_ in os.listdir(RAW_DATA_DIR):
            filename = os.path.join(RAW_DATA_DIR, file_)
            if st.sidebar.checkbox(f"Delete {file_}"):
                state.delete_files.add(filename)
            else:
                try:
                    state.delete_files.remove(filename)
                except KeyError:
                    pass


def init():
    df_initial = pd.read_sql("SELECT * FROM expenses", conn)
    default_user_input = add_date_range_widget(df_initial)
    default_user_input = add_category_widget(df_initial, default_user_input)
    default_user_input = add_description_widget(default_user_input)
    default_user_input = add_include_payment_widget(default_user_input)

    if st.sidebar.checkbox("Show sql"):
        user_input = st.text_input("label goes here", default_user_input)
        df = pd.read_sql(user_input, conn)
        st.dataframe(df)
    else:
        df = pd.read_sql(default_user_input, conn)

    add_download_csv_widget(df)
    add_delete_files_widget()

    max_width_str = f"max-width: 1080px;"
    st.markdown(
        f"""
    <style>
    .reportview-container .main .block-container{{
        {max_width_str}
    }}
    </style>
    """,
        unsafe_allow_html=True,
    )
    return df


def add_spending_by_category(df):
    fig = px.pie(
        df, values="amount", names="category", title="Spending by category", height=600,
    )
    fig.update_layout(
        font=dict(size=18, color="#7f7f7f"), title={"xanchor": "center", "x": 0.5},
    )

    st.plotly_chart(fig, use_container_width=True)


def add_spending_over_time(df):
    df = df.set_index(pd.DatetimeIndex(df["date"]))
    df_month = df.resample("M").sum()
    df_month["date"] = df_month.index

    fig2 = go.Figure()
    fig2.add_trace(
        go.Scatter(
            x=df_month["date"],
            y=df_month["amount"],
            mode="lines+markers",
            name="lines+markers",
        )
    )
    fig2.update_layout(
        title="Spending over time", xaxis_title="Date", yaxis_title="Amount",
    )
    fig2.update_layout(
        font=dict(size=16, color="#7f7f7f"), title={"xanchor": "center", "x": 0.5},
    )
    st.plotly_chart(fig2, use_container_width=True)


def main():
    df = init()
    add_spending_by_category(df)
    add_spending_over_time(df)


if __name__ == "__main__":
    main()
