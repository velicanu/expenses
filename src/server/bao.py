"""Plaid keys from OpenBao: AppRole login, then one kv read. Stdlib only, short timeouts.

Failure is not fatal: the rest of the app works without Plaid. Callers get PlaidUnavailable.
"""

import json
import threading
import time
import urllib.error
import urllib.request

from .settings import BaoSettings

CACHE_SECONDS = 900


class PlaidUnavailable(Exception):
    pass


class PlaidKeys:
    def __init__(self, bao: BaoSettings | None, opener=urllib.request.urlopen):
        self._bao = bao
        self._open = opener
        self._lock = threading.Lock()
        self._cached = None  # (fetched_at, {"client_id": ..., "secret": ...})

    @property
    def configured(self) -> bool:
        return self._bao is not None

    def get(self) -> dict:
        if not self._bao:
            raise PlaidUnavailable("bao is not configured")
        with self._lock:
            if self._cached and time.monotonic() - self._cached[0] < CACHE_SECONDS:
                return self._cached[1]
            try:
                keys = self._fetch()
            except PlaidUnavailable:
                raise
            except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
                # the reason, never the response body (it could echo a token)
                raise PlaidUnavailable(
                    f"cannot read the Plaid keys from bao ({type(e).__name__})"
                ) from e
            self._cached = (time.monotonic(), keys)
            return keys

    def _call(self, path, body=None, token=None):
        req = urllib.request.Request(
            self._bao.addr + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                **({"X-Vault-Token": token} if token else {}),
            },
        )
        with self._open(req, timeout=5) as r:
            return json.load(r)

    def _fetch(self) -> dict:
        login = self._call(
            "/v1/auth/approle/login",
            {"role_id": self._bao.role_id, "secret_id": self._bao.secret_id},
        )
        token = login["auth"]["client_token"]
        data = self._call("/v1/" + self._bao.kv_path, token=token)["data"]["data"]
        keys = {"client_id": data["client_id"], "secret": data["secret"]}
        if not keys["client_id"] or not keys["secret"]:
            raise PlaidUnavailable("the Plaid keys in bao are empty")
        return keys
