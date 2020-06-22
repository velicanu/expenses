import json

import click
from smart_open import open

from common import get_log
from detect import identify_card

log = get_log(__file__)


def parse_record(record):
    card, card_def = identify_card(record)
    parsed_record = {k: record[v] for v, k in card_def.items()}
    if "amount" in parsed_record:
        parsed_record["amount"] = (
            float(parsed_record["amount"]) if parsed_record["amount"] else None
        )
    if "-amount" in parsed_record:
        parsed_record["amount"] = (
            -1 * float(parsed_record["-amount"]) if parsed_record["-amount"] else None
        )
        parsed_record.pop("-amount")
    parsed_record["source"] = card
    if "category" not in parsed_record:
        parsed_record["category"] = None
    parsed_record["source_file"] = record["source_file"]
    return parsed_record


def parse(infile, outfile):
    """Converts extracted json files files into uniform schema"""

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
