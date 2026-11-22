import subprocess
import sys

import pyotp
import pytest
from fetcher import vault as v
from pykeepass import create_database

SEED = "JBSWY3DPEHPK3PXP"
PASSWORD = "hunter2-the-venmo-password"
MASTER = "correct horse battery staple"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "fetcher.kdbx"
    kp = create_database(str(path), password=MASTER)
    group = kp.root_group
    full = kp.add_entry(group, "Venmo", "someone@example.com", PASSWORD)
    # as KeePassXC stores it: the reserved `otp` attribute holding an otpauth:// URI
    full.otp = f"otpauth://totp/Venmo:someone@example.com?secret={SEED}&issuer=Venmo"
    plain = kp.add_entry(group, "Citi", "citiuser", "citipass")
    plain.set_custom_property(
        "TOTP Seed", "JBSW Y3DP EHPK 3PXP"
    )  # a spaced base32 seed, as some sites display it
    kp.add_entry(group, "NoOtp", "u", "p")
    kp.add_entry(group, "NoPassword", "u", "")
    kp.save()
    return str(path)


def test_it_reads_credentials_and_a_keepassxc_otp_attribute(db):
    vault = v.Vault(db, password=MASTER)
    creds = vault.credentials("Venmo")
    assert (creds.username, creds.password, creds.has_totp) == (
        "someone@example.com",
        PASSWORD,
        True,
    )
    assert vault.password("Venmo") == PASSWORD


def test_the_totp_code_is_the_current_code_for_the_seed(db):
    vault = v.Vault(db, password=MASTER)
    totp = v._Totp(SEED)
    before = totp.now()
    code = vault.totp_code("Venmo")
    after = totp.now()
    assert code in (before, after) and len(code) == 6 and code.isdigit()


def test_a_plain_base32_seed_property_works_too(db):
    totp = v._Totp(SEED)
    before = totp.now()
    code = v.Vault(db, password=MASTER).totp_code("Citi")
    assert code in (before, totp.now())


def test_missing_things_are_clear_errors(db):
    vault = v.Vault(db, password=MASTER)
    with pytest.raises(v.VaultError, match="no TOTP"):
        vault.totp_code("NoOtp")
    with pytest.raises(v.VaultError, match="no entry"):
        vault.credentials("Nope")
    with pytest.raises(v.VaultError, match="no password"):
        vault.password("NoPassword")
    assert vault.credentials("NoOtp").has_totp is False


def test_a_wrong_master_password_or_file_never_echoes_secrets(db, tmp_path):
    with pytest.raises(v.VaultError) as e:
        v.Vault(db, password="not the password")
    assert "not the password" not in str(e.value) and MASTER not in str(e.value)
    with pytest.raises(v.VaultError):
        v.Vault(str(tmp_path / "missing.kdbx"), password=MASTER)


def test_the_master_password_comes_from_a_file_before_the_environment(tmp_path):
    f = tmp_path / "master"
    f.write_text(MASTER + "\n")
    assert (
        v.master_password_from_env(
            {"FETCHER_VAULT_PASSWORD_FILE": str(f), "FETCHER_VAULT_PASSWORD": "other"}
        )
        == MASTER
    )
    assert (
        v.master_password_from_env({"FETCHER_VAULT_PASSWORD": "from-env"}) == "from-env"
    )
    with pytest.raises(v.VaultError, match="no master password"):
        v.master_password_from_env({})
    with pytest.raises(v.VaultError, match="cannot read"):
        v.master_password_from_env(
            {"FETCHER_VAULT_PASSWORD_FILE": str(tmp_path / "nope")}
        )


def test_describe_reports_what_an_entry_has_and_none_of_its_values(
    db, monkeypatch, tmp_path
):
    f = tmp_path / "master"
    f.write_text(MASTER)
    monkeypatch.setenv("FETCHER_VAULT_PASSWORD_FILE", str(f))
    text = v.describe(db, "Venmo")
    assert (
        "password present" in text
        and "TOTP present" in text
        and "username present" in text
    )
    for secret in (PASSWORD, SEED, MASTER, "someone@example.com"):
        assert secret not in text
    assert "TOTP missing" in v.describe(db, "NoOtp")


def test_the_cli_vault_check_prints_no_values_and_exit_codes_are_right(db, tmp_path):
    f = tmp_path / "master"
    f.write_text(MASTER)
    env = {
        "FETCHER_VAULT": db,
        "FETCHER_VAULT_PASSWORD_FILE": str(f),
        "PATH": "/usr/bin:/bin",
    }
    ok = subprocess.run(
        [sys.executable, "-m", "fetcher", "vault-check", "Venmo"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert (
        ok.returncode == 0
        and PASSWORD not in ok.stdout + ok.stderr
        and SEED not in ok.stdout + ok.stderr
    )
    bad = subprocess.run(
        [sys.executable, "-m", "fetcher", "vault-check", "Nope"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1 and "no entry" in bad.stderr
    usage = subprocess.run(
        [sys.executable, "-m", "fetcher"], env=env, capture_output=True, text=True
    )
    assert usage.returncode == 2 and "python -m fetcher" in usage.stderr


def test_short_real_world_seeds_are_accepted_and_uri_options_are_honoured():
    """16-character (80-bit) seeds are what many sites issue; pyotp 2.12's default 112-bit minimum would refuse them."""
    short = "JBSWY3DPEHPK3PXP"
    assert len(short) * 5 == 80
    plain = v.totp_from_uri(f"otpauth://totp/Venmo:me?secret={short}&issuer=Venmo")
    assert (
        plain.now() == v._Totp(short).now()
        and plain.interval == 30
        and plain.digits == 6
    )
    custom = v.totp_from_uri(
        f"otpauth://totp/Bank:me?secret={short}&digits=8&period=60&algorithm=SHA256"
    )
    assert custom.digits == 8 and custom.interval == 60 and len(custom.now()) == 8
    # a 160-bit seed (what RFC-conformant sites issue) works the same way
    long_seed = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
    assert (
        v.totp_from_uri(f"otpauth://totp/x?secret={long_seed}").now()
        == pyotp.TOTP(long_seed).now()
    )


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.com/?secret=JBSWY3DPEHPK3PXP",  # not otpauth
        "otpauth://hotp/x?secret=JBSWY3DPEHPK3PXP",  # counter-based, not time-based
        "otpauth://totp/x",  # no secret
        "otpauth://totp/x?secret=JBSWY3DPEHPK3PXP&algorithm=MD5",
        "otpauth://totp/x?secret=!!notbase32!!",
        "otpauth://totp/x?secret=ABC",  # far too short to be a real seed
    ],
)
def test_bad_otp_values_are_vault_errors_not_crashes(uri):
    with pytest.raises(v.VaultError):
        v.totp_from_uri(uri).now()
