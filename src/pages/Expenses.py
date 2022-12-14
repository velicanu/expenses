import json
import os
import sqlite3
import webbrowser
from datetime import date, datetime, timedelta

import dateutil.parser
import pandas as pd
import plotly.express as px
import streamlit as st
from st_aggrid import AgGrid
from st_aggrid.grid_options_builder import GridOptionsBuilder

from detect import save_file_if_valid
from pipeline import run
from plaidlib import get_transactions
from sql import apply_changes, get_create_table_string, insert_rows, run_sql
from standardize import get_default_categories
from utils import (
    clear,
    dump_csv,
    get_access_token,
    get_config,
    get_institution_st,
    make_dirs,
    merge_tx,
    put_config,
)

st.set_page_config(
    page_title="Expense app",
    page_icon="src/static/favicon.ico",
    layout="wide",
    initial_sidebar_state="expanded",
)
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


def extend_sql_statement(statement):
    return (
        statement + " WHERE "
        if " where " not in statement.lower()
        else statement + " AND "
    )


def add_date_range_widget(df):

    min_value = dateutil.parser.parse(df["date"].min())
    max_value = dateutil.parser.parse(df["date"].max())
    min_default = (
        dateutil.parser.parse(st.session_state.config.get("min_date"))
        if st.session_state.config.get("min_date")
        else min_value
    )
    max_default = (
        dateutil.parser.parse(st.session_state.config.get("max_date"))
        if st.session_state.config.get("max_date")
        else max_value
    )
    min_default = max(min_value, min_default)
    max_default = min(max_value, max_default)
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
    st.session_state.config["max_date"] = max_selected
    st.session_state.config["min_date"] = min_selected
    return default_user_input


def add_category_widget(df, default_user_input):
    selected = st.sidebar.multiselect("Categories", sorted(df["category"].unique()))
    if selected:
        default_user_input = extend_sql_statement(default_user_input) + "category in "
        default_user_input = (
            default_user_input + f"{tuple(c for c in selected)}"
            if len(selected) > 1
            else default_user_input + f"('{selected[0]}')"
        )
    return default_user_input, selected


def add_source_widget(df, default_user_input):
    selected = st.sidebar.multiselect("Source file", sorted(df["source_file"].unique()))
    if selected:
        default_user_input = (
            extend_sql_statement(default_user_input) + "source_file in "
        )
        default_user_input = (
            default_user_input + f"{tuple(c for c in selected)}"
            if len(selected) > 1
            else default_user_input + f"('{selected[0]}')"
        )
    return default_user_input


def validate_description_input(value):
    num_operators = 0
    for operator in ["+", "^"]:
        if operator in value:
            num_operators += 1
    return num_operators <= 1 and value


def add_description_widget(default_user_input):
    title = st.sidebar.text_input(
        "Description", "", help="^ is and, + is or, ! is not, * is wildcard"
    )
    title = title.replace("*", "%")
    if not validate_description_input(title):
        if title:
            st.sidebar.warning(
                "invalid description, only one of + or ^ supported at a time"
            )
        return default_user_input, []
    if "+" in title or "^" in title:
        operator = "+" if "+" in title else "^"
        description_list = title.replace("!", "").split(operator)
    if "+" in title:
        return (
            extend_sql_statement(default_user_input)
            + "("
            + " OR ".join(
                [
                    f"description LIKE '%{s}%'"
                    if not s.startswith("!")
                    else f"description NOT LIKE '%{s[1:]}%'"
                    for s in title.split("+")
                ]
            )
            + ")"
        ), description_list
    if "^" in title:
        return (
            extend_sql_statement(default_user_input)
            + "("
            + " AND ".join(
                [
                    f"description LIKE '%{s}%'"
                    if not s.startswith("!")
                    else f"description NOT LIKE '%{s[1:]}%'"
                    for s in title.split("^")
                ]
            )
            + ")"
        ), description_list

    return (
        extend_sql_statement(default_user_input) + f"description LIKE '%{title}%'",
        [],
    )


def delete_files():
    for filename in st.session_state.delete_files:
        os.remove(filename)
    st.session_state.delete_files = set()


def add_delete_files_widget(raw_data_dir):

    if st.checkbox("Delete files"):
        for file_ in os.listdir(raw_data_dir):
            filename = os.path.join(raw_data_dir, file_)
            if st.checkbox(f"Delete {file_}"):
                st.session_state.delete_files.add(filename)
            else:
                try:
                    st.session_state.delete_files.remove(filename)
                except KeyError:
                    pass
        if st.session_state.delete_files:
            st.button("Confirm Delete", on_click=delete_files)


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
        status_info = st.success("Saved: " + " ".join(success))
        run(data_dir)
    if failed:
        status_info = st.error("Failed: " + " ".join(failed))

    # this key increment clears the upload dialog box after clicking upload
    st.session_state.file_uploader_key += 1
    clear(streamlit_object=status_info, seconds=2)


