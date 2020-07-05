import unittest

from parse import parse_record
from detect import identify_card


class TestParse(unittest.TestCase):
    def test_parse(self):
        input_ = {
            "source_file": "amex.csv",
            "Date": "12/30/19",
            "Reference": 1234567890,
            "Description": "Trader Joe's",
            "Card Member": "foo",
            "Card Number": 12345,
            "Amount": 16.23,
            "Category": "Merchandise & Supplies-Groceries",
            "Type": "DEBIT",
            "Appears On Your Statement As": "TRADER JOE'S #502  QCAMBRIDGE           MA",
            "Address": "748 MEMORIAL DR\nCAMBRIDGE\nMA\n02139\nUNITED STATES",
            "Phone Number": 1234567890,
            "Website": "http://traderjoes.com",
            "Additional Information": '0080291     626-599-3700\n"Description : GROCERY STORES,SUPE Price : 0.00"\n626-599-3700',
        }
        expected = {
            "date": "12/30/19",
            "description": "Trader Joe's",
            "amount": 16.23,
            "category": "Merchandise & Supplies-Groceries",
            "source": "amex",
            "source_file": "amex.csv",
        }
        card, card_def = identify_card(input_)
        self.assertEqual(parse_record(input_, card, card_def), expected)

        input_ = {
            "source_file": "capital_one.csv",
            "Transaction Date": "2019-12-28",
            "Posted Date": "2019-12-30",
            "Card No.": 1234,
            "Description": "NIGHT SHIFT BREWING @",
            "Category": "Dining",
            "Debit": 4,
            "Credit": None,
        }
        expected = {
            "date": "2019-12-28",
            "description": "NIGHT SHIFT BREWING @",
            "amount": 4,
            "category": "Dining",
            "source": "capital_one",
            "source_file": "capital_one.csv",
        }
        card, card_def = identify_card(input_)
        self.assertEqual(parse_record(input_, card, card_def), expected)

        input_ = {
            "source_file": "chase.csv",
            "Transaction Date": "12/30/2019",
            "Post Date": "12/31/2019",
            "Description": "THE LANDING PIZZA AND KIT",
            "Category": "Food & Drink",
            "Type": "Sale",
            "Amount": -44,
        }
        expected = {
            "date": "12/30/2019",
            "description": "THE LANDING PIZZA AND KIT",
            "amount": 44,
            "category": "Food & Drink",
            "source": "chase",
            "source_file": "chase.csv",
        }
        card, card_def = identify_card(input_)
        self.assertEqual(parse_record(input_, card, card_def), expected)

        input_ = {
            "source_file": "usbank.csv",
            "Date": "12/18/2018",
            "Transaction": "CREDIT",
            "Name": "REI #80 BOSTON BOSTON MA",
            "Memo": "12345; ; ; ; ",
            "Amount": 59.89,
        }
        expected = {
            "date": "12/18/2018",
            "description": "REI #80 BOSTON BOSTON MA",
            "amount": -59.89,
            "category": None,
            "source": "usbank",
            "source_file": "usbank.csv",
        }
        card, card_def = identify_card(input_)
        self.assertEqual(parse_record(input_, card, card_def), expected)
