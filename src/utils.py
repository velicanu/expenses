import time

import requests
import streamlit as st

from cardstore import dump_csv, merge_tx  # noqa: F401  (moved; re-exported for main.py)
from common import get_log
from fsutil import (  # noqa: F401  (moved; re-exported for main.py)
    get_config,
    make_dirs,
    put_config,
)
from plaidlib import get_institution, get_item

log = get_log(__file__)


def toggle(state):
    st.session_state[state] = not st.session_state[state]


def toggle_button(key, function, *args, **kwargs):
    st.button(key, on_click=toggle, args=[key])
    if st.session_state[key]:
        function(*args, **kwargs)


def clear(streamlit_object, seconds):
    time.sleep(seconds)
    streamlit_object.empty()


def get_institution_st(access_token):
    institution_id = get_item(access_token)["institution_id"]
    institution_name = get_institution(
        access_token=access_token, institution_id=institution_id
    )["name"]
    return institution_name


def get_access_token(url="http://localhost:8000/api/info"):
    try:
        r = requests.post(url)
        data = r.json()
        return data["access_token"]
    except Exception as e:
        log.warning(f"Failed to get plaid token: {str(e)}")
