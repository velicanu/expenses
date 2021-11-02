import time


def clear(streamlit_object, seconds):
    time.sleep(seconds)
    streamlit_object.empty()
