from standardize import get_default_categories, newest_first, ordered, standardizer


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


# --- pks stay put as new rows arrive -----------------------------------------------------------------


def _rows(days, per_day, start=0, source="card.csv"):
    """Records for `days` consecutive dates with `per_day` rows each, in the order a file lists them."""
    out = []
    for d in range(start, start + days):
        for n in range(per_day):
            out.append(
                {
                    "date": f"20{20 + d // 28:02d}-01-{1 + d % 28:02d}T00:00:00",
                    "description": f"row-{d}-{n}",
                    "source_file": source,
                }
            )
    return out


def _pk_by_description(records):
    return {r["description"]: r["pk"] for r in ordered(records)}


def test_newest_first_detection():
    assert newest_first(["2024-03-01", "2024-02-01", "2024-01-01"])
    assert not newest_first(["2024-01-01", "2024-02-01", "2024-03-01"])
    assert not newest_first(["2024-01-01", "2024-01-01"])  # all one day: leave it alone
    assert not newest_first(["2024-01-01"])
    assert not newest_first([])


def test_prepending_newer_rows_to_a_newest_first_file_keeps_every_old_pk():
    """The wealthfront case: 628 rows, 480 of them sharing a date; 136 newer rows arrive at the top.
    With pandas' default (unstable) sort the tie order changed with the length and pks shifted."""
    old_oldest_first = _rows(days=157, per_day=4)  # 628 rows
    old_file = old_oldest_first[::-1]  # the exporter lists newest first
    new_rows = _rows(
        days=34, per_day=4, start=157
    )  # 136 rows, all newer than every old row
    new_file = new_rows[::-1] + old_file  # ...and puts them at the top
    before, after = _pk_by_description(old_file), _pk_by_description(new_file)
    assert len(after) == 628 + 136
    assert all(after[d] == pk for d, pk in before.items())


def test_appending_rows_to_an_oldest_first_file_keeps_every_old_pk():
    old_file = _rows(days=157, per_day=4)
    new_file = old_file + _rows(days=34, per_day=4, start=157)
    before, after = _pk_by_description(old_file), _pk_by_description(new_file)
    assert all(after[d] == pk for d, pk in before.items())


def test_a_late_row_on_the_newest_date_does_not_move_older_rows_in_a_newest_first_file():
    old_file = _rows(days=40, per_day=3)[::-1]
    newest_date = old_file[0]["date"]
    late = {"date": newest_date, "description": "late", "source_file": "card.csv"}
    new_file = [late] + old_file  # newest-first: the new row goes on top
    before, after = _pk_by_description(old_file), _pk_by_description(new_file)
    assert all(after[d] == pk for d, pk in before.items())
    assert after["late"] == f"card.csv-{len(old_file)}"  # it is the last row


def test_ordering_is_chronological_with_pk_and_line():
    out = ordered(_rows(days=3, per_day=2)[::-1])
    assert [r["date"] for r in out] == sorted(r["date"] for r in out)
    assert [r["line"] for r in out] == list(range(6))
    assert [r["pk"] for r in out] == [f"card.csv-{i}" for i in range(6)]
