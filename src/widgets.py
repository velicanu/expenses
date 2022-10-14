"""Widgets."""
from callbacks import delete_files, save_files_to_disk
from utils import extend_sql_statement
import dateutil
import os
import streamlit as st


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
    return default_user_input


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


def add_include_payment_widget(default_user_input):
    if not st.sidebar.checkbox("Include Payments"):
        return extend_sql_statement(default_user_input) + "category != 'Payment'"
    return default_user_input


def add_download_csv_widget(df):
    st.sidebar.download_button(
        label="Download csv",
        data=df.to_csv(index=False).encode(),
        file_name="data.csv",
        mime="text/csv",
    )


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
