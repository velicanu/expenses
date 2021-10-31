import base64
import os
import sqlite3
import time

import dateutil.parser
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit.report_thread import get_report_ctx
from streamlit.server.server import Server

from detect import save_file_if_valid
from pipeline import run

st.set_page_config(
    page_title="Expense app",
    page_icon="src/static/favicon.ico",
    layout="wide",
    initial_sidebar_state="expanded",
)


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


def delete_files():
    for filename in st.session_state.delete_files:
        os.remove(filename)
    st.session_state.delete_files = set()


def add_delete_files_widget(raw_data_dir):
    if "delete_files" not in st.session_state:
        st.session_state.delete_files = set()

    if st.sidebar.checkbox("Delete files"):
        for file_ in os.listdir(raw_data_dir):
            filename = os.path.join(raw_data_dir, file_)
            if st.sidebar.checkbox(f"Delete {file_}"):
                st.session_state.delete_files.add(filename)
            else:
                try:
                    st.session_state.delete_files.remove(filename)
                except KeyError:
                    pass
        if st.session_state.delete_files:
            st.sidebar.button("Confirm Delete", on_click=delete_files)


def save_files_to_disk(files, data_dir):
    success = []
    failed = []
    for file_ in files:
        status, msg = save_file_if_valid(file_, data_dir)
        if status == "success":
            success.append(msg)
        else:
            failed.append(msg)

    if success:
        st.sidebar.success("Saved: " + " ".join(success))
        run(data_dir)
    if failed:
        st.sidebar.error("Failed: " + " ".join(failed))

    # this key increment clears the upload dialog box after clicking upload
    st.session_state.file_uploader_key += 1


def add_upload_files_widget(data_dir):
    if "file_uploader_key" not in st.session_state:
        st.session_state.file_uploader_key = 1
    files = st.sidebar.file_uploader(
        "upload data",
        type="csv",
        accept_multiple_files=True,
        key=f"file_uploader_{st.session_state.file_uploader_key}",
    )
    st.sidebar.button(
        "Upload files",
        on_click=save_files_to_disk,
        kwargs={"files": files, "data_dir": data_dir},
    )


def init(conn, data_dir):
    df = None
    try:
        df_initial = pd.read_sql("SELECT * FROM expenses", conn)
        default_user_input = add_date_range_widget(df_initial)
        default_user_input = add_category_widget(df_initial, default_user_input)
        default_user_input = add_description_widget(default_user_input)
        default_user_input = add_include_payment_widget(default_user_input)

        if st.sidebar.checkbox("Show sql"):
            user_input = st.text_input("label goes here", default_user_input)
            df = pd.read_sql(user_input, conn)
            st.dataframe(df)
            add_download_csv_widget(df)
        else:
            df = pd.read_sql(default_user_input, conn)
    except pd.io.sql.DatabaseError:
        pass

    st.sidebar.button(
        "Run pipeline",
        on_click=run,
        kwargs={"data_dir": data_dir},
    )
    add_upload_files_widget(data_dir)
    add_delete_files_widget(os.path.join(data_dir, "raw"))

    max_width_str = "max-width: 1080px;"
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
    if "category" not in df or "amount" not in df:
        st.markdown("**Spending by category**")
        st.markdown("Missing category or amount columns.")
        return

    df2 = df.groupby(["category"], as_index=False)["amount"].agg("sum")

    total = df["amount"].sum()

    color_discrete_map = {
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
        title="Spending over time",
        xaxis_title="Date",
        yaxis_title="Amount",
    )
    fig2.update_layout(
        font=dict(size=16, color="#7f7f7f"),
        title={"xanchor": "center", "x": 0.5},
    )
    st.plotly_chart(fig2, use_container_width=True)


def main():
    session_id = get_report_ctx().session_id
    session_info = Server.get_current()._get_session_info(session_id)
    user = ""
    try:
        user = session_info.ws.request.headers.get("X-Forwarded-User", "")
    except AttributeError:
        pass
    if not user and "no_user_warning" not in st.session_state:
        no_user_warning = st.warning(
            "Warning: no user provided, defaulting to common directory"
        )
        st.session_state.no_user_warning = True

    script_dir = os.path.dirname(os.path.realpath(__file__))
    data_dir = os.path.join(script_dir, "..", user, "data")
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "expenses.db")

    conn = sqlite3.connect(db_path)

    df = init(conn=conn, data_dir=data_dir)
    if df is None:
        st.write("Add some data and run the pipeline.")
        return
    add_spending_by_category(df)
    add_spending_over_time(df)

    if not user and no_user_warning:
        time.sleep(5)
        no_user_warning.empty()


if __name__ == "__main__":
    main()
