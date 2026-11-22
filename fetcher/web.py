"""The credentials page: a phone-friendly web UI, behind a Google login, for the fetcher's accounts.

nginx on pi5 runs the login (oauth2-proxy) and puts the verified address in X-Email, always overwriting whatever the
browser sent. This service listens on the LAN, so that header is believed only from TRUSTED_PROXIES (run uvicorn with
proxy_headers off), and only for ALLOWED_EMAILS.

Secrets go one way: the fields are written to bao and are never sent back; the page only learns "stored" and a date.
This process logs in with the write-only AppRole, so even a bug here cannot read a stored password or seed. Bodies are
never logged. Every write is audited (who, what, when; no values).
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import vault as vault_mod
from .accounts import ACCOUNTS

STATIC = Path(__file__).parent / "static"


@dataclass
class Settings:
    trusted_proxies: frozenset[str] = frozenset()
    allowed_emails: frozenset[str] = frozenset()
    public_origin: str = ""  # e.g. https://fetch.velicanu.com; POSTs must come from it
    audit_log: str | None = None
    dev_user: str | None = None  # tests and local runs only
    writes_per_minute: int = 20
    _writes: list = field(default_factory=list)

    @classmethod
    def from_env(cls, env=None) -> "Settings":
        env = os.environ if env is None else env

        def split(key):
            return frozenset(
                x.strip().lower() for x in env.get(key, "").split(",") if x.strip()
            )

        return cls(
            trusted_proxies=frozenset(
                x.strip()
                for x in env.get("TRUSTED_PROXIES", "").split(",")
                if x.strip()
            ),
            allowed_emails=split("ALLOWED_EMAILS"),
            public_origin=env.get("PUBLIC_ORIGIN", ""),
            audit_log=env.get("AUDIT_LOG"),
        )


class CredentialsIn(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)
    totp_seed: str | None = Field(default=None, max_length=512)


def create_app(settings: Settings, bao: "vault_mod.Vault") -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    audit_lock = threading.Lock()

    def audit(email: str, action: str, name: str, ok: bool) -> None:
        if not settings.audit_log:
            return
        line = json.dumps(
            {
                "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "who": email,
                "action": action,
                "account": name,
                "ok": ok,
            }
        )
        with audit_lock, open(settings.audit_log, "a") as f:
            f.write(line + "\n")

    def current_email(request: Request) -> str:
        if settings.dev_user:
            return settings.dev_user
        peer = request.client.host if request.client else None
        if peer not in settings.trusted_proxies:
            raise HTTPException(403, "not reachable except through the login proxy")
        email = request.headers.get("x-email", "").strip().lower()
        if not email:
            raise HTTPException(401, "not logged in")
        if email not in settings.allowed_emails:
            raise HTTPException(403, "this account may not use this page")
        return email

    def same_origin_json(request: Request) -> None:
        """CSRF: a write must be JSON (which a cross-site form cannot send) from this site's own origin."""
        if not request.headers.get("content-type", "").startswith("application/json"):
            raise HTTPException(415, "expected JSON")
        if request.headers.get("origin") != settings.public_origin:
            raise HTTPException(403, "wrong origin")

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        # FastAPI's default reply repeats the rejected input, which here would be a password
        fields = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
        return JSONResponse(
            {"error": "invalid fields: " + ", ".join(fields)}, status_code=422
        )

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def write_guard(
        name: str, request: Request, email: str = Depends(current_email)
    ) -> str:
        """Runs before the body is parsed: who, which account, and where the request came from."""
        if name not in ACCOUNTS:
            raise HTTPException(404, "unknown account")
        same_origin_json(request)
        return email

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def index(email: str = Depends(current_email)):
        return FileResponse(STATIC / "index.html")

    @app.get("/app.js")
    def script(email: str = Depends(current_email)):
        return FileResponse(STATIC / "app.js", media_type="text/javascript")

    @app.get("/api/accounts")
    def accounts(email: str = Depends(current_email)):
        out = []
        for name, label in ACCOUNTS.items():
            try:
                out.append({"name": name, "label": label, **bao.status(name)})
            except vault_mod.VaultError as e:
                out.append({"name": name, "label": label, "error": str(e)})
        return {"email": email, "accounts": out}

    @app.post("/api/accounts/{name}/credentials")
    def save(
        name: str,
        body: CredentialsIn,
        email: str = Depends(write_guard),
    ):
        now = time.time()
        settings._writes[:] = [t for t in settings._writes if now - t < 60]
        if len(settings._writes) >= settings.writes_per_minute:
            raise HTTPException(429, "slow down")
        settings._writes.append(now)
        try:
            bao.store(name, body.username, body.password, body.totp_seed)
        except vault_mod.VaultError as e:
            audit(email, "save-credentials", name, False)
            return JSONResponse({"error": str(e)}, status_code=502)
        audit(email, "save-credentials", name, True)
        return {"ok": True, **bao.status(name)}

    return app


def serve() -> None:
    import uvicorn

    settings = Settings.from_env()
    if (
        not settings.trusted_proxies
        or not settings.allowed_emails
        or not settings.public_origin
    ):
        raise SystemExit("set TRUSTED_PROXIES, ALLOWED_EMAILS and PUBLIC_ORIGIN")
    app = create_app(settings, vault_mod.Vault.from_env())
    uvicorn.run(
        app,
        host=os.environ.get("LISTEN_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8095")),
        proxy_headers=False,  # request.client must stay the TCP peer: X-Forwarded-For is client-controlled
        access_log=False,
    )
