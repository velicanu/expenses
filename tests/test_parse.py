from detect import identify_card
from parse import parse_record


def test_parse():
    input_ = {
        "source_file": "amex.csv",
        "Date": "05/30/2021",
        "Description": "MOBILE PAYMENT - THANK YOU",
        "Amount": "-123",
        "Extended Details": "MOBILE PAYMENT - THANK YOU",
        "Appears On Your Statement As": "MOBILE PAYMENT - THANK YOU",
        "Address": "",
        "City/State": "",
        "Zip Code": "",
        "Country": "",
        "Reference": "'456'",
        "Category": "",
    }
    expected = {
        "date": "05/30/2021",
        "description": "MOBILE PAYMENT - THANK YOU",
        "amount": -123,
        "category": "",
        "source": "amex",
        "source_file": "amex.csv",
    }
    card, card_def = identify_card(input_)
    assert parse_record(input_, card, card_def) == expected

    input_ = {
        "source_file": "capital_one.csv",
        "Transaction Date": "2019-12-28",
        "Posted Date": "2019-12-30",
        "Card No.": 1234,
        "Description": "NIGHT SHIFT BREWING @",
        "Category": "Dining",
        "Debit": "4",
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
    assert parse_record(input_, card, card_def) == expected

    input_ = {
        "source_file": "chase.csv",
        "Transaction Date": "12/29/2020",
        "Post Date": "12/30/2020",
        "Description": "PAS*PASSPT PK BOSTON",
        "Category": "Travel",
        "Type": "Sale",
        "Amount": "-0.90",
        "Memo": "",
    }
    expected = {
        "date": "12/29/2020",
        "description": "PAS*PASSPT PK BOSTON",
        "category": "Travel",
        "amount": 0.9,
        "source": "chase",
        "source_file": "chase.csv",
    }
    card, card_def = identify_card(input_)
    assert parse_record(input_, card, card_def) == expected

    input_ = {
        "source_file": "usbank.csv",
        "Date": "12/18/2018",
        "Transaction": "CREDIT",
        "Name": "REI #80 BOSTON BOSTON MA",
        "Memo": "12345; ; ; ; ",
        "Amount": "59.89",
    }
    expected = {
        "date": "12/18/2018",
        "description": "REI #80 BOSTON BOSTON MA",
        "amount": -59.89,
        "category": "",
        "source": "usbank",
        "source_file": "usbank.csv",
    }
    card, card_def = identify_card(input_)
    assert parse_record(input_, card, card_def) == expected


def _parse(card_name, **row):
    input_ = {"source_file": f"{card_name}.csv", **row}
    card, card_def = identify_card(input_)
    assert card == card_name
    return parse_record(input_, card, card_def)["amount"]


def test_citi_debit_is_positive_spending():
    row = {
        "Status": "Cleared",
        "Date": "02/06/2026",
        "Description": "SHOP",
        "Debit": "109.06",
        "Credit": "",
    }
    assert _parse("citi", **row) == 109.06


def test_citi_credit_stays_negative():
    """Citi writes credits (refunds, payments) as negative numbers; they must not be negated again."""
    row = {
        "Status": "Cleared",
        "Date": "02/06/2026",
        "Description": "PAYMENT",
        "Debit": "",
        "Credit": "-109.06",
    }
    assert _parse("citi", **row) == -109.06
    row["Credit"] = "-1,109.06"
    assert _parse("citi", **row) == -1109.06


def test_a_credit_is_negative_whichever_sign_the_bank_writes():
    row = {
        "Status": "Cleared",
        "Date": "02/06/2026",
        "Description": "REFUND",
        "Debit": "",
        "Credit": "$12.50",
    }
    assert _parse("citi", **row) == -12.5


def test_capital_one_credits_are_unchanged():
    row = {
        "Transaction Date": "2024-01-02",
        "Posted Date": "2024-01-03",
        "Card No.": "1234",
        "Description": "PAYMENT",
        "Category": "Payment/Credit",
        "Debit": "",
        "Credit": "50.00",
    }
    assert _parse("capital_one", **row) == -50.0
    assert _parse("capital_one", **{**row, "Debit": "7.25", "Credit": ""}) == 7.25
