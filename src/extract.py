import json
import os

import click

from common import get_log, records_from_file

log = get_log(__file__)


def _get_newline(infile):
    with open(infile, "rb") as inf:
        rn_pos = inf.read().find(b"\r\n")
    return "\n" if rn_pos == -1 else "\r\n"


def extract(infile, outfile):
    """Converts csv files into json, returns the output filename"""
    with open(infile, "r", newline=_get_newline(infile)) as inf, open(
        outfile, "w"
    ) as outf:
        records = records_from_file(inf)
        log.info(f"Extracting {infile} into {outfile}")
        for record in records:
            record["source_file"] = os.path.basename(infile)
            outf.write(f"{json.dumps(record)}\n")


@click.command()
@click.argument("infile", type=str)
@click.argument("outfile", type=str)
def _extract(infile, outfile):
    extract(infile, outfile)


if __name__ == "__main__":
    _extract()
