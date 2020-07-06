import json
import os

import click
from dateutil.parser import parse

from common import get_log

log = get_log(__file__)

script_dir = os.path.dirname(os.path.realpath(__file__))

category_map = json.load(open(os.path.join(script_dir, "category_definitions.json")))

description_map = {"LYFT": "Rideshare", "UBER": "Rideshare"}


def standardizer(record):
    record["date"] = parse(record["date"]).isoformat()
    record["source_category"] = record["category"]
    record["category"] = (
        category_map[record.get("category")]
        if record.get("category") in category_map
        else "Other"
    )

    for key in description_map:
        if key in record["description"] and "EATS" not in record["description"]:
            record["category"] = description_map[key]

    if "pay" in record["description"].lower() and record["amount"] < 0:
        record["category"] = "Payment"
    return record


def standardize(infile, outfile):
    """Standardizes parsed files"""

    log.info(f"Standardizing {infile} into {outfile}")

    with open(infile, "r") as inf, open(outfile, "w") as outf:
        for line in inf:
            record = json.loads(line)
            standardized_record = standardizer(record)
            outf.write(f"{json.dumps(standardized_record)}\n")


@click.command()
@click.argument("infile", type=str)
@click.argument("outfile", type=str)
def _standardize(infile, outfile):
    standardize(infile, outfile)


if __name__ == "__main__":
    _standardize()
