import json
import os
import tempfile

import click

from common import records_from_file

script_dir = os.path.dirname(os.path.realpath(__file__))

CARD_DEFINITIONS = json.load(open(os.path.join(script_dir, "card_definitions.json")))


def identify_card(record):
    """
    Looks at a json record and returns the matching card + card_definition

    :param record: a json record
    :return: the matching card name, the card definition (field name mapping)
    """
    for card, card_def in CARD_DEFINITIONS.items():
        if all(key in record for key in card_def):
            return card, card_def
    return None, None


def identify_file(filename):
    records = records_from_file(filename)
    card, card_def = identify_card(records[0])
    return card


def save_file_if_valid(file_, data_dir):
    """
    Saves the given file to the upload_dir if it matches a card

    :param file_: a streamlit UploadedFile object
    :param data_dir: the data directory of this app

    """
    upload_dir = os.path.join(data_dir, "raw")
    with tempfile.TemporaryDirectory() as tempdir:
        tempfilename = os.path.join(tempdir, file_.name)
        with open(tempfilename, "wb") as tmpfile:
            tmpfile.write(file_.read())
        card = identify_file(tempfilename)

        if card:
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
            os.replace(tempfilename, os.path.join(upload_dir, file_.name))
            return "success", f"{file_.name}: {card}"
        else:
            return "failed", f"{file_.name}"


@click.command()
@click.argument("infile", type=str)
def _detect(infile):
    identify_file(infile)


if __name__ == "__main__":
    _detect()
