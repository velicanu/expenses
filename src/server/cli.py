"""Command-line jobs, run inside the app's container:  docker exec expenses python -m server.cli pull

pull: Refresh data for every user with linked Plaid accounts (what the Refresh data button does), for the nightly
schedule. One line per account on stdout; exits 1 if any account failed, so a cron log shows it.
"""

import argparse
import logging
import sys
import time
import warnings

from .bao import PlaidKeys, PlaidUnavailable
from .plaid_pull import make_client, pull_all
from .settings import Settings
from .store import PipelineBusy, Stores


def pull(settings: Settings, client_factory=make_client) -> int:
    stores, keys = Stores(settings.data_root), PlaidKeys(settings.bao)
    failed = 0
    for user in sorted(set(settings.users.values())):
        store = stores.get(user)
        if not store.accounts():
            continue
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            result = pull_all(store, keys, client_factory=client_factory)
        except PipelineBusy:
            print(f"{stamp} {user}: a pull or rebuild is already running; skipped")
            continue
        except PlaidUnavailable as e:
            print(f"{stamp} {user}: Plaid unavailable: {e}")
            failed += 1
            continue
        for acct in result["accounts"]:
            if "error" in acct:
                failed += 1
                hint = (
                    " (reconnect it in the app)" if acct.get("needs_reconnect") else ""
                )
                print(f"{stamp} {user}/{acct['alias']}: FAILED {acct['error']}{hint}")
            else:
                print(f"{stamp} {user}/{acct['alias']}: pulled {acct['pulled']}")
        if result["pipeline"]:
            print(
                f"{stamp} {user}: rebuilt, {result['pipeline']['count']} transactions ({result['pipeline']['seconds']}s)"
            )
    return 1 if failed else 0


def quiet():
    """A cron log should hold the result lines and nothing else. The pipeline logs every step at INFO (including the
    whole rules dictionary) and pandas warns about deprecations: both are off here; warnings and errors still print."""
    logging.disable(logging.INFO)
    warnings.simplefilter("ignore", FutureWarning)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("command", choices=["pull"])
    ap.parse_args(argv)
    quiet()
    return pull(Settings.from_env(), client_factory=make_client)


if __name__ == "__main__":
    sys.exit(main())
