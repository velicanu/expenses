import json

import click
from smart_open import open

from common import get_log
from detect import identify_card

log = get_log(__file__)


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
    if "credit" in parsed_record:
        # A credit column is money back: negative in the output whichever sign the bank writes it with
        # (Capital One writes credits as positive numbers, Citi as negative ones; "-amount" would turn
        # Citi's refunds and payments into spending).
        if parsed_record["credit"]:
            credit = (
                parsed_record["credit"]
                .replace("$", "")
                .replace(",", "")
                .replace(" ", "")
            )
            parsed_record["amount"] = -abs(float(credit))
        parsed_record.pop("credit")
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

    card, card_def = identify_card(json.loads(open(infile).readline()))

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
