import os
import sqlite3

import click
import pandas as pd

from common import get_log

log = get_log(__file__)


@click.command()
@click.argument("infiles", type=click.File("r"), nargs=-1)
@click.argument("table", type=str)
@click.argument("outfile", type=str)
def ingest(infiles, table, outfile):
    """Converts ingests records into SQLite"""

    log.info(f"Ingesting {[f.name for f in infiles]} into {outfile}:{table}")

    if os.path.exists(outfile):
        os.remove(outfile)

    con = sqlite3.connect(outfile)
    df = None
    for infile in infiles:
        df = (
            df.append(pd.read_json(infile, lines=True))
            if df is not None
            else pd.read_json(infile, lines=True)
        )

    df.to_sql(table, con)


if __name__ == "__main__":
    ingest()
