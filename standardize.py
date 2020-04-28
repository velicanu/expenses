import json

import click
from dateutil.parser import parse

from common import get_log

log = get_log(__file__)

full_list_of_categories = [
    "Airfare",
    "Automotive",
    "Bills & Utilities",
    "Dining",
    "Education",
    "Entertainment",
    "Fee/Interest Charge",
    "Fees & Adjustments",
    "Fees & Adjustments-Fees & Adjustments",
    "Food & Drink",
    "Gas",
    "Gas/Automotive",
    "Groceries",
    "Health & Wellness",
    "Health Care",
    "Home",
    "Lodging",
    "Merchandise & Supplies-Groceries",
    "Merchandise",
    "Other Services",
    "Other Travel",
    "Payment/Credit",
    "Personal",
    "Phone/Cable",
    "Professional Services",
    "Restaurant-Bar & Café",
    "Restaurant-Restaurant",
    "Shopping",
    "Transportation-Fuel",
    "Travel",
    "Travel-Airline",
]


def map_category(category):

    # Examples: annual fees, interest fee, cash from cc rewards
    if category in {
        "Fee/Interest Charge",
        "Fees & Adjustments",
        "Fees & Adjustments-Fees & Adjustments",
    }:
        return "Fees"

    if category in {
        "Food & Drink",
        "Dining",
        "Restaurant-Bar & Café",
        "Restaurant-Restaurant",
    }:
        return "Dining"

    if category in {
        "Gas",
        "Gas/Automotive",
        "Automotive",
        "Transportation-Fuel",
    }:
        return "Car"

    # Examples: mitoc, paintnite, alum events
    if category in {
        "Education",
        "Entertainment",
    }:
        return "Entertainment"

    # Examples: bkb membership, csv, hospital fees
    if category in {
        "Health & Wellness",
        "Health Care",
    }:
        return "Health"

    # Examples: tj, whole foods
    if category in {
        "Groceries",
        "Merchandise & Supplies-Groceries",
    }:
        return "Groceries"

    # Examples: flights, ubers, airbnb
    if category in {
        "Airfare",
        "Travel",
        "Travel-Airline",
        "Other Travel",
        "Lodging",
    }:
        return "Travel"

    # Examples: phone, internet, utilites
    if category in {
        "Bills & Utilities",
        "Phone/Cable",
    }:
        return "Bills"

    # Examples: stores, Note: capital_one puts TJs here
    if category in {
        "Merchandise",
        "Shopping",
    }:
        return "Shopping"

    return "Other"


def standardizer(record):
    record["date"] = parse(record["date"]).isoformat()
    record["category"] = map_category(record.get("category"))
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
