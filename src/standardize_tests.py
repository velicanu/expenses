import unittest

from standardize import standardizer


class TestStandardize(unittest.TestCase):
    def test_standardize(self):
        input_ = {
            "date": "12/30/2019",
            "description": "THE LANDING PIZZA AND KIT",
            "amount": -44.0,
            "category": "Food & Drink",
            "source": "chase",
        }
        expected = {
            "date": "2019-12-30T00:00:00",
            "description": "THE LANDING PIZZA AND KIT",
            "amount": -44.0,
            "category": "Dining",
            "source": "chase",
        }
        self.assertEqual(standardizer(input_), expected)

    def test_standardize_payment(self):
        input_ = {
            "date": "12/4/19",
            "description": "ONLINE PAYMENT - THANK YOU",
            "amount": -81.89,
            "category": "",
            "source": "amex",
            "source_file": "amex-viral-2019.csv",
        }
        expected = {
            "date": "2019-12-04T00:00:00",
            "description": "ONLINE PAYMENT - THANK YOU",
            "amount": -81.89,
            "category": "Payment",
            "source": "amex",
            "source_file": "amex-viral-2019.csv",
        }
        self.assertEqual(standardizer(input_), expected)
