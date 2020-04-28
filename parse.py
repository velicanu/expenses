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
        # no category :(
        "source": "usbank",
    }


PARSERS = {
    "amex": parse_amex,
    "capital_one": parse_capital_one,
    "chase": parse_chase,
    "usbank": parse_usbank,
}


@click.command()
@click.argument("infile", type=click.File("r"))
@click.argument("outfile", type=click.File("w"))
def parse(infile, outfile):
    """Converts excel and csv files into json"""
    path_info = pathlib.Path(infile.name)
    parser = PARSERS[path_info.stem]

    log.info(f"Parsing {infile.name} into {outfile.name}")
    for line in infile:
        record = json.loads(line)
        parsed_record = parser(record)
        outfile.write(f"{json.dumps(parsed_record)}\n")


if __name__ == "__main__":
    parse()
