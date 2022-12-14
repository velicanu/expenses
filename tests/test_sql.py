import sqlite3
import textwrap
from datetime import datetime

import pandas as pd
import pytest

from sql import (
    _get_apply_changes_query,
    _get_columns,
    add_pk_to_create_table_string,
    add_pk_to_sqlite_table,
    apply_changes,
    get_create_table_string,
    insert_rows,
    run_sql,
)


@pytest.fixture()
def df():
    yield pd.DataFrame(
        [
            {"date": datetime(2020, 1, 1, 1, 1, 1), "desc": "abc", "amount": 123},
            {"date": datetime(2020, 1, 1, 1, 1, 2), "desc": "def", "amount": 456},
        ]
    )


@pytest.fixture()
def conn(df):
    with sqlite3.connect(":memory:") as conn_:
        df.to_sql("test", conn_, index=False)
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


def test_apply_changes():
    df_initial = pd.DataFrame(
        [
            {"a": 123, "b": "abc", "pk": 1},
            {"a": 456, "b": "def", "pk": 2},
            {"a": 789, "b": "ghi", "pk": 3},
        ]
    )
    df_changes = pd.DataFrame(
        [
            {"a": 999, "b": "zzz", "pk": 2},
            {"a": 444, "b": "fff", "pk": 4},
        ]
    )
    actual_df = apply_changes(df_initial, df_changes)
    actual = sorted(actual_df.to_dict(orient="records"), key=lambda x: x["pk"])
    expected = [
        {"a": 123, "b": "abc", "pk": 1},
        {"a": 999, "b": "zzz", "pk": 2},
        {"a": 789, "b": "ghi", "pk": 3},
        {"a": 444, "b": "fff", "pk": 4},
    ]
    assert actual == expected


def test_run_sql(df):
    actual_df = run_sql(
        "SELECT desc,amount FROM expenses WHERE amount < 200", df, table_name="expenses"
    )
    actual = actual_df.to_dict(orient="records")
    expected = [{"desc": "abc", "amount": 123}]
    assert actual == expected


def test_get_columns(df):
    actual = _get_columns(df, "foo")
    expected = "foo.date,foo.desc,foo.amount"
    assert actual == expected


def test_get_apply_changes_query(df):
    actual = _get_apply_changes_query(df).strip()
    expected = textwrap.dedent(
        """
    SELECT chdf.date,chdf.desc,chdf.amount
    FROM df
        JOIN chdf
            ON df.pk = chdf.pk
    UNION ALL
    SELECT chdf.date,chdf.desc,chdf.amount
    FROM chdf
        LEFT JOIN df
            ON df.pk = chdf.pk
    WHERE df.pk IS NULL
    UNION ALL
    SELECT df.date,df.desc,df.amount
    FROM df
        LEFT JOIN chdf
            ON df.pk = chdf.pk
    WHERE chdf.pk IS NULL
    """
    ).strip()

    assert actual == expected
