import logging
import os


def get_log(name):
    log = logging.getLogger(os.path.basename(name))
    logging.basicConfig(level=logging.INFO)
    return log
