import os
import tempfile
import unittest

from extract import read_to_dict


class TestExtract(unittest.TestCase):
    def test_read_to_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_ = os.path.join(tmpdir, "input.csv")
            with open(input_, "w") as _f:
                _f.write(
                    """
Transaction Date,Post Date,Description,Category,Type,Amount
12/30/2019,12/31/2019,THE LANDING PIZZA AND KIT,Food & Drink,Sale,-44.00
12/29/2019,12/30/2019,TST* SWEET RICE - JP,Food & Drink,Sale,-51.37
"""
                )

            expected = [
                {
                    "Transaction Date": "12/30/2019",
                    "Post Date": "12/31/2019",
                    "Description": "THE LANDING PIZZA AND KIT",
                    "Category": "Food & Drink",
                    "Type": "Sale",
                    "Amount": -44.0,
                },
                {
                    "Transaction Date": "12/29/2019",
                    "Post Date": "12/30/2019",
                    "Description": "TST* SWEET RICE - JP",
                    "Category": "Food & Drink",
                    "Type": "Sale",
                    "Amount": -51.37,
                },
            ]
            actual = read_to_dict(input_)

            self.assertEqual(expected, actual)
