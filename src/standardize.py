import json

import click
import pandas as pd
from dateutil.parser import parse

from common import get_log

log = get_log(__file__)

default_category_map = {
    # Examples: annual fees, interest fee, cash from cc rewards
    "Fee/Interest Charge": "Fees",
    "Fees & Adjustments": "Fees",
    "Bank Fees": "Fees",
    "Fees & Adjustments-Fees & Adjustments": "Fees",
    "Food & Drink": "Dining",
    "Dining": "Dining",
    "Bar, cafe": "Dining",
    "Restaurant, fast-food": "Dining",
    "Restaurant-Bar & Café": "Dining",
    "Restaurant-Restaurant": "Dining",
    "Dining Out": "Dining",
    "Gas": "Car",
    "Gas/Automotive": "Car",
    "Automotive": "Car",
    "Transportation-Fuel": "Car",
    "Transportation": "Car",
    # Examples: mitoc, paintnite, alum events
    "Education": "Entertainment",
    "Entertainment": "Entertainment",
    # Examples: bkb membership, csv, hospital fees
    "Health & Wellness": "Health",
    "Health Care": "Health",
    "Active sport, fitness": "Health",
    # Examples: flights, ubers, airbnb
    "Airfare": "Travel",
    "Travel": "Travel",
    "Travel-Airline": "Travel",
    "Other Travel": "Travel",
    "Lodging": "Travel",
    "Holiday, trips, hotels": "Travel",
    # Examples: phone, internet, utilites
    "Energy, utilities": "Bills",
    "Bills & Utilities": "Bills",
    "Phone/Cable": "Bills",
    "Phone, cell phone": "Bills",
    # Examples: stores, Note: capital_one puts TJs here
    "Electronics, accessories": "Shopping",
    "Merchandise": "Shopping",
    "Shopping": "Shopping",
    "Specialty Stores": "Shopping",
    # Home
    "Rent": "Rent",
    "Services": "Services",
    "Life events": "Family",
    "Car Rental": "Travel",
    "food": "Dining",
    "entertainment": "Entertainment",
    "payment": "Payment",
    "fitness": "Health",
    "travel": "Travel",
    "shops": "Shopping",
    "Telecommunication": "Bills",
    "Insurance": "Bills",
    "Home": "Shopping",
    # Examples: tj, whole foods
    "Groceries": "Groceries",
}


default_description_map = {
    "LYFT": "Rideshare",
    "UBER": "Rideshare",
    "REI": "Shopping",
    "Google Fi": "Bills",
    "trvl": "Travel",
    "vrbo": "Travel",
    "nyct paygo": "Travel",
    "trader joe": "Groceries",
    "EASEWAY DE PR": "Travel",
    "Sanador": "Health",
    "CAPEAIR": "Travel",
    "EATS": "Dining",
}


def get_default_categories():
    return set(default_description_map.values()) | set(default_category_map.values())


def standardizer(record, rules):
    record["date"] = parse(record["date"]).isoformat()
    record["new_category"] = "Other"

    for rule, new_category in list(default_category_map.items()) + list(
        rules.get("category", {}).items()
    ):
        if rule.lower() in record["category"].lower():
            record["new_category"] = new_category

    for rule, new_category in list(default_description_map.items()) + list(
        rules.get("description", {}).items()
    ):
        if rule.lower() in record["description"].lower():
            record["new_category"] = new_category

    if "pay" in record["description"].lower() and record["amount"] < 0:
        record["new_category"] = "Payment"
    record["old_category"] = record["category"]
    record["category"] = record["new_category"]
    record.pop("new_category")

    return record


def ordered(records):
    df = pd.DataFrame(records)
    ordered_df = df.sort_values(by=["date"])
    ordered_records = ordered_df.to_dict(orient="records")
    for line, record in enumerate(ordered_records):
        record["pk"] = f"{record['source_file']}-{line}"
        record["line"] = line
    return ordered_records


def standardize(infile, outfile, rules):
    """Standardizes parsed files"""

    log.info(f"Standardizing {infile} into {outfile} using {rules}")

    with open(infile, "r") as inf, open(outfile, "w") as outf:
        standardized = [standardizer(json.loads(line), rules) for line in inf]
        ordered_records = ordered(standardized)
        for record in ordered_records:
            outf.write(f"{json.dumps(record)}\n")


@click.command()
@click.argument("infile", type=str)
@click.argument("outfile", type=str)
@click.argument("rules", type=str, default="{}")
def _standardize(infile, outfile, rules):
    get_default_categories()
    rules_ = json.loads(rules)
    standardize(infile, outfile, rules_)


if __name__ == "__main__":
    _standardize()
