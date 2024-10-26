import os

import streamlit as st

from auth import init_auth, load_config, logged_in, logged_out, update_config


def main(config):
    authenticator = init_auth(config)

    # this will create the login widgets and also update session_state:
    # st.session_state["authentication_status"] - True, False, or None
    # st.session_state["name"] and  st.session_state["username"] as also populated
    authenticator.login()

    if st.session_state["authentication_status"]:
        logged_in(authenticator)
    else:
        logged_out(authenticator)


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.realpath(__file__))
    config_path = os.path.join(script_dir, "..", "auth.yaml")

    config = load_config(config_path)
    main(config)
    update_config(config_path, config)
