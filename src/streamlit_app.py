import base64
import os
import sqlite3

import dateutil.parser
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit.report_thread import get_report_ctx
from streamlit.server.server import Server

from detect import save_file_if_valid
from pipeline import run
from utils import clear, get_config, put_config

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


def add_date_range_widget(df, config):
    min_value = dateutil.parser.parse(df["date"].min())
    max_value = dateutil.parser.parse(df["date"].max())
    min_default = (
        dateutil.parser.parse(config.get("min_date"))
        if config.get("min_date")
        else min_value
    )
    max_default = (
        dateutil.parser.parse(config.get("max_date"))
        if config.get("max_date")
        else max_value
    )
    date_range = st.sidebar.date_input(
        "Date range",
        value=(min_default, max_default),
        min_value=min_value,
        max_value=max_value,
    )
    min_value_str = min_value.isoformat().replace("T00:00:00", "")
    max_value_str = max_value.isoformat().replace("T00:00:00", "")
    min_selected = date_range[0].isoformat()
    max_selected = date_range[1].isoformat() if len(date_range) == 2 else None

    default_user_input = "SELECT * FROM expenses"

    if min_selected != min_value_str:
        default_user_input = (
            extend_sql_statement(default_user_input) + f'date >= "{min_selected}"'
        )
    if max_selected and max_selected != max_value_str:
        default_user_input = (
            extend_sql_statement(default_user_input) + f'date <= "{max_selected}"'
        )
    config["max_date"] = max_selected
    config["min_date"] = min_selected
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
        status_info = st.sidebar.success("Saved: " + " ".join(success))
        run(data_dir)
    if failed:
        status_info = st.sidebar.error("Failed: " + " ".join(failed))

    # this key increment clears the upload dialog box after clicking upload
    st.session_state.file_uploader_key += 1
    clear(streamlit_object=status_info, seconds=2)


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


def expand():
    st.session_state.expand = not st.session_state.expand


def init(conn, data_dir, user, config):
    df = None
    if "expand" not in st.session_state:
        st.session_state.expand = False
    st.sidebar.button(
        "Expand",
        on_click=expand,
    )
    if st.session_state.expand and user:
        st.sidebar.write(f"{user} logged in")
    try:
        df_initial = pd.read_sql("SELECT * FROM expenses", conn)
        default_user_input = add_date_range_widget(df_initial, config)
        default_user_input = add_category_widget(df_initial, default_user_input)
        default_user_input = add_description_widget(default_user_input)
        if st.session_state.expand:
            default_user_input = add_include_payment_widget(default_user_input)
        else:
            default_user_input = (
                extend_sql_statement(default_user_input) + "category != 'Payment'"
            )

        # only set the default state to config if on first run
        # otherwise you have to click twice
        if "init_done" not in st.session_state:
            show_sql = st.sidebar.checkbox(
                "Show sql", value=config.get("show_sql", False)
            )
            st.session_state.show_sql = show_sql
        else:
            show_sql = st.sidebar.checkbox("Show sql", value=st.session_state.show_sql)
        if show_sql:
            user_input = st.text_input("label goes here", default_user_input)
            df = pd.read_sql(user_input, conn)
            st.dataframe(df)
            if st.session_state.expand:
                add_download_csv_widget(df)
        else:
            df = pd.read_sql(default_user_input, conn)
        config["show_sql"] = show_sql
    except pd.io.sql.DatabaseError:
        pass

    if df is None or st.session_state.expand:
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
    st.session_state.init_done = True
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
    data_dir = os.path.join(script_dir, "..", "data", user)
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "expenses.db")

    conn = sqlite3.connect(db_path)

    config_file = os.path.join(data_dir, "config.json")
    config = get_config(config_file)
    df = init(conn=conn, data_dir=data_dir, user=user, config=config)
    put_config(config_file=config_file, config=config)
    if df is None:
        st.write("Add some data and run the pipeline.")
        return
    if len(df.index) == 0:
        st.warning("Current selection is empty.")
    else:
        add_spending_by_category(df)
        add_spending_over_time(df)

    if not user:
        try:
            clear(streamlit_object=no_user_warning, seconds=2)
        except UnboundLocalError:
            pass
        st.session_state.no_user_warning = False


if __name__ == "__main__":
    main()
