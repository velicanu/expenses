"""
sqlite util functions inspired by:
https://stackoverflow.com/a/47346969
with functionality improved and tests added
"""

import re
import sqlite3

import pandas as pd


def get_create_table_string(tablename, connection):
    sql = f'select * from sqlite_master where name = "{tablename}" and type = "table"'
    result = connection.execute(sql).fetchmany()
    return result[0][4] if result else ""


def add_pk_to_create_table_string(create_table_string, colname):
    regex = f'"{colname}"' + r"\ ([A-Z]*)"
    result = re.sub(regex, f'"{colname}" \\1 PRIMARY KEY', create_table_string, count=1)
    return result


def add_pk_to_sqlite_table(tablename, index_column, connection):
    cts = get_create_table_string(tablename, connection)
    cts = add_pk_to_create_table_string(cts, index_column)
    template = """
    BEGIN TRANSACTION;
        ALTER TABLE {tablename} RENAME TO {tablename}_old_;

        {cts};

        INSERT INTO {tablename} SELECT * FROM {tablename}_old_;

        DROP TABLE {tablename}_old_;

    COMMIT TRANSACTION;
    """

    create_and_drop_sql = template.format(tablename=tablename, cts=cts)
    connection.executescript(create_and_drop_sql)


def insert_rows(rows, tablename, conn):
    row = rows[0]
    columns = ",".join(row.keys())
    values = ",".join(["?" for _ in row])
    sql = f"INSERT OR REPLACE INTO {tablename}({columns}) VALUES ({values})"
    conn.executemany(sql, [list(r.values()) for r in rows])
    conn.commit()


def run_sql(query, df, table_name="df"):
    with sqlite3.connect(":memory:") as conn:
        df.to_sql(table_name, conn, index=False)
        out = pd.read_sql(query, conn)

    return out


def apply_changes(df, chdf):
    with sqlite3.connect(":memory:") as conn:
        df.to_sql("df", conn, index=False)
        chdf.to_sql("chdf", conn, index=False)
        out = pd.read_sql(
            """
            SELECT chdf.*
            FROM df
                JOIN chdf
                    ON df.pk = chdf.pk
            UNION ALL
            SELECT chdf.*
            FROM chdf
                LEFT JOIN df
                    ON df.pk = chdf.pk
            WHERE df.pk IS NULL
            UNION ALL
            SELECT df.*
            FROM df
                LEFT JOIN chdf
                    ON df.pk = chdf.pk
            WHERE chdf.pk IS NULL
            """,
            conn,
        )
    return out
