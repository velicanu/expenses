import json

import click

from common import get_log, records_from_file

log = get_log(__file__)


@click.command()
@click.argument("infile", type=click.File("r"))
@click.argument("outfile", type=click.File("w"))
def extract(infile, outfile):
    """Converts excel and csv files into json"""
    records = records_from_file(infile)
    log.info(f"Extracting {infile} into {outfile.name}")
    for record in records:
        outfile.write(f"{json.dumps(record)}\n")


if __name__ == "__main__":
    extract()
