"""python -m fetcher <command>

  probe URL SHOT            open a page once and report whether it is a normal form or a bot challenge (no login)
  check INSTITUTION [SHOT]  is the saved session still logged in?  exit 0 logged in, 10 login needed, 11 human check,
                            12 unknown
  login INSTITUTION [MIN]   the one-time login by hand (run through remote-login.sh, a virtual display + noVNC)
  vault-check TITLE         what the KeePass vault holds for an entry (no values)

Environment: FETCHER_PROFILES (default /profiles), FETCHER_VAULT (default /vault/fetcher.kdbx),
FETCHER_VAULT_PASSWORD_FILE.
"""

import os
import sys


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    profiles = os.environ.get("FETCHER_PROFILES", "/profiles")
    vault_path = os.environ.get("FETCHER_VAULT", "/vault/fetcher.kdbx")
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    if cmd == "probe" and len(args) == 2:
        from . import probe

        for k, v in probe.probe(args[0], args[1]).items():
            print(f"{k:12} {v}")
        return 0
    if cmd == "check" and args:
        from . import check

        return check.main(args[0], profiles, args[1] if len(args) > 1 else None)
    if cmd == "login" and args:
        from . import login

        return login.login(args[0], profiles, int(args[1]) if len(args) > 1 else 30)
    if cmd == "vault-check" and args:
        from . import vault

        try:
            print(vault.describe(vault_path, args[0]))
            return 0
        except vault.VaultError as e:
            print(f"vault: {e}", file=sys.stderr)
            return 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
