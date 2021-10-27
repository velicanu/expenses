import json
import os
import shutil
import sqlite3
import tempfile

import numpy as np
import pandas as pd
import pytest

from common import get_files
from pipeline import run


@pytest.mark.fails_on_windows
def test_full_pipeline():
    with tempfile.TemporaryDirectory() as tmpdir:
        script_dir = os.path.dirname(os.path.realpath(__file__))
        sample_files_dir = os.path.join(script_dir, "..", "data", "sample")
        raw_dir = os.path.join(tmpdir, "raw")
        os.makedirs(raw_dir)
        for file_ in get_files(sample_files_dir):
            shutil.copy(file_, raw_dir)

        run(tmpdir)

        conn = sqlite3.connect(os.path.join(tmpdir, "expenses.db"))

        actual = sorted(
            pd.read_sql("SELECT * FROM expenses", conn)
            .replace({np.nan: None})
            .to_dict(orient="records"),
            key=lambda i: json.dumps(i),
        )
        expected = [
            {
                "date": "2018-12-18 00:00:00",
                "description": "REI #80 BOSTON BOSTON MA",
                "amount": -59.89,
                "category": "Shopping",
                "source": "usbank",
                "source_file": "usbank.csv",
            },
            {
                "date": "2019-01-02 00:00:00",
                "description": "LATE FEE - PAYMENT DUE ON 01/01",
                "amount": 27.0,
                "category": "Other",
                "source": "usbank",
                "source_file": "usbank.csv",
            },
            {
                "date": "2019-06-15 00:00:00",
                "description": "Hannaford",
                "amount": 2.55,
                "category": "Groceries",
                "source": "amex",
                "source_file": "amex.csv",
            },
            {
                "date": "2019-12-28 00:00:00",
                "description": "NIGHT SHIFT BREWING @",
                "amount": 4.0,
                "category": "Dining",
                "source": "capital_one",
                "source_file": "capital_one.csv",
            },
            {
                "date": "2019-12-29 00:00:00",
                "description": "KOHL'S #0531",
                "amount": 39.98,
                "category": "Shopping",
                "source": "capital_one",
                "source_file": "capital_one.csv",
            },
            {
                "date": "2019-12-29 00:00:00",
                "description": "TST* SWEET RICE - JP",
                "amount": 51.37,
                "category": "Dining",
                "source": "chase",
                "source_file": "chase.csv",
            },
            {
                "date": "2019-12-30 00:00:00",
                "description": "THE LANDING PIZZA AND KIT",
                "amount": 44.0,
                "category": "Dining",
                "source": "chase",
                "source_file": "chase.csv",
            },
            {
                "date": "2020-06-15 00:00:00",
                "description": "Trader Joe's",
                "amount": 24.17,
                "category": "Groceries",
                "source": "amex",
                "source_file": "amex.csv",
            },
            {
                "date": "2020-06-19 00:00:00",
                "description": "Trader Joe's",
                "amount": 10.76,
                "category": "Groceries",
                "source": "amex",
                "source_file": "amex.csv",
            },
        ]
        assert actual == expected
