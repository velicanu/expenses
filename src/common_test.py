import io
import os
import tempfile

import pytest

from common import _clean_barclays, records_from_file
from detect import save_file_if_valid

input_string = """Transaction Date,Post Date,Description,Category,Type,Amount,Memo
12/30/2019,12/31/2019,THE LANDING PIZZA AND KIT,Food & Drink,Sale,-44.00,
12/29/2019,12/30/2019,TST* SWEET RICE - JP,Food & Drink,Sale,-51.37,
,,,,,,
"""
unknown_string = """Foo,Bar,Baz,Spam,Ham,Jam
12/30/2019,12/31/2019,THE LANDING PIZZA AND KIT,Food & Drink,Sale,-44.00
12/29/2019,12/30/2019,TST* SWEET RICE - JP,Food & Drink,Sale,-51.37
"""
expected = [
    {
        "Transaction Date": "12/30/2019",
        "Post Date": "12/31/2019",
        "Description": "THE LANDING PIZZA AND KIT",
        "Category": "Food & Drink",
        "Type": "Sale",
        "Amount": "-44.00",
        "Memo": "",
    },
    {
        "Transaction Date": "12/29/2019",
        "Post Date": "12/30/2019",
        "Description": "TST* SWEET RICE - JP",
        "Category": "Food & Drink",
        "Type": "Sale",
        "Amount": "-51.37",
        "Memo": "",
    },
]


def test_clean_barclays():
    input_ = """Barclays Bank Delaware
Account Number: XXXXXXXXXXXX1330
Account Balance as of January 1 2022:    $0.00
 
Transaction Date,Description,Category,Amount
11/13/2021,"Payment Received","CREDIT",193.64
10/22/2021,"THDCAPEAIR AIR TKT","DEBIT",-193.64"""
    expected = """Transaction Date,Description,Category,Amount
11/13/2021,"Payment Received","CREDIT",193.64
10/22/2021,"THDCAPEAIR AIR TKT","DEBIT",-193.64"""
    actual = _clean_barclays(input_)
    assert actual == expected


def test_records_from_file_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        input_ = os.path.join(tmpdir, "input.csv")
        with open(input_, "w") as _f:
            _f.write(input_string)

        actual = list(records_from_file(open(input_, "r")))

        assert actual == expected


def test_records_from_file_stream():
    with io.BytesIO() as _f:
        _f.write(input_string.encode("utf-8"))
        _f.seek(0)

        actual = list(records_from_file(_f))

        assert actual == expected


@pytest.mark.fails_on_windows
def test_save_file_if_valid_valid():
    with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as data_dir:
        filename = "input.csv"
        input_ = os.path.join(tmpdir, filename)
        with open(input_, "w") as _f:
            _f.write(input_string)
        file_object = open(input_, "rb")

        expected = "success", f"{filename}: chase"
        actual = save_file_if_valid(file_object, data_dir)
        assert actual == expected

        with open(os.path.join(data_dir, "raw", filename), "r") as uploaded_file:
            assert input_string == uploaded_file.read()


@pytest.mark.fails_on_windows
def test_save_file_if_valid_invalid():
    with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as data_dir:
        filename = "input.csv"
        input_ = os.path.join(tmpdir, filename)
        with open(input_, "w") as _f:
            _f.write(unknown_string)
        file_object = open(input_, "rb")

        expected = "failed", f"{filename}"
        actual = save_file_if_valid(file_object, data_dir)
        assert actual == expected

        with pytest.raises(FileNotFoundError):
            open(os.path.join(data_dir, "raw", filename), "r")