def add_upload_files_widget(data_dir):
    files = st.file_uploader(
        "upload data",
        type="csv",
        accept_multiple_files=True,
        key=f"file_uploader_{st.session_state.file_uploader_key}",
    )
    st.button(
        "Upload files",
        on_click=save_files_to_disk,
        kwargs={"files": files, "data_dir": data_dir},
    )


def expand():
    st.session_state.expand = not st.session_state.expand


def toggle_sql():
    st.session_state.config["show_sql"] = not st.session_state.config["show_sql"]


def toggle_rules():
    st.session_state.config["rules_button"] = not st.session_state.config[
        "rules_button"
    ]


def toggle_new_row():
    st.session_state.new_row = not st.session_state.new_row


def toggle_save_changes():
    st.session_state.save_changes = not st.session_state.save_changes


def save_rule(category_rule, description_rule, target, df):
    for cat in df["category"].unique():
        st.session_state.categories.add(cat.lower())
    if description_rule:
        st.session_state.config["rules"]["description"][description_rule] = target
    if category_rule:
        st.session_state.config["rules"]["category"][category_rule] = target


def list_rules():
    st.session_state.list_rules = not st.session_state.list_rules


def apply_rules(data_dir):
    run(data_dir, standardize_only=True, config=st.session_state.config)


def delete_rule(collection, label):
    delete_selection = st.multiselect(label, collection)
    if delete_selection:
        for selection in delete_selection:
            collection.pop(selection)


def add_rules(data_dir, df_initial):
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        category_rule = st.text_input("Category rule", "")
        delete_rule(
            st.session_state.config["rules"]["category"], "Delete category rule"
        )
    with col2:
        description_rule = st.text_input("Description rule", "")
        delete_rule(
            st.session_state.config["rules"]["description"], "Delete description rule"
        )
    with col3:
        new_categories = st.session_state.config["rules"]["new_categories"]
        all_categories = sorted(
            list(set(df_initial["category"].unique().tolist() + list(new_categories)))
        )
        target = st.selectbox("Target category", all_categories)
        new_category = st.text_input("Add a new category").title()
        if new_category and new_category not in new_categories:
            new_categories[new_category] = ""
        delete_rule(new_categories, "Delete new category")

    with col4:
        disabled = False
        help_ = ""
        if not category_rule and not description_rule:
            help_ = "No rule specified"
            disabled = True
        if category_rule and description_rule:
            help_ = "Specify only one rule"
            disabled = True

        st.button(
            "Save rule",
            on_click=save_rule,
            kwargs={
                "category_rule": category_rule,
                "description_rule": description_rule,
                "target": target,
                "df": df_initial,
            },
            disabled=disabled,
            help=help_,
        )
        st.button("Apply rules", on_click=apply_rules, kwargs={"data_dir": data_dir})
        st.button("List rules", on_click=list_rules)
        # st.button(
        #     "Delete rules",
        #     on_click=delete_rules,
        #     kwargs={
        #         "category_rule": category_rule,
        #         "description_rule": description_rule,
        #     },
        # )
    if st.session_state.list_rules:
        st.json(st.session_state.config["rules"])


def _make_new_row(date_, description, amount, category, df, conn):
    line_num = conn.execute("SELECT max(line) FROM expenses").fetchone()[0]
    new_line_num = line_num + 1 if line_num is not None else 0
    new_row = {
        "date": date_.isoformat() + " 00:00:00",
        "description": description,
        "amount": str(amount),
        "category": category,
        "source": "input",
        "source_file": "input",
        "old_category": "Other",
        "pk": f"input-{new_line_num}",
        "line": str(new_line_num),
    }
    return new_row


def save_new_row(date_, description, amount, category, df, conn):
    new_row = _make_new_row(date_, description, amount, category, df, conn)
    insert_rows([new_row], "expenses", conn)


def add_row(df, conn):
    st.write("Add a new row")
    help_ = ""
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        input_date = st.date_input("Date", value=date.today())
    with col2:
        input_description = st.text_input("Description")
        if not input_description:
            help_ = "No description"
    with col3:
        input_amount = st.number_input("Amount")
        if input_amount == 0.0:
            help_ = help_ + ", amount is 0" if help_ else "Amount is 0"

    with col4:
        new_categories = st.session_state.config["rules"]["new_categories"]
        all_categories = sorted(list(set(new_categories) | get_default_categories()))
        input_category = st.selectbox("Category", all_categories)

    enabled = bool(input_description) and (input_amount != 0.0)
    st.button(
        "Save new row",
        on_click=save_new_row,
        kwargs={
            "date_": input_date,
            "description": input_description,
            "amount": input_amount,
            "category": input_category,
            "df": df,
            "conn": conn,
        },
        disabled=not enabled,
        help=help_,
    )


