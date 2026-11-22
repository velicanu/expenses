"""A dedicated KeePass vault for the fetcher (separate from any personal vault): usernames, passwords and TOTP seeds.

Read-only. Entries are found by title. A TOTP seed is read the way KeePassXC stores it: the `otp` attribute (an
otpauth:// URI), or failing that a plain base32 custom property named `TOTP Seed` / `totp`.

The vault file lives on tess outside the Syncthing folder; the master password comes from a file or the environment,
never from the command line. Nothing here logs or prints a secret: `describe` reports only what an entry has.
"""

import hashlib
import os
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import pyotp
from pykeepass import PyKeePass


class VaultError(Exception):
    pass


class _Totp(pyotp.TOTP):
    # pyotp 2.12 refuses seeds under 112 bits by default, but many real sites issue 16-character (80-bit) seeds, which
    # authenticator apps accept. The seed is whatever the site gave us; refusing it would only make the account unusable.
    min_secret_length_bits = 80


_DIGESTS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}


def totp_from_uri(uri: str) -> pyotp.TOTP:
    """An otpauth://totp/... URI (what KeePassXC stores in `otp`). pyotp's own parser builds the stricter class."""
    parts = urlparse(uri)
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    if (
        parts.scheme != "otpauth"
        or parts.netloc.lower() != "totp"
        or not query.get("secret")
    ):
        raise VaultError("the otp value is not an otpauth://totp URI with a secret")
    try:
        return _Totp(
            query["secret"].replace(" ", ""),
            digits=int(query.get("digits", 6)),
            interval=int(query.get("period", 30)),
            digest=_DIGESTS[query.get("algorithm", "SHA1").upper()],
        )
    except (KeyError, ValueError) as e:
        raise VaultError(f"the otp value is not usable ({type(e).__name__})") from None


@dataclass(frozen=True)
class Credentials:
    username: str | None
    password: str | None
    has_totp: bool


class Vault:
    def __init__(
        self, path: str, password: str | None = None, keyfile: str | None = None
    ):
        if password is None and keyfile is None:
            password = master_password_from_env()
        try:
            self._db = PyKeePass(path, password=password, keyfile=keyfile)
        except Exception as e:  # wrong password, missing file, not a keepass database
            raise VaultError(f"cannot open the vault: {type(e).__name__}") from None

    def _entry(self, title: str):
        entry = self._db.find_entries(title=title, first=True)
        if entry is None:
            raise VaultError(f"no entry titled {title!r}")
        return entry

    def credentials(self, title: str) -> Credentials:
        entry = self._entry(title)
        return Credentials(
            entry.username, entry.password, bool(self._totp_source(entry))
        )

    @staticmethod
    def _totp_source(entry):
        otp = entry.otp  # KeePassXC's otpauth:// URI
        if otp:
            return totp_from_uri(otp)
        for key in ("TOTP Seed", "totp", "TOTP"):
            seed = entry.get_custom_property(key)
            if seed:
                return _Totp(seed.replace(" ", ""))
        return None

    def totp_code(self, title: str) -> str:
        """The current 6-digit code. Short-lived, but still a secret: the caller types it into the page, nothing else."""
        source = self._totp_source(self._entry(title))
        if source is None:
            raise VaultError(f"entry {title!r} has no TOTP")
        return source.now()

    def password(self, title: str) -> str:
        entry = self._entry(title)
        if not entry.password:
            raise VaultError(f"entry {title!r} has no password")
        return entry.password


def master_password_from_env(env=None) -> str:
    """FETCHER_VAULT_PASSWORD_FILE (a file, mode 600 on tess) wins over FETCHER_VAULT_PASSWORD."""
    env = os.environ if env is None else env
    path = env.get("FETCHER_VAULT_PASSWORD_FILE")
    if path:
        try:
            return open(path).read().rstrip("\n")
        except OSError as e:
            raise VaultError(
                f"cannot read the master password file: {type(e).__name__}"
            ) from None
    if env.get("FETCHER_VAULT_PASSWORD"):
        return env["FETCHER_VAULT_PASSWORD"]
    raise VaultError("no master password: set FETCHER_VAULT_PASSWORD_FILE")


def describe(path: str, title: str) -> str:
    """What the vault holds for an entry, without any value: for checking the setup."""
    creds = Vault(path).credentials(title)
    return (
        f"entry {title!r}: username {'present' if creds.username else 'MISSING'}, "
        f"password {'present' if creds.password else 'MISSING'}, TOTP {'present' if creds.has_totp else 'missing'}"
    )
