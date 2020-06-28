import csv
import io
import logging
import os
import tempfile

from detect import identify_card


def get_files(dir_):
    """
    returns a list of full path filenames in dir
    """
    return [os.path.join(dir_, filename) for filename in os.listdir(dir_)]


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
    This function returns a generator of json records from an input csv.

    :param infile: Input csv file or stream
    :return: generator of json records
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # first clean the file
        with open(os.path.join(tmpdir, "tmp.txt"), "w") as tmpfile:
            input_ = infile.read()
            if isinstance(infile, io.BytesIO):
                input_ = input_.decode("utf-8")
            # amex csv export breaks python csv parser due to double "" inside "
            input_ = input_.replace('""', "@")
            dialect = csv.Sniffer().sniff(input_)
            tmpfile.write(input_)

        with open(os.path.join(tmpdir, "tmp.txt"), "r") as tmpfile:
            reader = csv.reader(tmpfile, dialect)
            header = next(reader)
            for row in reader:
                _row = {k: v for k, v in zip(header, row)}
                # don't return null rows
                if any([v for v in _row.values()]):
                    yield _row


def save_file_if_valid(file_, filename, data_dir):
    """
    Saves the given file to the upload_dir if it matches a card

    :param file_: a werkzeug.FileStorage object from flask
    :param filename: the filename to save the file to
    :param data_dir: the data directory of this app

    """
    upload_dir = os.path.join(data_dir, "raw")
    with io.BytesIO() as stream:
        file_.save(stream)
        stream.seek(0)
        first_record = next(records_from_file(stream))
        card, card_def = identify_card(first_record)
        if card:
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
            with open(os.path.join(upload_dir, filename), "wb") as output_file:
                output_file.write(stream.getbuffer())
            return "success", f"{filename}: {card}"
        else:
            return "failed", f"{filename}"
