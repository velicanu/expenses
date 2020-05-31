import csv
import io
import logging
import os

import numpy as np
import pandas as pd


def get_log(name):
    log = logging.getLogger(os.path.basename(name))
    logging.basicConfig(level=logging.INFO)
    return log


def flip_spending_sign(records):
    for record in records:
        record["amount"] = -1 * record["amount"]
    return records


def records_from_file(infile):
    """
    This function returns a list of json records from an input csv.

    :param infile: Input csv file or stream
    :return: list of json records
    """
    payload = infile.read(2048)
    if isinstance(infile, io.BytesIO):
        payload = payload.decode("utf-8")
    dialect = csv.Sniffer().sniff(payload)
    infile.seek(0)
    return (
        pd.read_csv(infile, dialect=dialect)
        .replace({np.nan: None})
        .to_dict(orient="records")
    )
