import csv
import io
import logging
import os
import tempfile


def get_files(dir_):
    """
    returns a list of full path filenames in dir
    """
    return [os.path.join(dir_, filename) for filename in os.listdir(dir_)]


def get_log(name):
    log = logging.getLogger(os.path.basename(name))
    logging.basicConfig(level=logging.INFO)
    return log


def flip_spending_sign(records):
    for record in records:
        record["amount"] = -1 * record["amount"]
    return records


def records_from_file(infile):
    """
    This function returns a generator of json records from an input csv.

    :param infile: Input csv file or stream
    :return: generator of json records
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # first clean the file
        with open(os.path.join(tmpdir, "tmp.txt"), "w") as tmpfile:
            input_ = infile.read()
            if isinstance(infile, io.BytesIO):
                input_ = input_.decode("utf-8")
            # amex csv export breaks python csv parser due to double "" inside "
            input_ = input_.replace('"""', '"@')
            input_ = input_.replace('""', "@")
            dialect = csv.Sniffer().sniff(input_)
            tmpfile.write(input_)

        with open(os.path.join(tmpdir, "tmp.txt"), "r") as tmpfile:
            reader = csv.reader(tmpfile, dialect)
            header = next(reader)
            for row in reader:
                _row = {k: v for k, v in zip(header, row)}
                # don't return null rows
                if any([v for v in _row.values()]):
                    yield _row
