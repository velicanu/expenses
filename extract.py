import json
import pathlib

import click
import numpy as np
import pandas as pd

from common import get_log

log = get_log(__file__)
READERS = {".xlsx": pd.read_excel, ".xls": pd.read_excel, ".csv": pd.read_csv}


@click.command()
@click.argument("infile", type=str)  # click isn't smart enough to open xlsx :(
@click.argument("outfile", type=click.File("w"))
def extract(infile, outfile):
    """Converts excel and csv files into json"""
    path_info = pathlib.Path(infile)
    reader = READERS[path_info.suffix]

    log.info(f"Extracting {infile} into {outfile.name}")
    records = reader(infile).replace({np.nan: None}).to_dict(orient="records")

    for record in records:
        outfile.write(f"{json.dumps(record)}\n")


if __name__ == "__main__":
    extract()
