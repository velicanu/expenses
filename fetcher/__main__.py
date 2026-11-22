"""python -m fetcher <command>

  probe URL SHOT            open a page once and report whether it is a normal form or a bot challenge (no login)
  check INSTITUTION [SHOT]  is the saved session still logged in?  exit 0 logged in, 10 login needed, 11 human check,
                            12 unknown
  login INSTITUTION [MIN]   the one-time login by hand (run through remote-login.sh, a virtual display + noVNC)
  serve                     the credentials page (web.py): LISTEN_HOST, PORT, TRUSTED_PROXIES, ALLOWED_EMAILS, PUBLIC_ORIGIN
  vault-check INSTITUTION   what bao holds for an institution (never any value)
  set-credentials INSTITUTION
                            prompt (hidden) for username, password, optional TOTP seed and a short-lived
                            `fetcher-writer` bao token, then store them in bao

Environment: FETCHER_PROFILES (default /profiles); BAO_ADDR, BAO_ROLE_ID, BAO_SECRET_ID (the fetcher's bao.env).
"""

import getpass
import os
import sys


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    profiles = os.environ.get("FETCHER_PROFILES", "/profiles")
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
    if cmd == "serve" and not args:
        from . import web

        web.serve()
        return 0
    if cmd == "vault-check" and len(args) == 1:
        from . import vault

        try:
            print(vault.Vault.from_env().describe(args[0]))
            return 0
        except vault.VaultError as e:
            print(f"vault: {e}", file=sys.stderr)
            return 1
    if cmd == "set-credentials" and len(args) == 1:
        from . import vault

        try:
            addr = os.environ.get("BAO_ADDR") or ""
            if not addr:
                raise vault.VaultError("BAO_ADDR is not set")
            ask = (
                getpass.getpass
            )  # nothing typed here is echoed or kept in shell history
            user = ask(f"{args[0]} username: ")
            password = ask(f"{args[0]} password: ")
            seed = ask("TOTP seed or otpauth:// URI (Enter for none): ")
            token = ask("fetcher-writer bao token: ")
            vault.set_credentials(addr, token, args[0], user, password, seed or None)
            print(
                f"stored credentials for {args[0]}"
                + (" and a TOTP key" if seed else "")
            )
            return 0
        except (vault.VaultError, EOFError, KeyboardInterrupt) as e:
            print(f"vault: {e or 'cancelled'}", file=sys.stderr)
            return 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
