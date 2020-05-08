import os
import sqlite3
import subprocess
import tempfile
import unittest

import numpy as np
import pandas as pd


class TestPipeline(unittest.TestCase):
    def test_full_pipeline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["sh", "run_test_setup.sh", f"{tmpdir}"])
            conn = sqlite3.connect(os.path.join(tmpdir, "expenses.db"))
            actual = (
                pd.read_sql("SELECT * FROM expenses", conn)
                .replace({np.nan: None})
                .to_dict(orient="records")
            )
            expected = [
                {
                    "index": 0,
                    "date": "2019-12-30 00:00:00",
                    "description": "Trader Joe's",
                    "amount": -26.23,
                    "category": "Groceries",
                    "source": "amex",
                },
                {
                    "index": 1,
                    "date": "2019-12-29 00:00:00",
                    "description": "SPEEDWAY            1-800-643-1949      OH",
                    "amount": -80.02,
                    "category": "Car",
                    "source": "amex",
                },
                {
                    "index": 0,
                    "date": "2019-12-30 00:00:00",
                    "description": "Trader Joe's",
                    "amount": -16.23,
                    "category": "Groceries",
                    "source": "amex",
                },
                {
                    "index": 1,
                    "date": "2019-12-29 00:00:00",
                    "description": "SPEEDWAY            1-800-643-1949      OH",
                    "amount": -40.02,
                    "category": "Car",
                    "source": "amex",
                },
                {
                    "index": 0,
                    "date": "2019-12-28 00:00:00",
                    "description": "NIGHT SHIFT BREWING @",
                    "amount": -4.0,
                    "category": "Dining",
                    "source": "capital_one",
                },
                {
                    "index": 1,
                    "date": "2019-12-29 00:00:00",
                    "description": "KOHL'S #0531",
                    "amount": -39.98,
                    "category": "Shopping",
                    "source": "capital_one",
                },
                {
                    "index": 0,
                    "date": "2019-12-30 00:00:00",
                    "description": "THE LANDING PIZZA AND KIT",
                    "amount": -44.0,
                    "category": "Dining",
                    "source": "chase",
                },
                {
                    "index": 1,
                    "date": "2019-12-29 00:00:00",
                    "description": "TST* SWEET RICE - JP",
                    "amount": -51.37,
                    "category": "Dining",
                    "source": "chase",
                },
                {
                    "index": 0,
                    "date": "2018-12-18 00:00:00",
                    "description": "REI #80 BOSTON BOSTON MA",
                    "amount": 59.89,
                    "category": "Other",
                    "source": "usbank",
                },
                {
                    "index": 1,
                    "date": "2019-01-02 00:00:00",
                    "description": "LATE FEE - PAYMENT DUE ON 01/01",
                    "amount": -27.0,
                    "category": "Other",
                    "source": "usbank",
                },
            ]

            self.assertEqual(actual, expected)
