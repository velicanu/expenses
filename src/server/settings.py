"""Configuration, all from the environment (see iac/files/tess/expenses/compose.yaml in velicanu/server).

DATA_ROOT        directory holding one subdirectory per user (data/<user>/expenses.db, changes.db, ...)
USERS_FILE       JSON object: login email -> user name (the directory under DATA_ROOT)
TRUSTED_PROXIES  comma-separated addresses of the reverse proxy; X-Email is believed only from these
BAO_ADDR / BAO_ROLE_ID / BAO_SECRET_ID / BAO_KV_PATH   where the Plaid keys live (optional)
STATIC_DIR       the built web app, served at / (optional)
DEV_USER         local development only: skip the login and act as this user
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

# A user name is a directory name under DATA_ROOT: keep it boring so it can never be a path.
USER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


@dataclass(frozen=True)
class BaoSettings:
    addr: str
    role_id: str
    secret_id: str
    kv_path: str


@dataclass(frozen=True)
class Settings:
    data_root: Path
    users: dict
    trusted_proxies: frozenset
    dev_user: str | None = None
    bao: BaoSettings | None = None
    static_dir: Path | None = None
    max_upload_bytes: int = 25 * 1024 * 1024

    def __post_init__(self):
        for user in [*self.users.values(), *([self.dev_user] if self.dev_user else [])]:
            if not USER_RE.match(user):
                raise ValueError(f"invalid user name {user!r}: use a-z, 0-9, _ and -")
        if not self.users and not self.dev_user:
            raise ValueError("no users configured (USERS_FILE is empty)")

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        users = {}
        if env.get("USERS_FILE"):
            with open(env["USERS_FILE"]) as f:
                users = {k.strip().lower(): v for k, v in json.load(f).items()}
        bao = None
        if env.get("BAO_ADDR") and env.get("BAO_ROLE_ID") and env.get("BAO_SECRET_ID"):
            bao = BaoSettings(
                addr=env["BAO_ADDR"].rstrip("/"),
                role_id=env["BAO_ROLE_ID"],
                secret_id=env["BAO_SECRET_ID"],
                kv_path=env.get("BAO_KV_PATH", "kv/data/expenses/plaid"),
            )
        return cls(
            data_root=Path(env.get("DATA_ROOT", "data")).resolve(),
            users=users,
            trusted_proxies=frozenset(
                p.strip()
                for p in env.get("TRUSTED_PROXIES", "").split(",")
                if p.strip()
            ),
            dev_user=env.get("DEV_USER") or None,
            bao=bao,
            static_dir=Path(env["STATIC_DIR"]) if env.get("STATIC_DIR") else None,
        )
