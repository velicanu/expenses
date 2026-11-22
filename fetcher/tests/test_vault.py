import io
import json
import os
import subprocess
import sys
import urllib.error

import pytest
from fetcher import vault as v

PASSWORD = "hunter2-the-venmo-password"
SEED = "JBSWY3DPEHPK3PXP"
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


@pytest.fixture
def bao():
    return FakeBao()


def make(bao):
    return v.Vault(ADDR, "role", "secret", bao)


def test_it_reads_credentials_and_whether_a_totp_key_exists(bao):
    vault = make(bao)
    creds = vault.credentials("venmo")
    assert (creds.username, creds.password, creds.has_totp) == (
        "someone@example.com",
        PASSWORD,
        True,
    )
    assert vault.password("venmo") == PASSWORD
    assert vault.credentials("citi").has_totp is False


def test_the_totp_code_comes_from_the_engine_and_the_seed_is_never_requested(bao):
    assert make(bao).totp_code("venmo") == "166971"
    paths = [p for _, p, _, _ in bao.requests]
    assert "/v1/totp/code/venmo" in paths
    assert not any("seed" in p for p in paths)


def test_it_logs_in_once_and_uses_the_token_it_got(bao):
    vault = make(bao)
    vault.credentials("venmo")
    vault.totp_code("venmo")
    assert sum(1 for _, p, _, _ in bao.requests if p.endswith("/login")) == 1
    assert all(
        t == "s.reader" for _, p, t, _ in bao.requests if not p.endswith("/login")
    )


def test_missing_things_are_clear_errors(bao):
    vault = make(bao)
    with pytest.raises(v.VaultError, match="no entry"):
        vault.credentials("nope")
    with pytest.raises(v.VaultError, match="no TOTP"):
        vault.totp_code("citi")
    with pytest.raises(v.VaultError, match="no password"):
        vault.password("citi")


def test_a_refused_login_or_unreachable_bao_never_echoes_secrets(bao):
    bao.login_status = 403
    with pytest.raises(v.VaultError) as e:
        make(bao).credentials("venmo")
    assert (
        "HTTP 403" in str(e.value)
        and "secret" not in str(e.value)
        and "role" not in str(e.value)
    )

    def down(req, timeout=None):
        raise urllib.error.URLError("connection refused for secret")

    with pytest.raises(v.VaultError) as e:
        v.Vault(ADDR, "role", "secret", down).credentials("venmo")
    assert "URLError" in str(e.value) and "secret" not in str(e.value)


@pytest.mark.parametrize("name", ["../x", "Venmo", "a/b", "", "x" * 40, "-a", "a b"])
def test_institution_names_cannot_reach_other_paths(bao, name):
    with pytest.raises(v.VaultError, match="not an institution name"):
        make(bao).credentials(name)
    assert bao.requests == []


def test_describe_reports_what_there_is_and_none_of_its_values(bao):
    text = make(bao).describe("venmo")
    assert (
        "username present" in text
        and "password present" in text
        and "TOTP present" in text
    )
    for secret in (PASSWORD, SEED, "someone@example.com", "166971"):
        assert secret not in text
    assert "password MISSING" in make(bao).describe("citi") and "TOTP missing" in make(
        bao
    ).describe("citi")


def test_from_env_names_the_missing_variable():
    with pytest.raises(v.VaultError, match="BAO_ROLE_ID"):
        v.Vault.from_env({"BAO_ADDR": ADDR})
    assert v.Vault.from_env(
        {"BAO_ADDR": ADDR, "BAO_ROLE_ID": "r", "BAO_SECRET_ID": "s"}
    )


def test_set_credentials_writes_with_the_writer_token_and_a_bare_seed(bao):
    v.set_credentials(
        ADDR, WRITER, "wealthfront", "me", "pw", "JBSW Y3DP EHPK 3PXP", opener=bao
    )
    assert bao.kv["wealthfront"] == {"username": "me", "password": "pw"}
    (_, _, token, body) = [
        r for r in bao.requests if r[1] == "/v1/totp/keys/wealthfront"
    ][0]
    assert token == WRITER and body == {
        "key": "JBSWY3DPEHPK3PXP",
        "issuer": "wealthfront",
    }
    assert make(bao).credentials("wealthfront").has_totp is True


