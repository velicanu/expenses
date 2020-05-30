import csv
import io
import json

import click
import numpy as np
import pandas as pd

from common import get_log

log = get_log(__file__)


def read_to_dict(infile):
    payload = infile.read(2048)
    if isinstance(infile, io.BytesIO):
        payload = payload.decode("utf-8")
    dialect = csv.Sniffer().sniff(payload)
    infile.seek(0)
    return (
        pd.read_csv(infile, dialect=dialect)
        .replace({np.nan: None})
        .to_dict(orient="records")
    )


@click.command()
@click.argument("infile", type=click.File("r"))
@click.argument("outfile", type=click.File("w"))
def extract(infile, outfile):
    """Converts excel and csv files into json"""
    records = read_to_dict(infile)
    log.info(f"Extracting {infile} into {outfile.name}")
    for record in records:
        outfile.write(f"{json.dumps(record)}\n")


if __name__ == "__main__":
    extract()
