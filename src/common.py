import logging
import os


def get_log(name):
    log = logging.getLogger(os.path.basename(name))
    logging.basicConfig(level=logging.INFO)
    return log

def flip_spending_sign(records):
    for record in records:
        record['amount'] = -1 * record['amount']
    return records