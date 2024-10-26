from standardize import get_default_categories, standardizer


def test_standardize():
    input_ = {
        "date": "12/30/2019",
        "description": "THE LANDING PIZZA AND KIT",
        "amount": -44.0,
        "category": "Food & Drink",
        "source": "chase",
        "source_file": "test",
    }
    expected = {
        "date": "2019-12-30T00:00:00",
        "description": "THE LANDING PIZZA AND KIT",
        "amount": -44.0,
        "category": "Dining",
        "source": "chase",
        "source_file": "test",
        "old_category": "Food & Drink",
    }
    actual = standardizer(input_, {})
    assert actual == expected


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
        "old_category": "Dining",
    }
    actual = standardizer(input_, {})
    assert actual == expected

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
        "old_category": "Other Travel",
    }
    actual = standardizer(input_, {})
    assert actual == expected


def test_get_default_categories():
    actual = get_default_categories()
    expected = {
        "Entertainment",
        "Bills",
        "Family",
        "Fees",
        "Groceries",
        "Car",
        "Shopping",
        "Travel",
        "Rent",
        "Health",
        "Rideshare",
        "Dining",
        "Services",
        "Payment",
    }

    assert actual == expected
