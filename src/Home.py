import os

import streamlit as st


def main():
    user = os.getenv("EXPENSES_USER")
    if not user:
        st.error(
            "EXPENSES_USER environment variable is not set. Please set it to your username and restart the app."
        )
        st.stop()


if __name__ == "__main__":
    main()
