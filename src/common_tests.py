import io
import os
import tempfile
import unittest

from werkzeug.datastructures import FileStorage

from common import records_from_file, save_file_if_valid

input_string = """
Transaction Date,Post Date,Description,Category,Type,Amount
12/30/2019,12/31/2019,THE LANDING PIZZA AND KIT,Food & Drink,Sale,-44.00
12/29/2019,12/30/2019,TST* SWEET RICE - JP,Food & Drink,Sale,-51.37
"""
unknown_string = """
Foo,Bar,Baz,Spam,Ham,Jam
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


class TestCommon(unittest.TestCase):
    def test_records_from_file_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_ = os.path.join(tmpdir, "input.csv")
            with open(input_, "w") as _f:
                _f.write(input_string)

            actual = records_from_file(open(input_, "r"))

            self.assertEqual(expected, actual)

    def test_records_from_file_stream(self):
        with io.BytesIO() as _f:
            _f.write(input_string.encode("utf-8"))
            _f.seek(0)

            actual = records_from_file(_f)

            self.assertEqual(expected, actual)

    def test_save_file_if_valid_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as upload_folder:
            filename = "input.csv"
            input_ = os.path.join(tmpdir, filename)
            with open(input_, "w") as _f:
                _f.write(input_string)
            file_object = FileStorage(open(input_, "rb"))

            expected = "success", f"{filename}: chase"
            actual = save_file_if_valid(file_object, filename, upload_folder)
            self.assertEqual(expected, actual)

            with open(os.path.join(upload_folder, filename), "r") as uploaded_file:
                self.assertTrue(input_string, uploaded_file.read())

    def test_save_file_if_valid_invalid(self):
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as upload_folder:
            filename = "input.csv"
            input_ = os.path.join(tmpdir, filename)
            with open(input_, "w") as _f:
                _f.write(unknown_string)
            file_object = FileStorage(open(input_, "rb"))

            expected = "failed", f"{filename}"
            actual = save_file_if_valid(file_object, filename, upload_folder)
            self.assertEqual(expected, actual)

            with self.assertRaises(FileNotFoundError):
                open(os.path.join(upload_folder, filename), "r")
