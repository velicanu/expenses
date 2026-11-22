"""Just enough of OpenBao's HTTP API for the unit tests; records every request."""

import io
import json
import urllib.error

PASSWORD = "hunter2-the-venmo-password"
WRITER = "s.writer-token"
ADDR = "http://bao.test"


class FakeBao:
    """Just enough of OpenBao's HTTP API; records every request so tests can see what was sent and with which token."""

    def __init__(self):
        self.kv = {
            "venmo": {"username": "someone@example.com", "password": PASSWORD},
            "citi": {"username": "u"},
        }
        self.totp = {"venmo"}
        self.requests = []
        self.login_status = 200

    def __call__(self, req, timeout=None):
        path = req.full_url.removeprefix(ADDR)
        token = req.get_header("X-vault-token")
        body = json.loads(req.data) if req.data else None
        self.requests.append((req.get_method(), path, token, body))
        if path == "/v1/auth/approle/login":
            return self._reply(
                self.login_status, {"auth": {"client_token": "s.reader"}}
            )
        if token not in ("s.reader", WRITER):
            return self._reply(403, {"errors": ["permission denied"]})
        kind, _, rest = path.removeprefix("/v1/").partition("/")
        if kind == "kv":
            name = rest.removeprefix("data/fetcher/")
            if rest.startswith("metadata/"):
                name = rest.removeprefix("metadata/fetcher/")
                return (
                    self._reply(200, {"data": {"updated_time": "2026-11-22T17:03:00Z"}})
                    if name in self.kv
                    else self._reply(404, {})
                )
            if body is not None:  # a write needs the writer, as the real policies say
                if token != WRITER:
                    return self._reply(403, {})
                self.kv[name] = body["data"]
                return self._reply(200, {"data": {"version": 2}})
            return (
                self._reply(200, {"data": {"data": self.kv[name]}})
                if name in self.kv
                else self._reply(404, {})
            )
        if kind == "totp":
            what, _, name = rest.partition("/")
            if what == "keys" and body is not None:
                if token != WRITER:
                    return self._reply(403, {})
                if body.get("key", "x") == "ABC":
                    return self._reply(
                        400, {"errors": ["invalid key value: illegal base32 data"]}
                    )
                self.totp.add(name)
                return self._reply(204, None)
            if name not in self.totp:
                return self._reply(
                    404 if what == "keys" else 400, {"errors": ["unknown key"]}
                )
            if what == "keys":
                return self._reply(
                    200, {"data": {"period": 30}}
                )  # settings only, never the seed
            return self._reply(200, {"data": {"code": "166971"}})
        return self._reply(404, {})

    @staticmethod
    def _reply(status, payload):
        raw = b"" if payload is None else json.dumps(payload).encode()
        if status >= 400:
            raise urllib.error.HTTPError("u", status, "err", {}, io.BytesIO(raw))
        return _Resp(raw)


class _Resp:
    def __init__(self, raw):
        self._raw = raw

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
