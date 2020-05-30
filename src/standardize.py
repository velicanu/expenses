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


def strip_payment(records):
    """Remove payment of bill from records.

    Currently only implemented for AMEX.
    """
    records = [record for record in records if "THANK YOU" not in record["description"]]
    return records


def standardizer(record):
    record["date"] = parse(record["date"]).isoformat()
    record["category"] = (
        category_map[record.get("category")]
        if record.get("category") in category_map
        else "Other"
    )

    if record["description"] in description_map:
        record["category"] = description_map[record["description"]]
    return record


@click.command()
@click.argument("infile", type=click.File("r"))
@click.argument("outfile", type=click.File("w"))
def standardize(infile, outfile):
    """Converts excel and csv files into json"""

    log.info(f"Standardizing {infile.name} into {outfile.name}")
    for line in infile:
        record = json.loads(line)
        standardized_record = standardizer(record)
        outfile.write(f"{json.dumps(standardized_record)}\n")


if __name__ == "__main__":
    standardize()
