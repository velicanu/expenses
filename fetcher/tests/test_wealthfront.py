import pytest
from fetcher import wealthfront
from fetcher.pageutil import PageError


class _Timeout(Exception):
    pass


_Timeout.__name__ = "TimeoutError"


class _Loc:
    def __init__(self, page, name, present=True):
        self.page, self.name, self.present = page, name, present
        self.first = self

    def wait_for(self, state, timeout):
        if not self.present:
            raise _Timeout()

    def count(self):
        return 1 if self.present else 0

    def click(self):
        self.page.clicks.append(self.name)


class _Download:
    def __init__(self, path):
        self.value = type("D", (), {"path": lambda s: path})()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Page:
    def __init__(self, path, missing=()):
        self.url, self.clicks, self.path, self.missing = (
            "https://www.wealthfront.com/dashboard",
            [],
            path,
            missing,
        )

    def get_by_text(self, text, exact=False):
        name = text if isinstance(text, str) else text.pattern
        return _Loc(self, name, name not in self.missing)

    def get_by_role(self, role, name=None):
        return _Loc(self, name.pattern, name.pattern not in self.missing)

    def expect_download(self, timeout):
        return _Download(self.path)


def test_it_walks_the_pages_the_way_a_person_does(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("Transaction date,Description,Type,Amount\n")
    page = _Page(str(f))
    assert wealthfront.fetch_statements(page, ["2026-11"]) == [
        {"month": "all", "csv": "Transaction date,Description,Type,Amount\n"}
    ]
    assert page.clicks == [
        "Individual Cash Account",
        "see all activity",
        "download activity",
        "All time",
        "Download CSV",
    ]


def test_a_missing_control_is_a_page_error_not_a_wrong_click(tmp_path):
    page = _Page(str(tmp_path / "x"), missing=("All time",))
    with pytest.raises(PageError, match="All time choice did not appear"):
        wealthfront.download_all(page)
    assert "Download CSV" not in page.clicks


def test_a_download_that_is_not_the_export_is_refused(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("<html>oops</html>")
    with pytest.raises(PageError):
        wealthfront.download_all(_Page(str(f)))
