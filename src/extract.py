import json
import os

import click

from common import get_log, records_from_file

log = get_log(__file__)


def extract(infile, outfile):
    """Converts csv files into json, returns the output filename"""
    records = records_from_file(infile)
    with open(outfile, "w") as outf:
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
