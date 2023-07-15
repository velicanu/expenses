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


def _get_newline(infile):
    with open(infile, "rb") as inf:
        rn_pos = inf.read().find(b"\r\n")
    return "\n" if rn_pos == -1 else "\r\n"


def _clean_barclays(instr):
    if instr.startswith("Barclays Bank Delaware"):
        idx = instr.find("\n \n") + 3
        return instr[idx:]
    return instr


def records_from_file(infile):
    """
    This function returns a generator of json records from an input csv.

    :param infile: Input csv file or stream
    :return: generator of json records
    """
    if type(infile) == str:
        infile = open(infile, "r", newline=_get_newline(infile))

    with tempfile.TemporaryDirectory() as tmpdir:
        # first clean the file
        with open(os.path.join(tmpdir, "tmp.txt"), "w") as tmpfile:
            input_ = infile.read()
            if isinstance(infile, io.BytesIO):
                input_ = input_.decode("utf-8")
            # amex csv export breaks python csv parser due to double "" inside "
            input_ = input_.replace('"""', '"@')
            input_ = input_.replace('""', "@")
            # usalliance has terrible newlines
            input_ = input_.replace("\n\n", "\n")
            # barclays adds garbage to the start of their csv
            input_ = _clean_barclays(input_)
            dialect = csv.Sniffer().sniff(input_)
            tmpfile.write(input_)

        records = []
        with open(os.path.join(tmpdir, "tmp.txt"), "r") as tmpfile:
            reader = csv.reader(tmpfile, dialect)
            header = next(reader)
            for row in reader:
                if not row:
                    continue
                # for python 3.8 and 3.9 compatibility. strict zip is 3.10+
                if len(header) != len(row):
                    raise ValueError(f"length mismatch: {len(header)}!={len(row)}")
                _row = dict(zip(header, row))  # noqa:B905
                # don't return null rows
                if any(_row.values()):
                    records.append(_row)
        return records
