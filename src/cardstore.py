"""Local copies of Plaid card transactions (cards/<alias>.json -> cards/<alias>.db -> raw/<alias>.csv)."""

import os
import sqlite3

import pandas as pd


def dump_csv(data_dir, db_file, card_id):
    conn = sqlite3.connect(db_file)
    df = pd.read_sql("SELECT * FROM transactions", conn, index_col="transaction_id")
    csv_file = os.path.join(data_dir, "raw", f"{card_id}.csv")
    df.to_csv(csv_file)


def merge_tx(card_dir, card_id):
    new_tx_file = os.path.join(card_dir, f"{card_id}.json")
    df = pd.read_json(open(new_tx_file).read(), lines=True)
    if df.empty:
        return
    df.fillna("", inplace=True)
    df["categories"] = df["category"].apply(lambda x: ",".join(x))

    df_out = df[
        [
            "transaction_id",
            "institution",
            "categories",
            "name",
            "amount",
            "date",
            "authorized_date",
        ]
    ]

    db_file = os.path.join(card_dir, f"{card_id}.db")
    if os.path.exists(db_file):
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        df_out.set_index("transaction_id").to_sql(
            name="temp", con=conn, if_exists="replace"
        )
        cur.execute("INSERT OR IGNORE INTO transactions SELECT * FROM temp")
        conn.commit()
        conn.close()
    else:
        conn = sqlite3.connect(db_file)
        df_out.to_sql(
            name="transactions",
            con=conn,
            dtype={
                "transaction_id": "TEXT PRIMARY KEY",
                "institution": "TEXT",
                "categories": "TEXT",
                "name": "TEXT",
                "amount": "REAL",
                "date": "TIMESTAMP",
                "authorized_date": "TIMESTAMP",
            },
            index=False,
        )
    return db_file