def add_card_to_config(token, card, alias, start_date):
    st.session_state.config["linked_accounts"][alias] = {
        "alias": alias,
        "institution": card,
        "start_date": start_date,
        "token": token,
    }


def get_token(alias, start_date):
    token = get_access_token()
    if not token:
        st.warning("No access token")
        return
    name = get_institution_st(token)
    st.success(name)
    add_card_to_config(token=token, card=name, alias=alias, start_date=start_date)
    st.session_state.link_account_button = False


def toggle_custom_start_date():
    st.session_state.custom_start_date = not st.session_state.custom_start_date


def toggle_link_account():
    st.session_state.link_account_button = not st.session_state.link_account_button
    if st.session_state.link_account_button:
        webbrowser.open_new_tab("http://localhost:3000")


def add_link_account():
    st.button("Link account", on_click=toggle_link_account)
    if st.session_state.link_account_button:
        alias = st.text_input("Account alias", "")
        if alias:
            st.button("Custom start date", on_click=toggle_custom_start_date)
            if st.session_state.custom_start_date:
                dd = st.date_input(
                    label="Transaction start date",
                    help="Only pull transactions after this date. This is useful if you are combining manually uploaded CSVs with auto.",
                )
            st.button(
                "Get token",
                on_click=get_token,
                kwargs={
                    "alias": alias,
                    "start_date": dd.isoformat()
                    if st.session_state.custom_start_date
                    else date(date.today().year, 1, 1).isoformat(),
                },
            )
        else:
            st.write("Alias required to add token")


def json_serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"{value} not serializable")


def pull(data_dir):
    cards = st.session_state.config.get("linked_accounts")
    card_dir = os.path.join(data_dir, "cards")
    for card in cards.values():
        with st.spinner(f"Pulling {card} transactions"):
            transactions = get_transactions(
                access_token=card["token"],
                start_date=card["start_date"],
                end_date=date.today().isoformat(),
            )
        card_id = card["alias"]

        with open(os.path.join(card_dir, f"{card_id}.json"), "w") as outfile:
            for tx in transactions:
                tx["institution"] = card["institution"]
                outfile.write(f"{json.dumps(tx.to_dict(), default=json_serialize)}\n")
        db_file = merge_tx(card_dir, card_id)
        if db_file:
            dump_csv(data_dir, db_file, card_id)

        card["start_date"] = (date.today() - timedelta(days=30)).isoformat()

    run_wrapper(data_dir)


def add_refresh_data(data_dir):
    st.button(
        "Refresh data",
        on_click=pull,
        kwargs={"data_dir": data_dir},
    )


def run_wrapper(data_dir):
    with st.spinner("Running pipeline..."):
        run(data_dir=data_dir)


def init(conn, conn_changes, data_dir, user):
    df = None

    st.sidebar.button("Settings", on_click=expand)
    if st.session_state.expand and user:
        st.sidebar.write(f"{user} logged in")

    col1, col2, col3 = st.columns([2, 5, 5])
    if st.session_state.expand:
        st.subheader("Linked cards:")
        st.table(data=st.session_state.config["linked_accounts"])
        with col1:
            st.button(
                "Run pipeline",
                on_click=run_wrapper,
                kwargs={"data_dir": data_dir},
            )
            add_refresh_data(data_dir)
            add_link_account()
        with col2:
            add_upload_files_widget(data_dir)
        with col3:
            add_delete_files_widget(os.path.join(data_dir, "raw"))
    try:
        df_initial = pd.read_sql("SELECT * FROM expenses", conn)
        chdf_initial = pd.read_sql("SELECT * FROM expenses", conn_changes)
        df_initial = apply_changes(df_initial, chdf_initial)
        df_initial = df_initial[df_initial.amount != 0]  # filter out empty transactions
        default_user_input = add_date_range_widget(df_initial)
        default_user_input, selected = add_category_widget(
            df_initial, default_user_input
        )
        default_user_input, description_list = add_description_widget(
            default_user_input
        )
        default_user_input = add_source_widget(df_initial, default_user_input)
        if "Payment" not in selected:
            default_user_input = (
                extend_sql_statement(default_user_input) + "category != 'Payment'"
            )

        st.sidebar.button("Modify", on_click=toggle_rules)

        if st.session_state.config["rules_button"]:
            add_rules(data_dir, df_initial)

        st.sidebar.button("Show data", on_click=toggle_sql)

        if st.session_state.config["show_sql"]:
            col1, col2 = st.columns([20, 1])
            with col1:
                user_input = st.text_input(
                    "Input sql", default_user_input, label_visibility="collapsed"
                )
            with col2:
                if st.session_state.new_row:
                    st.button("+", on_click=toggle_new_row)
                else:
                    st.button("-", on_click=toggle_new_row)
            if not st.session_state.new_row and conn_changes:
                add_row(df=df_initial, conn=conn_changes)

            df = run_sql(user_input, df_initial, table_name="expenses")
            df = df.round(2)
            gb = GridOptionsBuilder.from_dataframe(df)
            gridOptions = gb.build()
            gridOptions["editable"] = True
            gridOptions["sortable"] = True
            gridOptions["filter"] = True
            gridOptions["columnDefs"] = [
                {
                    "headerName": col,
                    "field": col,
                    "editable": col not in {"pk", "source_file", "line"},
                }
                for col in df.columns
            ]
            edits = AgGrid(
                df,
                gridOptions,
                data_return_mode="AS_INPUT",
                update_mode="MODEL_CHANGED",
                fit_columns_on_grid_load=False,
                theme="streamlit",  # Add theme color to the table
                enable_enterprise_modules=True,
                height=350,
                width="100%",
                reload_data=False,
            )
            df_plus_edits = pd.concat([df, edits["data"]]).drop_duplicates(keep=False)
            changes = pd.merge(edits["data"], df_plus_edits, how="inner")
            if len(changes) > 0:
                st.write("Unsaved changes:")
                st.write(changes)
                st.button(
                    "Save Changes",
                    on_click=toggle_save_changes,
                )
                if st.session_state.save_changes:
                    insert_rows(
                        changes.to_dict(orient="records"), "expenses", conn_changes
                    )
                    st.session_state.save_changes = False
                    st.experimental_rerun()

        else:
            df = run_sql(default_user_input, df_initial, table_name="expenses")

    except pd.io.sql.DatabaseError:
        pass

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


