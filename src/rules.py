"""Rules."""
import streamlit as st

from preprocess.pipeline import run


def toggle_rules():
    st.session_state.config["rules_button"] = not st.session_state.config[
        "rules_button"
    ]


def save_rule(category_rule, description_rule, target, df):
    for cat in df["category"].unique():
        st.session_state.categories.add(cat.lower())
    valid = True
    if not category_rule and not description_rule:
        st.warning("No rule specified")
        valid = False
    if category_rule and description_rule:
        st.warning("Specify only one rule")
        valid = False
    if not target:
        st.warning("Target must be specified")
        valid = False
    if valid:
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
        st.button(
            "Save rule",
            on_click=save_rule,
            kwargs={
                "category_rule": category_rule,
                "description_rule": description_rule,
                "target": target,
                "df": df_initial,
            },
        )
        st.button("Apply rules", on_click=apply_rules, kwargs={"data_dir": data_dir})
        st.button("List rules", on_click=list_rules)

    if st.session_state.list_rules:
        st.json(st.session_state.config["rules"])
