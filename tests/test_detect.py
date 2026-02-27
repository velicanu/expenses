from detect import get_schemaless_card_defs, identify_card

CARD_DEFS = get_schemaless_card_defs()


def test_detect_amex():
    input_ = {
        "Date": "1/3/20",
        "Description": "Trader Joe's",
        "Amount": 123,
        "Extended Details": '0098616     626-599-3700\n"Description : GROCERY STORES,SUPE Price : 0.00"\n626-599-3700',
        "Appears On Your Statement As": "TRADER JOE'S #502  QCAMBRIDGE           MA",
        "Address": "748 MEMORIAL DR\nCAMBRIDGE\nMA\n02139\nUNITED STATES",
        "City/State": "",
        "Zip Code": "",
        "Country": "",
        "Reference": "'123'",
        "Category": "Merchandise & Supplies-Groceries",
    }
    card, card_def, info = identify_card(input_)
    assert card == "amex" and card_def == CARD_DEFS["amex"] and info is None


def test_detect_chase():
    input_ = {
        "Transaction Date": "12/30/2018",
        "Post Date": "01/01/2019",
        "Description": "CHESHIRE CAFE",
        "Category": "Food & Drink",
        "Type": "Sale",
        "Amount": -123,
        "Memo": "",
    }
    card, card_def, info = identify_card(input_)
    assert card == "chase" and card_def == CARD_DEFS["chase"] and info is None


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
    card, card_def, info = identify_card(input_)
    assert (
        card == "capital_one" and card_def == CARD_DEFS["capital_one"] and info is None
    )


def test_detect_usbank():
    input_ = {
        "Date": "12/23/2019",
        "Transaction": "CREDIT",
        "Name": "PAYMENT THANK YOU",
        "Memo": "WEB AUTOMTC; ; ; ; ; ",
        "Amount": 123.45,
    }
    card, card_def, info = identify_card(input_)
    assert card == "usbank" and card_def == CARD_DEFS["usbank"] and info is None


def test_detect_no_match_returns_columns():
    input_ = {"Foo": 1, "Bar": 2}
    card, card_def, info = identify_card(input_)
    assert card is None and card_def is None
    assert info is not None and info.get("columns") == ["Foo", "Bar"]
