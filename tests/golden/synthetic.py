"""A deterministic, made-up data directory for the parity tests (no real data): Chase-layout CSVs through the
pipeline, plus a config.json with rules, custom category colors and the old sidebar's saved filters.

It is built to hit the awkward cases of the charts: a category with a custom color, two categories with NO
color in the old app's map (Plotly Express picks theirs), categories whose net sum is negative (the pie does
not draw those), several rows a day, and years of data (so the bin choices differ)."""

import json
import random
from datetime import date, timedelta
from pathlib import Path

# (raw Chase category, description, typical amount as written in the file: negative = money spent)
SHOPS = [
    ("Food & Drink", "BLUE BOTTLE COFFEE", -6.5),
    ("Food & Drink", "SWEETGREEN", -14.2),
    ("Groceries", "WHOLE FOODS MARKET", -63.0),
    ("Groceries", "TRADER JOES", -41.0),
    ("Gas", "SHELL OIL", -48.0),
    ("Travel", "DELTA AIR LINES", -310.0),
    ("Travel", "AIRBNB", -420.0),
    ("Bills & Utilities", "CON EDISON", -96.0),
    ("Shopping", "AMAZON MARKETPLACE", -37.5),
    ("Health & Wellness", "CVS PHARMACY", -22.0),
    ("Entertainment", "AMC THEATRES", -28.0),
    ("Rent", "RENT PAYMENT LLC", -3100.0),
    ("Fees & Adjustments", "ANNUAL FEE", -95.0),
    ("payment", "PAYMENT THANK YOU", 1800.0),
    ("Misc", "LYFT RIDE", -18.0),
    ("Misc", "PAYROLL ACME INC", 4200.0),
    ("Misc", "GIFT FOR MOM", -55.0),
    ("Misc", "MYSTERY VENDOR", -12.0),
    ("Misc", "REFUND AMAZON", 20.0),
]

CONFIG = {
    "min_date": "2024-01-01",
    "max_date": "2025-06-30",
    "categories in": [],
    "categories not in": ["Income"],
    "show_sql": True,
    "rules_button": False,
    "linked_accounts": {},
    "rules": {
        "description": {
            "payroll": "Income",
            "lyft": "Rideshare",
            "gift": "Gifts",
            "mystery": "Mystery",
        },
        "category": {},
        # Income and Gifts have custom colors; Payment and Mystery have none, anywhere
        "new_categories": {"Income": "#00ff00", "Gifts": "#5b1385"},
    },
}


def write(data_dir: Path) -> None:
    rng = random.Random(20260101)
    raw = data_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    rows = []
    day = date(2023, 1, 1)
    while day <= date(2025, 12, 31):
        if day.day == 1:
            rows.append((day, *SHOPS[11]))  # rent on the 1st
        if day.day == 15:
            rows.append((day, *SHOPS[15]))  # payroll twice a month
        if day.day == 28:
            rows.append((day, *SHOPS[15]))
        if day.day == 20:
            rows.append((day, *SHOPS[13]))  # a card payment
        for _ in range(rng.choice([0, 1, 1, 2, 3])):
            cat, desc, amount = rng.choice(
                [s for i, s in enumerate(SHOPS) if i not in (11, 13, 15)]
            )
            rows.append((day, cat, desc, round(amount * rng.uniform(0.6, 1.5), 2)))
        day += timedelta(days=1)
    # Chase lists newest first
    with open(raw / "chase.csv", "w") as f:
        f.write("Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n")
        for d, cat, desc, amount in reversed(rows):
            f.write(f"{d:%m/%d/%Y},{d:%m/%d/%Y},{desc},{cat},Sale,{amount:.2f},\n")
    (data_dir / "config.json").write_text(json.dumps(CONFIG))
