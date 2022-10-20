import sqlite3
import textwrap
from datetime import datetime

import pandas as pd
import pytest

from sql import (
    add_pk_to_create_table_string,
    add_pk_to_sqlite_table,
    get_create_table_string,
    insert_rows,
)


@pytest.fixture()
def conn():
    conn_ = sqlite3.connect(":memory:")
    pd.DataFrame(
        [
            {"date": datetime(2020, 1, 1, 1, 1, 1), "desc": "abc", "amount": 123},
            {"date": datetime(2020, 1, 1, 1, 1, 2), "desc": "def", "amount": 456},
        ]
    ).to_sql("test", conn_, index=False)
    yield conn_


CREATE_TABLE_STRING = """
CREATE TABLE "test" (
"date" TIMESTAMP,
  "desc" TEXT,
  "amount" INTEGER
)
""".strip()


def test_get_create_table_string(conn):
    actual = get_create_table_string("test", conn)
    expected = CREATE_TABLE_STRING
    assert actual == expected


def test_add_pk_to_create_table_string():
    actual = add_pk_to_create_table_string(CREATE_TABLE_STRING, "desc")
    expected = textwrap.dedent(
        """
    CREATE TABLE "test" (
    "date" TIMESTAMP,
      "desc" TEXT PRIMARY KEY,
      "amount" INTEGER
    )
    """
    ).strip()
    assert actual == expected

    actual = add_pk_to_create_table_string(CREATE_TABLE_STRING, "amount")
    expected = textwrap.dedent(
        """
    CREATE TABLE "test" (
    "date" TIMESTAMP,
      "desc" TEXT,
      "amount" INTEGER PRIMARY KEY
    )
    """
    ).strip()
    assert actual == expected


def test_add_pk_to_sqlite_table(conn):
    add_pk_to_sqlite_table("test", "date", conn)

    actual = get_create_table_string("test", conn)
    expected = textwrap.dedent(
        """
    CREATE TABLE "test" (
    "date" TIMESTAMP PRIMARY KEY,
      "desc" TEXT,
      "amount" INTEGER
    )
    """
    ).strip()
    assert actual == expected


def test_insert_rows(conn):
    input_ = [
        {"date": datetime(2020, 1, 1, 1, 1, 3), "desc": "ggg", "amount": 777},
        {"date": datetime(2020, 1, 1, 1, 1, 4), "desc": "hhh", "amount": 888},
    ]
    insert_rows(input_, "test", conn)
    actual = pd.read_sql("SELECT * FROM test", conn).to_dict(orient="records")
    expected = [
        {"date": "2020-01-01 01:01:01", "desc": "abc", "amount": 123},
        {"date": "2020-01-01 01:01:02", "desc": "def", "amount": 456},
        {"date": "2020-01-01 01:01:03", "desc": "ggg", "amount": 777},
        {"date": "2020-01-01 01:01:04", "desc": "hhh", "amount": 888},
    ]
    assert actual == expected
