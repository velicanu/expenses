"""Record class."""
import matplotlib.pyplot as plt
import pandas as pd

from common import flip_spending_sign
from extract import read_to_dict
from parse import get_card_from_filename, get_parser
from standardize import standardizer


class Card(object):
    """Class for a single credit card, and associated records."""

    def __init__(self, filename, card=None, df=None):
        """Init."""
        self.filename = filename
        if card is None:
            self.card = get_card_from_filename(filename)
            self.parser = get_parser(filename)
        else:
            self.card = card
            self.parser = get_parser(card)
        if df is not None:
            self._records = df.copy(deep=True)
            self._records.index = pd.to_datetime(self._records["date"])

    def read_expenses(self):
        """Read expenses."""
        records = read_to_dict(self.filename)
        records = [standardizer(self.parser(record)) for record in records]
        records_df = pd.DataFrame(flip_spending_sign(records))
        records_df.index = pd.to_datetime(records_df["date"])
        self._records = records_df

    @property
    def category_colors(self):
        """Generate colors for each unique category.

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
            self._records = pd.DataFrame(records)
        elif isinstance(records, pd.DataFrame):
            self._records = records
        else:
            raise TypeError("Records cannot be converted to dataframe.")

    @property
    def record_is_payment(self):
        """Mask for payments (as opposed to expenses)."""
        return (
            self.records["description"]
            .str.lower()
            .str.contains("autopay|thank you|payment")
        )

    @property
    def monthly_spending(self):
        """Monthly totals by category."""
        records_df = self.records[~self.record_is_payment]
        return (
            records_df.groupby([pd.Grouper(freq="M"), "category"]).sum().reset_index()
        )

    def plot_categories(self, include_payments=False):
        """Barplot of expense across categories for entire expense record selected."""
        records_df = self.records
        if not include_payments:
            records_df = records_df[~self.record_is_payment]
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
        self.monthly_spending.pivot(index="date", columns="category").plot(
            kind="bar", stacked=stacked
        )
