import json

import click
from dateutil.parser import parse

from common import get_log

log = get_log(__file__)

category_map = {
    # Examples: annual fees, interest fee, cash from cc rewards
    "Fee/Interest Charge": "Fees",
    "Fees & Adjustments": "Fees",
    "Fees & Adjustments-Fees & Adjustments": "Fees",
    "Food & Drink": "Dining",
    "Dining": "Dining",
    "Restaurant-Bar & Café": "Dining",
    "Restaurant-Restaurant": "Dining",
    "Gas": "Car",
    "Gas/Automotive": "Car",
    "Automotive": "Car",
    "Transportation-Fuel": "Car",
    # Examples: mitoc, paintnite, alum events
    "Education": "Entertainment",
    "Entertainment": "Entertainment",
    # Examples: bkb membership, csv, hospital fees
    "Health & Wellness": "Health",
    "Health Care": "Health",
    # Examples: tj, whole foods
    "Groceries": "Groceries",
    "Merchandise & Supplies-Groceries": "Groceries",
    # Examples: flights, ubers, airbnb
    "Airfare": "Travel",
    "Travel": "Travel",
    "Travel-Airline": "Travel",
    "Other Travel": "Travel",
    "Lodging": "Travel",
    # Examples: phone, internet, utilites
    "Bills & Utilities": "Bills",
    "Phone/Cable": "Bills",
    # Examples: stores, Note: capital_one puts TJs here
    "Merchandise": "Shopping",
    "Shopping": "Shopping",
}


description_map = {"LYFT": "Rideshare", "UBER": "Rideshare"}


def standardizer(record):
    record["date"] = parse(record["date"]).isoformat()
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
