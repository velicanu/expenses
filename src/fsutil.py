"""Filesystem helpers shared by the pipeline and the API (no UI imports)."""

import json
import os
import tempfile


def make_dirs(list_of_dirs):
    """
    Makes internal directories if they don't exist
    """
    for dir_ in list_of_dirs:
        os.makedirs(dir_, exist_ok=True)


def get_config(config_file):
    try:
        with open(config_file) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def put_config(config_file, config):
    """Writes the config atomically: a reader (or Syncthing) never sees a half-written file."""
    directory = os.path.dirname(os.path.abspath(config_file))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(config))
        os.replace(tmp, config_file)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
