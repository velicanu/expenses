import copy
import json
import os
import tempfile

import click

from common import records_from_file

script_dir = os.path.dirname(os.path.realpath(__file__))


def _load_card_definitions():
    with open(os.path.join(script_dir, "card_definitions.json")) as f:
        definitions = json.load(f)
    schemaless = copy.deepcopy(definitions)
    for value in schemaless.values():
        value.pop("schema")
    return definitions, schemaless


def get_schemaless_card_defs():
    """Return schemaless card definitions (for tests and callers that need a def by name)."""
    _, schemaless = _load_card_definitions()
    return schemaless


def identify_card(record):
    """
    Looks at a json record and returns the matching card + card_definition.

    :param record: a json record (dict with column names as keys)
    :return: (card_name, card_def, info). On match: (card, card_def, None).
        On no match: (None, None, info) where info is {"columns": list of column names found}.
    """
    card_definitions, schemaless_card_defs = _load_card_definitions()
    columns = list(record)
    if "source_file" in record:
        columns.remove("source_file")
    for card, card_def in card_definitions.items():
        if columns == card_def["schema"]:
            return card, schemaless_card_defs[card], None
    return None, None, {"columns": columns}


def identify_file(filename):
    """Return (card_name, info). info is None on match, or dict with 'columns' on no match."""
    records = records_from_file(filename)
    card, _card_def, info = identify_card(records[0])
    return card, info


def save_file_if_valid(file_, data_dir):
    """
    Saves the given file to the upload_dir if it matches a card

    :param file_: a filelike object
    :param data_dir: the data directory of this app

    """
    raw = file_.read()
    upload_dir = os.path.join(data_dir, "raw")
    file_name = os.path.basename(file_.name)
    with tempfile.TemporaryDirectory() as tempdir:
        tempfilename = os.path.join(tempdir, file_name)
        with open(tempfilename, "wb") as tmpfile:
            tmpfile.write(raw)
        card, info = identify_file(tempfilename)

        if card:
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
            os.replace(tempfilename, os.path.join(upload_dir, file_name))
            return "success", f"{file_name}: {card}"
        else:
            columns_msg = f" (columns: {info['columns']})" if info and "columns" in info else ""
            return "failed", f"{file_name}{columns_msg}"


@click.command()
@click.argument("infile", type=str)
def _detect(infile):
    card, info = identify_file(infile)
    if card:
        click.echo(card)
    else:
        click.echo(f"No matching card. Columns: {info['columns'] if info else 'unknown'}")


if __name__ == "__main__":
    _detect()
