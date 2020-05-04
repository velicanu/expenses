"""Record class."""
from parse import get_parser, get_card
from extract import read_to_dict
from standardize import standardizer, strip_payment
from common import flip_spending_sign
import pandas as pd
import matplotlib.pyplot as plt


class CardRecord(object):
    def __init__(self, filename):
        self.filename = filename
        self.card = get_card(filename)
        self.parser = get_parser(filename)

    def read_expenses(self):
        records = read_to_dict(self.filename)
        records = [standardizer(self.parser(record)) for record in records]
        self.records = flip_spending_sign(records)

    def to_df(self):
        return pd.DataFrame(self.records)

    @property
    def category_colors(self):
        categories = self.to_df()["category"].unique()
        colors = plt.get_cmap("tab10").colors
        cmap = {cat: colors[i] for i, cat in enumerate(categories)}
        return pd.Series(cmap)

    def plot_categories(self):
        records_df = pd.DataFrame(strip_payment(self.records))
        records_df[["category", "amount"]].groupby("category")["amount"].sum().plot(
            x="category", y="amount", kind="bar", color=self.category_colors
        )

    def plot_over_time(self, freq="M", stacked=True):
        records_df = pd.DataFrame(strip_payment(self.records))
        records_df.index = pd.to_datetime(records_df["date"])
        records_df.groupby(
            [pd.Grouper(freq="M"), "category"]
        ).sum().reset_index().pivot(index="date", columns="category").plot(
            kind="bar", stacked=stacked
        )
