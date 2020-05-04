"""Record class."""
from parse import get_parser, get_card_from_filename
from extract import read_to_dict
from standardize import standardizer
from common import flip_spending_sign
import pandas as pd
import matplotlib.pyplot as plt


class Card(object):
    """Class for a single credit card, and associated records."""
    def __init__(self, filename, card=None):
        """Init."""
        self.filename = filename
        if card is None:
            self.card = get_card_from_filename(filename)
            self.parser = get_parser(filename)
        else:
            self.card = card
            self.parser = get_parser(card)

    def read_expenses(self):
        """Read expenses."""
        records = read_to_dict(self.filename)
        records = [standardizer(self.parser(record)) for record in records]
        self._records = pd.DataFrame(flip_spending_sign(records))

    @property
    def category_colors(self):
        """Generate colors for each unique category

        So that plot colors stay consistent throughout.
        """
        categories = self.records["category"].unique()
        colors = plt.get_cmap("tab10").colors
        cmap = {cat: colors[i] for i, cat in enumerate(categories)}
        return pd.Series(cmap)

    @property
    def records(self):
        """Records."""
        return self._records

    @records.setter
    def records(self, records):
        """Set records."""
        if isinstance(records, list) or isinstance(records, dict):
            self.records = pd.DataFrame(records)
        elif isinstance(records, pd.DataFrame):
            self.records = records

    def plot_categories(self, include_payments=False):
        """Barplot of expense across categories for entire expense record selected."""
        records_df = self.records
        if not include_payments:
            records_df = records_df[~records_df['description'].str.contains('THANK YOU')]
        records_df[["category", "amount"]].groupby("category")["amount"].sum().plot(
            x="category", y="amount", kind="bar", color=self.category_colors
        )

    def plot_over_time(self, freq="M", stacked=True, include_payments=False):
        """Plot expenses over time.

        Parameters
        ----------
        freq: str
            interval for which to plot expenses. {M: month, W: week}. See pd.Grouper for other options.
        stacked: bool
            stack bars by category. If False, defaults to a grouped barplot.
        include_payments: False
            include credit card payments in records whil plotting.
        """
        records_df = self.records
        if not include_payments:
            records_df = records_df[~records_df['description'].str.contains('THANK YOU')]
        records_df.index = pd.to_datetime(records_df["date"])
        records_df.groupby(
            [pd.Grouper(freq=freq), "category"]
        ).sum().reset_index().pivot(index="date", columns="category").plot(
            kind="bar", stacked=stacked
        )
