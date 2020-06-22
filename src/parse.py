import json

import click
from smart_open import open

from common import get_log
from detect import identify_card

log = get_log(__file__)


def safe_float(value):
    return float(value) if value else None


def parse_record(record):
    card, card_def = identify_card(record)
    parsed_record = {k: record[v] for v, k in card_def.items()}
    if "amount" in parsed_record:
        parsed_record["amount"] = safe_float(parsed_record["amount"])
    if "-amount" in parsed_record:
        parsed_record["amount"] = -1 * safe_float(parsed_record["-amount"])
        parsed_record.pop("-amount")
    parsed_record["source"] = card
    if "category" not in parsed_record:
        parsed_record["category"] = None
    return parsed_record


def parse(infile, outfile):
    """Converts excel and csv files into json"""

    log.info(f"Parsing {infile} into {outfile}")
    with open(infile, "r") as inf, open(outfile, "w") as outf:
        for line in inf:
            record = json.loads(line)
            parsed_record = parse_record(record)
            outf.write(f"{json.dumps(parsed_record)}\n")


@click.command()
@click.argument("infile", type=str)
@click.argument("outfile", type=str)
def _parse(infile, outfile):
    parse(infile, outfile)


if __name__ == "__main__":
    _parse()
