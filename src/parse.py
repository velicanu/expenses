import json

import click
from smart_open import open

from common import get_log
from detect import get_schemaless_card_defs, identify_card

log = get_log(__file__)


def get_card_from_filename(filename):
    """Determine card name from a parsed/extracted JSON file (first record)."""
    with open(filename, "r") as f:
        first_line = f.readline()
    record = json.loads(first_line)
    card, _card_def, info = identify_card(record)
    if card is None:
        columns = info.get("columns", []) if info else []
        raise ValueError(f"No card definition matches {filename}. Columns: {columns}")
    return card


def get_parser(card):
    """Return a function that parses a record for the given card."""
    card_defs = get_schemaless_card_defs()
    card_def = card_defs[card]

    def parser(record):
        return parse_record(record, card, card_def)

    return parser


def parse_record(record, card, card_def):
    parsed_record = {k: record.get(v) for v, k in card_def.items()}
    if "amount" in parsed_record and parsed_record["amount"]:
        parsed_record["amount"] = (
            parsed_record["amount"].replace("$", "").replace(",", "").replace(" ", "")
        )
        parsed_record["amount"] = float(parsed_record["amount"])
    if "-amount" in parsed_record and parsed_record["-amount"]:
        parsed_record["-amount"] = (
            parsed_record["-amount"].replace("$", "").replace(",", "").replace(" ", "")
        )
        parsed_record["amount"] = -1 * float(parsed_record["-amount"])
    if "-amount" in parsed_record:
        parsed_record.pop("-amount")
    parsed_record["source"] = card
    if "category" not in parsed_record:
        parsed_record["category"] = ""
    parsed_record["source_file"] = record["source_file"]

    # plaid hack
    if not parsed_record["date"]:
        parsed_record["date"] = record["date"]

    # venmo hack
    if card == "venmo":
        parsed_record["description"] = (
            f"{record['From']} --> {record['To']}: {record['Note']}"
        )

    return parsed_record


def parse(infile, outfile):
    """Converts extracted json files files into uniform schema"""

    log.info(f"Parsing {infile} into {outfile}")

    card, card_def, no_match_info = identify_card(json.loads(open(infile).readline()))
    if no_match_info is not None:
        columns = no_match_info.get("columns", [])
        raise ValueError(f"No card definition matches this file. Columns: {columns}")

    with open(infile, "r") as inf, open(outfile, "w") as outf:
        for line in inf:
            record = json.loads(line)
            parsed_record = parse_record(record, card, card_def)
            # if not parsed_record["amount"]:
            #     continue  # skip records without amount
            outf.write(f"{json.dumps(parsed_record)}\n")


@click.command()
@click.argument("infile", type=str)
@click.argument("outfile", type=str)
def _parse(infile, outfile):
    parse(infile, outfile)


if __name__ == "__main__":
    _parse()