def init_changes_db(db_path, changes_path):
    if not os.path.exists(changes_path):
        with sqlite3.connect(db_path) as conn:
            cts = get_create_table_string("expenses", conn)
        if not cts:
            return None
        changes_conn = sqlite3.connect(changes_path)
        changes_conn.execute(cts)
        changes_conn.commit()
        return changes_conn
    else:
        return sqlite3.connect(changes_path)


def init_data_dir(user):
    script_dir = os.path.dirname(os.path.realpath(__file__))
    data_dir = os.path.join(script_dir, "..", "data", user)
    cards_dir = os.path.join(data_dir, "cards")
    raw_dir = os.path.join(data_dir, "raw")
    extracted_dir = os.path.join(data_dir, "extracted")
    parsed_dir = os.path.join(data_dir, "parsed")
    standardized_dir = os.path.join(data_dir, "standardized")
    make_dirs(
        [data_dir, cards_dir, raw_dir, extracted_dir, parsed_dir, standardized_dir]
    )
    return data_dir


def main(user):
    if not user and "no_user_warning" not in st.session_state:
        no_user_warning = st.warning("No user provided, defaulting to common directory")
        st.session_state.no_user_warning = True

    data_dir = init_data_dir(user)

    db_path = os.path.join(data_dir, "expenses.db")
    changes_path = os.path.join(data_dir, "changes.db")

    conn = sqlite3.connect(db_path)
    conn_changes = init_changes_db(db_path=db_path, changes_path=changes_path)

    config_file = os.path.join(data_dir, "config.json")
    if "config" not in st.session_state:
        st.session_state.config = get_config(config_file)

    # init session state
    if "expand" not in st.session_state:
        st.session_state.expand = False
    if "delete_files" not in st.session_state:
        st.session_state.delete_files = set()
    if "file_uploader_key" not in st.session_state:
        st.session_state.file_uploader_key = 1
    if "linked_accounts" not in st.session_state.config:
        st.session_state.config["linked_accounts"] = {}
    if "show_sql" not in st.session_state.config:
        st.session_state.config["show_sql"] = False
    if "rules_button" not in st.session_state.config:
        st.session_state.config["rules_button"] = False
    if "link_account_button" not in st.session_state:
        st.session_state.link_account_button = False
    if "custom_start_date" not in st.session_state:
        st.session_state.custom_start_date = False
    if "list_rules" not in st.session_state:
        st.session_state.list_rules = False
    if "rules" not in st.session_state.config:
        st.session_state.config["rules"] = {
            "description": {},
            "category": {},
            "new_categories": {},
        }
    if "categories" not in st.session_state:
        st.session_state.categories = set()
    if "save_changes" not in st.session_state:
        st.session_state.save_changes = False
    if "new_row" not in st.session_state:
        st.session_state.new_row = True

    df = init(conn=conn, conn_changes=conn_changes, data_dir=data_dir, user=user)
    put_config(config_file=config_file, config=st.session_state.config)
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
    if st.session_state["authentication_status"]:
        main(st.session_state["username"])
    else:
        st.write("Not logged in.")
