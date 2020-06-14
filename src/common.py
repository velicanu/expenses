import csv
import io
import logging
import os

import numpy as np
import pandas as pd

from detect import identify_card


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


def save_file_if_valid(file_, filename, upload_folder):
    """
    Saves the given file to the upload_folder if it matches a card

    :param file_: a werkzeug.FileStorage object from flask
    :param filename: the filename to save the file to
    :param upload_folder: folder to save the file

    """
    with io.BytesIO() as stream:
        file_.save(stream)
        stream.seek(0)
        first_record = records_from_file(stream)[0]
        card, card_def = identify_card(first_record)
        if card:
            with open(os.path.join(upload_folder, filename), "wb") as output_file:
                output_file.write(stream.getbuffer())
            return "success", f"{filename}: {card}"
        else:
            return "failed", f"{filename}"
