import os
import sqlite3

import click
import pandas as pd

from common import get_log
from sql import add_pk_to_sqlite_table

log = get_log(__file__)


def ingest(infiles, table, outfile):
    """Converts ingests records into SQLite"""

    log.info(f"Ingesting {infiles} into {outfile}:{table}")

    if os.path.exists(outfile):
        os.remove(outfile)

    con = sqlite3.connect(outfile)
    df = pd.concat([pd.read_json(f, lines=True) for f in infiles])

    df.to_sql(table, con, index=False)
    add_pk_to_sqlite_table(tablename="expenses", index_column="pk", connection=con)


@click.command()
@click.argument("infiles", type=str, nargs=-1)
@click.argument("table", type=str)
@click.argument("outfile", type=str)
def _ingest(infiles, table, outfile):
    ingest(infiles, table, outfile)


if __name__ == "__main__":
    _ingest()
