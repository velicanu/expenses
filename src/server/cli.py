"""Command-line jobs, run inside the app's container:  docker exec expenses python -m server.cli pull

pull:        Refresh data for every user with linked Plaid or browser-pulled accounts (what the Refresh data button does).
             One line per account on stdout; exits 1 if any account failed. There is no schedule: data is pulled when
             someone clicks Refresh data (or runs this by hand).
add-direct:  python -m server.cli add-direct USER ACCOUNT   make ACCOUNT (e.g. venmo-dragos, an account on the fetcher's
             credentials page that has a sign-in flow) part of USER's Refresh data.
"""

import argparse
import logging
import sys
import time
import warnings

from .bao import PlaidKeys, PlaidUnavailable
from .direct_pull import FetcherClient
from .plaid_pull import make_client, pull_all
from .settings import Settings
from .store import PipelineBusy, Stores


def pull(settings: Settings, client_factory=make_client, fetcher=None) -> int:
    stores, keys = Stores(settings.data_root), PlaidKeys(settings.bao)
    if fetcher is None and settings.fetcher:
        fetcher = FetcherClient(
            settings.fetcher.url, settings.fetcher.token, settings.fetcher.login_url
        )
    failed = 0
    for user in sorted(set(settings.users.values())):
        store = stores.get(user)
        if not store.accounts() and not store.direct_accounts():
            continue
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            result = pull_all(
                store, keys, client_factory=client_factory, fetcher=fetcher
            )
        except PipelineBusy:
            print(f"{stamp} {user}: a pull or rebuild is already running; skipped")
            continue
        except PlaidUnavailable as e:
            print(f"{stamp} {user}: Plaid unavailable: {e}")
            failed += 1
            continue
        for acct in result["accounts"]:
            who = f"{stamp} {user}/{acct['alias']}"
            if acct.get("needs_login"):
                failed += 1
                print(f"{who}: NEEDS LOGIN, fix it at {acct.get('login_url')}")
            elif "error" in acct:
                failed += 1
                hint = (
                    " (reconnect it in the app)" if acct.get("needs_reconnect") else ""
                )
                print(f"{who}: FAILED {acct['error']}{hint}")
            elif "skipped" in acct:
                print(f"{who}: skipped, {acct['skipped']}")
            else:
                print(f"{who}: pulled {acct['pulled']}")
        if result["pipeline"]:
            print(
                f"{stamp} {user}: rebuilt, {result['pipeline']['count']} transactions ({result['pipeline']['seconds']}s)"
            )
    return 1 if failed else 0


def add_direct(settings: Settings, user: str = "", account: str = "") -> int:
    from .direct_pull import schema

    if user not in set(settings.users.values()) or not account:
        print(
            "usage: add-direct USER ACCOUNT   (USER is one of the app's users)",
            file=sys.stderr,
        )
        return 2
    institution = account.split("-", 1)[0]
    try:
        schema(institution)  # only institutions whose export layout the pipeline knows
    except Exception:
        print(f"no direct pull for {institution!r} yet", file=sys.stderr)
        return 2
    Stores(settings.data_root).get(user).add_direct_account(account, institution)
    print(f"{user}: {account} will be fetched by Refresh data")
    return 0


def quiet():
    """A cron log should hold the result lines and nothing else. The pipeline logs every step at INFO (including the
    whole rules dictionary) and pandas warns about deprecations: both are off here; warnings and errors still print."""
    logging.disable(logging.INFO)
    warnings.simplefilter("ignore", FutureWarning)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("command", choices=["pull", "add-direct"])
    ap.add_argument("args", nargs="*")
    ns = ap.parse_args(argv)
    quiet()
    settings = Settings.from_env()
    if ns.command == "add-direct":
        return add_direct(settings, *ns.args)
    return pull(settings, client_factory=make_client)


if __name__ == "__main__":
    sys.exit(main())
