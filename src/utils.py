import json
import time


def clear(streamlit_object, seconds):
    time.sleep(seconds)
    streamlit_object.empty()


def get_config(config_file):
    try:
        return json.load(open(config_file))
    except FileNotFoundError:
        return {}


def put_config(config_file, config):
    with open(config_file, "w") as f:
        f.write(json.dumps(config))
