import json
import pathlib

import click
from smart_open import open

from common import get_log
from detect import identify_card

log = get_log(__file__)

# money spent is negative, money paid is positive


def parse_amex(record):
    return {
        "date": record["Date"],
        "description": record["Description"],
        "amount": -1 * record["Amount"],
        "category": record["Category"],
        "source": "amex",
    }


def parse_capital_one(record):
    return {
        "date": record["Transaction Date"],
        "description": record["Description"],
        "amount": -1 * record.get("Debit") if record.get("Debit") else record["Credit"],
        "category": record["Category"],
        "source": "capital_one",
    }


def parse_chase(record):
    return {
        "date": record["Transaction Date"],
        "description": record["Description"],
        "amount": record["Amount"],
        "category": record["Category"],
        "source": "chase",
    }


def parse_usbank(record):
    return {
        "date": record["Date"],
        "description": record["Name"],
        "amount": record["Amount"],
        "category": None,  # No category
        "source": "usbank",
    }


PARSERS = {
    "amex": parse_amex,
    "chase": parse_chase,
    "capital_one": parse_capital_one,
    "usbank": parse_usbank,
}


def default_parser(record):
    return record


def get_card_from_filename(filename):
    path_info = pathlib.Path(filename)
    for card_name in PARSERS.keys():
        if path_info.stem.startswith(card_name):
            return card_name
    else:
        raise NotImplementedError("Card type not supported.")


def get_parser(record):
    card, card_def = identify_card(record)
    return PARSERS.get(card, default_parser)


def parse(infile, outfile):
    """Converts excel and csv files into json"""
    parser = None

    log.info(f"Parsing {infile} into {outfile}")
    with open(infile, "r") as inf, open(outfile, "w") as outf:
        for line in inf:
            record = json.loads(line)
            if parser is None:
                parser = get_parser(record)
            parsed_record = parser(record)
            outf.write(f"{json.dumps(parsed_record)}\n")


@click.command()
@click.argument("infile", type=str)
@click.argument("outfile", type=str)
def _parse(infile, outfile):
    parse(infile, outfile)


if __name__ == "__main__":
    _parse()
