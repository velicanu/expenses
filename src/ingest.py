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

    # Build next to the target and rename into place, so a reader (the API, or Syncthing) sees either
    # the old database or the new one, never a missing or half-written file.
    tmpfile = outfile + ".tmp"
    if os.path.exists(tmpfile):
        os.remove(tmpfile)

    con = sqlite3.connect(tmpfile)
    try:
        df = pd.concat([pd.read_json(f, lines=True) for f in infiles])
        df.to_sql(table, con, index=False)
        add_pk_to_sqlite_table(tablename="expenses", index_column="pk", connection=con)
    except BaseException:
        con.close()
        if os.path.exists(tmpfile):
            os.remove(tmpfile)
        raise
    con.close()
    os.replace(tmpfile, outfile)


@click.command()
@click.argument("infiles", type=str, nargs=-1)
@click.argument("table", type=str)
@click.argument("outfile", type=str)
def _ingest(infiles, table, outfile):
    ingest(infiles, table, outfile)


if __name__ == "__main__":
    _ingest()
