from standardize import standardizer


def test_standardize():
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
    assert standardizer(input_) == expected


def test_standardize_payment():
    input_ = {
        "date": "12/4/19",
        "description": "ONLINE PAYMENT - THANK YOU",
        "amount": -8,
        "category": "",
        "source": "amex",
        "source_file": "amex.csv",
    }
    expected = {
        "date": "2019-12-04T00:00:00",
        "description": "ONLINE PAYMENT - THANK YOU",
        "amount": -8,
        "category": "Payment",
        "source": "amex",
        "source_file": "amex.csv",
    }
    assert standardizer(input_) == expected


def test_standardize_rideshare():
    input_ = {
        "date": "2020-03-26",
        "description": "UBER   EATS",
        "amount": 2,
        "category": "Dining",
        "source": "capital_one",
        "source_file": "capital_one.csv",
    }
    expected = {
        "date": "2020-03-26T00:00:00",
        "description": "UBER   EATS",
        "amount": 2,
        "category": "Dining",
        "source": "capital_one",
        "source_file": "capital_one.csv",
    }
    assert standardizer(input_) == expected

    input_ = {
        "date": "2020-01-01",
        "description": "UBER TRIP HELP.UBER.COM",
        "amount": 5,
        "category": "Other Travel",
        "source": "capital_one",
        "source_file": "capital_one.csv",
    }
    expected = {
        "date": "2020-01-01T00:00:00",
        "description": "UBER TRIP HELP.UBER.COM",
        "amount": 5,
        "category": "Rideshare",
        "source": "capital_one",
        "source_file": "capital_one.csv",
    }
    assert standardizer(input_) == expected
