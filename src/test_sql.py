import sqlite3
import textwrap
from datetime import datetime

import pandas as pd
import pytest

from sql import (
    add_pk_to_create_table_string,
    add_pk_to_sqlite_table,
    get_create_table_string,
)


@pytest.fixture()
def conn():
    conn_ = sqlite3.connect(":memory:")
    pd.DataFrame(
        [
            {"date": datetime(2020, 1, 1, 1, 1, 1), "desc": "abc", "amount": 123},
            {"date": datetime(2020, 1, 1, 1, 1, 2), "desc": "def", "amount": 456},
        ]
    ).to_sql("test", conn_)
    yield conn_


CREATE_TABLE_STRING = """
CREATE TABLE "test" (
"index" INTEGER,
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
    actual = add_pk_to_create_table_string(CREATE_TABLE_STRING, "index")
    expected = textwrap.dedent(
        """
    CREATE TABLE "test" (
    "index" INTEGER PRIMARY KEY,
      "date" TIMESTAMP,
      "desc" TEXT,
      "amount" INTEGER
    )
    """
    ).strip()
    assert actual == expected

    actual = add_pk_to_create_table_string(CREATE_TABLE_STRING, "amount")
    expected = textwrap.dedent(
        """
    CREATE TABLE "test" (
    "index" INTEGER,
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
    "index" INTEGER,
      "date" TIMESTAMP PRIMARY KEY,
      "desc" TEXT,
      "amount" INTEGER
    )
    """
    ).strip()
    assert actual == expected
