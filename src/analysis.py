"""Analysis."""
import streamlit as st
import plotly.express as px
import pandas as pd


def add_spending_by_category(df):
    if "category" not in df or "amount" not in df:
        st.markdown("**Spending by category**")
        st.markdown("Missing category or amount columns.")
        return

    df2 = df.groupby(["category"], as_index=False)["amount"].agg("sum")

    total = df["amount"].sum()

    fig = px.pie(
        df2,
        values="amount",
        names="category",
        title=f"Spending by category, total: {total}",
        height=600,
        color="category",
        color_discrete_map=color_discrete_map,
    )

    fig.update_layout(
        font=dict(size=18, color="#7f7f7f"),
        title={"xanchor": "center", "x": 0.5},
    )

    st.plotly_chart(fig, use_container_width=True)


def add_spending_over_time(df):
    if "date" not in df or "amount" not in df:
        st.markdown("**Spending over time**")
        st.markdown("Missing date or amount columns.")
        return

    df = df.set_index(pd.DatetimeIndex(df["date"]))
    df_month = df.groupby("category").resample("M").sum().reset_index()

    fig2 = px.bar(
        df_month,
        x="date",
        y="amount",
        color="category",
        color_discrete_map=color_discrete_map,
    )
    fig2.update_layout(
        title="Spending over time",
        xaxis_title="Date",
        yaxis_title="Amount",
    )
    fig2.update_layout(
        font=dict(size=16, color="#7f7f7f"),
        title={"xanchor": "center", "x": 0.5},
    )
    st.plotly_chart(fig2, use_container_width=True)
