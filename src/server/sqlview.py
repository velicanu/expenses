"""The "Input sql" box of the old app: the query its sidebar widgets build, and running a query over the data.

The Streamlit app pasted the widgets into a SELECT and ran whatever was in the box against an in-memory copy
of the data (table `expenses`). Both are kept, quirks included, so the numbers are the old ones:

- the end date is compared as text, so `date <= "2026-06-26"` leaves out rows ON 2026-06-26
  ("2026-06-26 00:00:00" sorts after "2026-06-26");
- a lone `!term` in the description box is not negated (only `a+!b` / `a^!b` are).

What is new: the query runs with a read-only authorizer (SELECT only: no ATTACH, no PRAGMA, nothing that
writes), a time limit, and a row cap, since the text box is now a web endpoint.
"""

import sqlite3
import time

import dateutil.parser
import pandas as pd

MAX_SECONDS = 10.0
MAX_ROWS = 50_000
DESCRIPTION_WARNING = "invalid description, only one of + or ^ supported at a time"

# sqlite3 authorizer action codes that a read-only query needs
_ALLOWED = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


class QueryError(ValueError):
    pass


def _extend(statement: str) -> str:
    return (
        statement + " WHERE "
        if " where " not in statement.lower()
        else statement + " AND "
    )


def _in_list(values) -> str:
    return f"{tuple(c for c in values)}" if len(values) > 1 else f"('{values[0]}')"


def _valid_description(value: str):
    operators = sum(1 for op in ("+", "^") if op in value)
    return operators <= 1 and value


def default_query(
    df: pd.DataFrame, start, end, category_in, category_not_in, description, sources
):
    """-> (query, warning). `df` is the data the widgets were built from (edits applied, zero amounts out)."""
    query = "SELECT * FROM expenses"
    if df.empty:
        return query, None

    lo = dateutil.parser.parse(df["date"].min()).isoformat().replace("T00:00:00", "")
    hi = dateutil.parser.parse(df["date"].max()).isoformat().replace("T00:00:00", "")
    if start and start.isoformat() != lo:
        query = _extend(query) + f'date >= "{start.isoformat()}"'
    if end and end.isoformat() != hi:
        query = _extend(query) + f'date <= "{end.isoformat()}"'

    for selection, selected in (("in", category_in), ("not in", category_not_in)):
        if selected:
            query = _extend(query) + f"category {selection} " + _in_list(selected)

    warning = None
    title = description.replace("*", "%")
    if not _valid_description(title):
        if title:
            warning = DESCRIPTION_WARNING
    elif "+" in title:
        query = _extend(query) + "(" + _like_terms(title.split("+"), " OR ") + ")"
    elif "^" in title:
        query = _extend(query) + "(" + _like_terms(title.split("^"), " AND ") + ")"
    else:
        query = _extend(query) + f"description LIKE '%{title}%'"

    if sources:
        query = _extend(query) + "source_file in " + _in_list(sources)
    return query, warning


def _like_terms(terms, joiner: str) -> str:
    return joiner.join(
        f"description LIKE '%{s}%'"
        if not s.startswith("!")
        else f"description NOT LIKE '%{s[1:]}%'"
        for s in terms
    )


def run_query(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """The query's result. The data is copied into a fresh in-memory database as table `expenses`."""
    if not query.strip():
        raise QueryError("empty query")
    conn = sqlite3.connect(":memory:")
    try:
        df.to_sql("expenses", conn, index=False)
        conn.set_authorizer(
            lambda action, *_: sqlite3.SQLITE_OK
            if action in _ALLOWED
            else sqlite3.SQLITE_DENY
        )
        deadline = time.monotonic() + MAX_SECONDS
        conn.set_progress_handler(
            lambda: 1 if time.monotonic() > deadline else 0, 10_000
        )
        try:
            out = pd.read_sql(query, conn)
        except (
            Exception
        ) as e:  # sqlite3 errors, pandas wrappers, "not authorized", "interrupted"
            raise QueryError(_reason(e)) from None
    finally:
        conn.close()
    return out


def _reason(e: Exception) -> str:
    text = str(e)
    if "not authorized" in text:
        return "only SELECT queries are allowed"
    if "interrupted" in text:
        return f"the query took longer than {MAX_SECONDS:.0f} seconds"
    # pandas wraps sqlite's message: "Execution failed on sql '...': <reason>"
    return text.rsplit("': ", 1)[-1] if "Execution failed on sql" in text else text


def rows_for_json(df: pd.DataFrame) -> dict:
    """{columns, rows, count} with rows aligned to columns; NaN -> null. Capped at MAX_ROWS."""
    shown = df.head(MAX_ROWS)
    rows = shown.astype(object).where(shown.notna(), None).values.tolist()
    return {
        "columns": [str(c) for c in shown.columns],
        "rows": rows,
        "count": int(len(df)),
    }
