from detect import CARD_DEFINITIONS, identify_card


def test_detect_amex():
    input_ = {
        "Date": "1/3/20",
        "Description": "Trader Joe's",
        "Amount": 123,
        "Extended Details": '0098616     626-599-3700\n"Description : GROCERY STORES,SUPE Price : 0.00"\n626-599-3700',
        "Appears On Your Statement As": "TRADER JOE'S #502  QCAMBRIDGE           MA",
        "Address": "748 MEMORIAL DR\nCAMBRIDGE\nMA\n02139\nUNITED STATES",
        "Reference": "'123'",
        "Category": "Merchandise & Supplies-Groceries",
    }
    expected = "amex", CARD_DEFINITIONS["amex"]
    assert identify_card(input_) == expected


def test_detect_chase():
    input_ = {
        "Transaction Date": "12/30/2018",
        "Post Date": "01/01/2019",
        "Description": "CHESHIRE CAFE",
        "Category": "Food & Drink",
        "Type": "Sale",
        "Amount": -123,
    }
    expected = "chase", CARD_DEFINITIONS["chase"]
    assert identify_card(input_) == expected


def test_detect_capital_one():
    input_ = {
        "Transaction Date": "2019-01-02",
        "Posted Date": "2019-01-02",
        "Card No.": 1234,
        "Description": "UBER",
        "Category": "Other Travel",
        "Debit": 123,
        "Credit": None,
    }
    expected = "capital_one", CARD_DEFINITIONS["capital_one"]
    assert identify_card(input_) == expected


def test_detect_usbank():
    input_ = {
        "Date": "12/23/2019",
        "Transaction": "CREDIT",
        "Name": "PAYMENT THANK YOU",
        "Memo": "WEB AUTOMTC; ; ; ; ; ",
        "Amount": 123.45,
    }
    expected = "usbank", CARD_DEFINITIONS["usbank"]
    assert identify_card(input_) == expected