def test_set_credentials_takes_an_otpauth_uri_and_makes_the_seed_optional(bao):
    uri = f"otpauth://totp/Citi:me?secret={SEED}&issuer=Citi"
    v.set_credentials(ADDR, WRITER, "citi2", "me", "pw", uri, opener=bao)
    assert [r[3] for r in bao.requests if r[1] == "/v1/totp/keys/citi2"] == [
        {"url": uri}
    ]
    v.set_credentials(ADDR, WRITER, "fidelity", "me", "pw", None, opener=bao)
    assert not any(r[1] == "/v1/totp/keys/fidelity" for r in bao.requests)


def test_set_credentials_failures_never_echo_what_was_typed(bao):
    with pytest.raises(v.VaultError) as e:
        v.set_credentials(ADDR, WRITER, "x1", "me", "pw", "ABC", opener=bao)
    assert (
        "HTTP 400" in str(e.value)
        and "ABC" not in str(e.value)
        and "pw" not in str(e.value)
    )
    with pytest.raises(v.VaultError, match="HTTP 403"):
        v.set_credentials(ADDR, "s.reader", "x1", "me", "pw", None, opener=bao)
    with pytest.raises(v.VaultError, match="both needed"):
        v.set_credentials(ADDR, WRITER, "x1", "", "pw", None, opener=bao)


def test_the_cli_usage_and_missing_configuration_exit_codes(tmp_path):
    env = {"PATH": "/usr/bin:/bin"}

    def run(*a):
        return subprocess.run(
            [sys.executable, "-m", "fetcher", *a],
            env=env,
            capture_output=True,
            text=True,
        )

    assert run().returncode == 2
    bad = run("vault-check", "venmo")
    assert bad.returncode == 1 and "BAO_ADDR" in bad.stderr


@pytest.mark.skipif(
    not os.environ.get("BAO_TEST_ADDR"),
    reason="needs a real (dev-mode) OpenBao: BAO_TEST_ADDR/BAO_TEST_TOKEN",
)
def test_against_a_real_openbao():
    """Run by hand against `bao server -dev` with the kv and totp engines and the fetcher policies; see docs/deploy.md."""
    addr, root = os.environ["BAO_TEST_ADDR"], os.environ["BAO_TEST_TOKEN"]
    v.set_credentials(addr, root, "realtest", "me", PASSWORD, SEED)
    # the reader role is set up by the harness script; here the root token stands in only for the write side
    reader = v.Vault(
        addr, os.environ["BAO_TEST_ROLE_ID"], os.environ["BAO_TEST_SECRET_ID"]
    )
    assert (
        reader.describe("realtest")
        == "realtest: username present, password present, TOTP present"
    )
    code = reader.totp_code("realtest")
    assert len(code) == 6 and code.isdigit()
    # the policies, not the code, are what keep secrets one-way: the reader cannot write, the writer cannot read
    writer = v.Vault(addr, "", "")
    for method_path, body, token, what in [
        (
            "/v1/totp/keys/realtest",
            {"key": SEED},
            reader._auth(),
            "reader writing a TOTP key",
        ),
        (
            "/v1/kv/data/fetcher/realtest",
            {"data": {"password": "x"}},
            reader._auth(),
            "reader writing kv",
        ),
        ("/v1/kv/data/fetcher/realtest", None, root, "writer reading kv"),
    ]:
        with pytest.raises(v._Http) as e:
            writer._call(method_path, body, token=token)
        assert e.value.status == 403, what
    # a seed can never be read back: the key's settings carry no secret
    settings = reader._call("/v1/totp/keys/realtest", token=reader._auth())
    assert SEED not in json.dumps(settings)
    # what a missing key looks like (the statuses the code relies on)
    for path in ("/v1/totp/keys/nobody", "/v1/totp/code/nobody"):
        with pytest.raises(v._Http) as e:
            reader._call(path, token=reader._auth())
        assert e.value.status in (400, 404), path
    with pytest.raises(v.VaultError, match="no TOTP"):
        reader.totp_code("nobody")
    with pytest.raises(v.VaultError, match="no entry"):
        reader.credentials("nobody")
    assert reader.describe("realtest").endswith("TOTP present")
