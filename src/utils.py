import json
import os
import sqlite3
import time

import pandas as pd
import requests

from common import get_log
from plaidlib import get_institution, get_item

log = get_log(__file__)


def make_dirs(list_of_dirs):
    """
    Makes internal directories if they don't exist
    """
    for dir_ in list_of_dirs:
        os.makedirs(dir_, exist_ok=True)


def clear(streamlit_object, seconds):
    time.sleep(seconds)
    streamlit_object.empty()


def get_config(config_file):
    try:
        return json.load(open(config_file))
    except FileNotFoundError:
        return {}


def put_config(config_file, config):
    with open(config_file, "w") as f:
        f.write(json.dumps(config))


def get_institution_st(access_token):
    institution_id = get_item(access_token)["institution_id"]
    institution_name = get_institution(
        access_token=access_token, institution_id=institution_id
    )["name"]
    return institution_name


def get_access_token(url="http://localhost:8000/api/info"):
    try:
        r = requests.post(url)
        data = r.json()
        return data["access_token"]
    except Exception as e:
        log.warning(f"Failed to get plaid token: {str(e)}")


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
