import json
import pathlib

import click

from common import get_log

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
        "category": None, # No category
        "source": "usbank",
    }


PARSER_DICT = {"amex": parse_amex,
               "chase": parse_chase,
               "capital_one": parse_capital_one,
               "usbank": parse_usbank}


def default_parser(record):
    return record


def get_card(filename):
    path_info = pathlib.Path(filename)
    if path_info.stem.startswith("amex"):
        return "amex"
    elif path_info.stem.startswith("chase"):
        return "chase"
    elif path_info.stem.startswith("capital"):
        return "capital_one"
    elif path_info.stem.startswith("usbank"):
        return "usbank"
    else:
        raise NotImplementedError("Card type not supported.")


def get_parser(filename):
    card_type = get_card(filename)
    if card_type in PARSER_DICT:
        return PARSER_DICT[card_type]
    else:
        return default_parser


@click.command()
@click.argument("infile", type=click.File("r"))
@click.argument("outfile", type=click.File("w"))
def parse(infile, outfile):
    """Converts excel and csv files into json"""
    parser = get_parser(infile.name)

    log.info(f"Parsing {infile.name} into {outfile.name}")
    for line in infile:
        record = json.loads(line)
        parsed_record = parser(record)
        outfile.write(f"{json.dumps(parsed_record)}\n")


if __name__ == "__main__":
    parse()
