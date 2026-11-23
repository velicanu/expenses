"""The fetcher's credentials, in OpenBao: a username and password per institution (kv) and its TOTP seed (the totp
secrets engine). Stdlib only, short timeouts, AppRole login like the expense app.

    kv/fetcher/<institution>     username, password
    totp/keys/<institution>      the TOTP seed; the engine hands out the current code and never the seed

The fetcher's role can read the kv entry and ask for a code; it cannot read a seed back. Writing is a separate policy
(`fetcher-writer`) used by `set_credentials`, with a short-lived token a person supplies. Nothing here logs or prints a
secret: errors carry an HTTP status or an exception type, never a response body.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

KV = "kv"
TOTP = "totp"
_NAME = re.compile(r"^[a-z][a-z0-9-]{1,30}$")


class VaultError(Exception):
    pass


@dataclass(frozen=True)
class Credentials:
    username: str | None
    password: str | None
    has_totp: bool


def _check_name(name: str) -> str:
    if not _NAME.match(name or ""):
        raise VaultError(
            f"{name!r} is not an institution name (lowercase letters, digits, dashes)"
        )
    return name


class Vault:
    def __init__(
        self,
        addr: str,
        role_id: str,
        secret_id: str,
        opener=urllib.request.urlopen,
        token: str | None = None,
        clock=time.monotonic,
    ):
        self._addr = addr.rstrip("/")
        self._login_with = {"role_id": role_id, "secret_id": secret_id}
        self._open = opener
        self._token = token  # a ready-made token (the CLI's); otherwise the AppRole login makes one
        self._token_until: float | None = (
            None  # when to log in again; None for a ready-made token, which is not ours to renew
        )
        self._clock = clock

    @classmethod
    def from_env(cls, env=None, opener=urllib.request.urlopen) -> "Vault":
        env = os.environ if env is None else env
        try:
            return cls(
                env["BAO_ADDR"], env["BAO_ROLE_ID"], env["BAO_SECRET_ID"], opener
            )
        except KeyError as e:
            raise VaultError(
                f"{e.args[0]} is not set (the fetcher's bao.env)"
            ) from None

    def _call(
        self, path: str, body=None, token: str | None = None, method: str | None = None
    ):
        req = urllib.request.Request(
            self._addr + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "Content-Type": "application/json",
                **({"X-Vault-Token": token} if token else {}),
            },
        )
        try:
            with self._open(req, timeout=5) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise _Http(e.code) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise VaultError(f"cannot reach bao ({type(e).__name__})") from None

    def _auth(self) -> str:
        """A live token. An AppRole token only lasts its lease (15 minutes here); a long-running service (the credentials
        page) must log in again before then, or every call after that is refused with HTTP 403."""
        if self._token is None or (
            self._token_until is not None and self._clock() >= self._token_until
        ):
            try:
                auth = self._call("/v1/auth/approle/login", self._login_with)["auth"]
                token = auth["client_token"]
            except _Http as e:
                self._token = None
                raise VaultError(
                    f"bao refused the fetcher's login (HTTP {e.status})"
                ) from None
            except KeyError:
                self._token = None
                raise VaultError("bao's login reply had no token") from None
            self._token = token
            # renew at three quarters of the lease; a reply without one is treated as short
            self._token_until = self._clock() + 0.75 * (
                auth.get("lease_duration") or 300
            )
        return self._token

    def _kv(self, name: str) -> dict:
        try:
            return self._call(
                f"/v1/{KV}/data/fetcher/{_check_name(name)}", token=self._auth()
            )["data"]["data"]
        except _Http as e:
            if e.status == 404:
                raise VaultError(f"no entry for {name!r}") from None
            raise VaultError(
                f"cannot read {name!r} from bao (HTTP {e.status})"
            ) from None

    def _has_totp(self, name: str) -> bool:
        try:
            self._call(f"/v1/{TOTP}/keys/{_check_name(name)}", token=self._auth())
            return True
        except _Http as e:
            if e.status == 404:
                return False
            raise VaultError(
                f"cannot check the TOTP key for {name!r} (HTTP {e.status})"
            ) from None

    def credentials(self, name: str) -> Credentials:
        data = self._kv(name)
        return Credentials(
            data.get("username"), data.get("password"), self._has_totp(name)
        )

    def password(self, name: str) -> str:
        password = self._kv(name).get("password")
        if not password:
            raise VaultError(f"entry {name!r} has no password")
        return password

    def totp_code(self, name: str) -> str:
        """The current code, from the engine: the seed never leaves bao. Short-lived, but still a secret."""
        try:
            return self._call(
                f"/v1/{TOTP}/code/{_check_name(name)}", token=self._auth()
            )["data"]["code"]
        except _Http as e:
            if e.status in (400, 404):
                raise VaultError(f"entry {name!r} has no TOTP") from None
            raise VaultError(
                f"cannot get a TOTP code for {name!r} (HTTP {e.status})"
            ) from None

    def registry(self) -> list | None:
        """The list of accounts (kv/fetcher-meta/accounts): not secret, so the page and the nightly job both read it."""
        try:
            return self._call(
                f"/v1/{KV}/data/fetcher-meta/accounts", token=self._auth()
            )["data"]["data"].get("accounts")
        except _Http as e:
            if e.status == 404:
                return None
            raise VaultError(
                f"cannot read the account list (HTTP {e.status})"
            ) from None

    def save_registry(self, accounts: list) -> None:
        try:
            self._call(
                f"/v1/{KV}/data/fetcher-meta/accounts",
                {"data": {"accounts": accounts}},
                token=self._auth(),
            )
        except _Http as e:
            raise VaultError(
                f"cannot save the account list (HTTP {e.status})"
            ) from None

    def status(self, name: str) -> dict:
        """What is stored, as booleans and a date, never a value. Works with the write-only role: it reads the kv entry's
        metadata (versions and times), not its data, and a TOTP key's settings, which hold no seed."""
        try:
            meta = self._call(
                f"/v1/{KV}/metadata/fetcher/{_check_name(name)}", token=self._auth()
            )["data"]
            stored, saved = True, meta.get("updated_time")
        except _Http as e:
            if e.status != 404:
                raise VaultError(
                    f"cannot read the status of {name!r} (HTTP {e.status})"
                ) from None
            stored, saved = False, None
        return {"stored": stored, "saved_at": saved, "totp": self._has_totp(name)}

    def store(
        self, name: str, username: str, password: str, totp_seed: str | None = None
    ) -> None:
        """Write (replace) an institution's credentials. A TOTP seed may be a base32 secret or an otpauth:// URI. The kv
        entry is replaced as a whole, so username and password go together."""
        name = _check_name(name)
        if not username or not password:
            raise VaultError("a username and a password are both needed")
        try:
            token = self._auth()
            self._call(
                f"/v1/{KV}/data/fetcher/{name}",
                {"data": {"username": username, "password": password}},
                token=token,
            )
            if totp_seed and totp_seed.strip():
                seed = totp_seed.strip()
                body = (
                    {"url": seed}
                    if seed.startswith("otpauth://")
                    else {"key": seed.replace(" ", ""), "issuer": name}
                )
                self._call(f"/v1/{TOTP}/keys/{name}", body, token=token)
        except _Http as e:
            raise VaultError(
                f"bao refused the write (HTTP {e.status}); a bad TOTP seed is HTTP 400"
            ) from None

    def describe(self, name: str) -> str:
        """What bao holds for an institution, without any value: for checking the setup."""
        c = self.credentials(name)
        return (
            f"{name}: username {'present' if c.username else 'MISSING'}, "
            f"password {'present' if c.password else 'MISSING'}, TOTP {'present' if c.has_totp else 'missing'}"
        )


class _Http(Exception):
    def __init__(self, status: int):
        self.status = status


def set_credentials(
    addr: str,
    token: str,
    name: str,
    username: str,
    password: str,
    totp_seed: str | None = None,
    opener=urllib.request.urlopen,
) -> None:
    """The CLI's break-glass path: write with a short-lived `fetcher-writer` token a person supplies."""
    Vault(addr, "", "", opener, token=token).store(name, username, password, totp_seed)
