import os

import streamlit as st
import yaml

from auth import init_auth, logged_in, logged_out


def main(config):
    authenticator = init_auth(config)

    # this will create the login widgets and also update session_state:
    # st.session_state["authentication_status"] - True, False, or None
    # st.session_state["name"] and  st.session_state["username"] as also populated
    authenticator.login("Login", "main")

    if st.session_state["authentication_status"]:
        logged_in(authenticator)
    else:
        logged_out(authenticator)


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.realpath(__file__))
    config_path = os.path.join(script_dir, "..", "auth.yaml")

    # load auth config
    with open(config_path) as file:
        config = yaml.load(file, Loader=yaml.SafeLoader)
    main(config)

    # save auth config, this is how register and change password persists
    with open(config_path, "w") as file:
        yaml.dump(config, file, default_flow_style=False)
