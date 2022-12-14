import streamlit as st
import streamlit_authenticator as stauth

from utils import toggle_button

REGISTER = "Register"
RESET_PASSWORD = "Reset Password"


def is_logged_in():
    return (
        "authentication_status" in st.session_state
        and st.session_state["authentication_status"]
    )


def register(authenticator):
    """
    Adds registration widgets.
    """
    try:
        if authenticator.register_user("Register user", preauthorization=True):
            st.success("User registered successfully")
            st.session_state[REGISTER] = False
    except Exception as e:
        st.error(e)


def reset_password(authenticator, username):
    """
    Adds a user password reset widget.
    """
    try:
        if authenticator.reset_password(username, "Reset password"):
            st.success("Password modified successfully")
    except Exception as e:
        st.error(e)


def init_auth(config):
    if REGISTER not in st.session_state:
        st.session_state[REGISTER] = False
    if RESET_PASSWORD not in st.session_state:
        st.session_state[RESET_PASSWORD] = False
    return stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
        config["preauthorized"],
    )


def logged_in(authenticator):
    """
    Adds a logout button, a reset password button
    and a message that you are logged in.
    """
    authenticator.logout("Logout", "main")
    st.write(f'Welcome *{st.session_state["name"]}*')
    st.title("You are logged in!")
    toggle_button(
        RESET_PASSWORD, reset_password, authenticator, {st.session_state["username"]}
    )


def logged_out(authenticator):
    """
    Shows some info that we're not logged in and a register button
    """
    if st.session_state["authentication_status"] is False:
        st.error("Username/password is incorrect")
    elif st.session_state["authentication_status"] is None:
        st.warning("Please enter your username and password")
    toggle_button(REGISTER, register, authenticator)
