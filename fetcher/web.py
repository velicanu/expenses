"""The credentials page: a phone-friendly web UI, behind a Google login, for the fetcher's accounts.

nginx on pi5 runs the login (oauth2-proxy) and puts the verified address in X-Email, always overwriting whatever the
browser sent. This service listens on the LAN, so that header is believed only from TRUSTED_PROXIES (run uvicorn with
proxy_headers off), and only for ALLOWED_EMAILS.

Secrets go one way: the fields are written to bao and are never sent back; the page only learns "stored" and a date.
This process logs in with the write-only AppRole, so even a bug here cannot read a stored password or seed. Bodies are
never logged. Every write is audited (who, what, when; no values).
"""

import asyncio
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from . import accounts as acct
from . import institutions
from . import vault as vault_mod

STATIC = Path(__file__).parent / "static"


@dataclass
class Settings:
    trusted_proxies: frozenset[str] = frozenset()
    allowed_emails: frozenset[str] = frozenset()
    public_origin: str = ""  # e.g. https://fetch.velicanu.com; POSTs must come from it
    audit_log: str | None = None
    browserd_url: str = "http://127.0.0.1:8097"
    browserd_token: str = ""
    vnc_host: str = "127.0.0.1"
    vnc_port: int = 5900
    novnc_dir: str = "/usr/share/novnc"
    expense_url: str = ""  # where Done sends the person to fetch the account they just logged in to (the expense app)
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
            browserd_url=env.get("BROWSERD_URL", "http://127.0.0.1:8097"),
            browserd_token=env.get("BROWSERD_TOKEN", ""),
            expense_url=env.get("EXPENSE_URL", "").rstrip("/"),
        )


class CredentialsIn(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)
    totp_seed: str | None = Field(default=None, max_length=512)


class BrowserdError(Exception):
    pass


class Browserd:
    """The browser container's control API (browserd.py) on 127.0.0.1, with the shared token. It reports its own refusals
    in words (one session at a time, no flow for that bank); everything else is reduced to a status code."""

    def __init__(self, url: str, token: str, opener=urllib.request.urlopen):
        self._url, self._token, self._open = url.rstrip("/"), token, opener

    def _call(self, method: str, path: str, body=None) -> dict:
        req = urllib.request.Request(
            self._url + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._open(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                try:
                    raise BrowserdError(json.load(e)["detail"]) from None
                except (ValueError, KeyError, TypeError):
                    pass
            raise BrowserdError(
                f"the browser service refused (HTTP {e.code})"
            ) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise BrowserdError(
                f"cannot reach the browser service ({type(e).__name__})"
            ) from None

    def status(self) -> dict:
        return self._call("GET", "/status")

    def start(self, account: str) -> dict:
        return self._call("POST", "/start", {"account": account})

    def stop(self) -> dict:
        return self._call("POST", "/stop", {})


def create_app(
    settings: Settings,
    bao: "vault_mod.Vault",
    browser: "Browserd | None" = None,
    open_vnc=asyncio.open_connection,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    browser = browser or Browserd(settings.browserd_url, settings.browserd_token)
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

    def same_origin(request: Request) -> None:
        """CSRF: a write must come from this site's own origin (browsers always send Origin on a write)."""
        if request.headers.get("origin") != settings.public_origin:
            raise HTTPException(403, "wrong origin")

    def same_origin_json(request: Request) -> None:
        """...and a body must be JSON, which a cross-site form cannot send."""
        if not request.headers.get("content-type", "").startswith("application/json"):
            raise HTTPException(415, "expected JSON")
        same_origin(request)

    registry_lock = threading.Lock()

    def accounts_list() -> list[dict]:
        """The account list from bao, saved there on first use from the defaults (the existing data files' accounts)."""
        stored = bao.registry()
        if stored is None:
            stored = acct.defaults()
            bao.save_registry(stored)
        return acct.clean(stored)

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
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
            "img-src 'self' data: blob:; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def write_guard(
        name: str, request: Request, email: str = Depends(current_email)
    ) -> str:
        """Runs before the body is parsed: who, which account, and where the request came from."""
        same_origin_json(request)
        try:
            if name not in {a["key"] for a in accounts_list()}:
                raise HTTPException(404, "unknown account")
        except vault_mod.VaultError:
            raise HTTPException(502, "cannot read the account list") from None
        return email

    def origin_guard(request: Request, email: str = Depends(current_email)) -> str:
        same_origin(request)
        return email

    def json_guard(request: Request, email: str = Depends(current_email)) -> str:
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
        try:
            listed = accounts_list()
        except vault_mod.VaultError as e:
            return JSONResponse({"error": str(e)}, status_code=502)
        for a in listed:
            try:
                out.append(
                    {
                        **a,
                        **bao.status(a["key"]),
                        "login": institutions.find(a["key"]) is not None,
                    }
                )
            except vault_mod.VaultError as e:
                out.append({**a, "error": str(e), "login": False})
        return {
            "email": email,
            "institutions": [
                {"id": k, "label": v} for k, v in acct.INSTITUTIONS.items()
            ],
            "accounts": out,
        }

    class AccountIn(BaseModel):
        institution: str = Field(min_length=1, max_length=32)
        owner: str = Field(default="", max_length=32)

    @app.post("/api/accounts")
    def add_account(body: AccountIn, email: str = Depends(json_guard)):
        try:
            new = acct.entry(body.institution, body.owner)
        except acct.AccountError as e:
            return JSONResponse({"error": str(e)}, status_code=422)
        with registry_lock:
            try:
                current = accounts_list()
                if new["key"] in {a["key"] for a in current}:
                    return JSONResponse(
                        {"error": f"{new['label']} is already listed"}, status_code=409
                    )
                bao.save_registry(current + [new])
            except vault_mod.VaultError as e:
                audit(email, "add-account", new["key"], False)
                return JSONResponse({"error": str(e)}, status_code=502)
        audit(email, "add-account", new["key"], True)
        return {"ok": True, "account": new}

    @app.delete("/api/accounts/{name}")
    def remove_account(name: str, email: str = Depends(origin_guard)):
        """Takes the account off the list. Stored credentials stay in bao (this role cannot delete them) and are
        used again if the account is re-added."""
        with registry_lock:
            try:
                current = accounts_list()
                if name not in {a["key"] for a in current}:
                    raise HTTPException(404, "unknown account")
                bao.save_registry([a for a in current if a["key"] != name])
            except vault_mod.VaultError as e:
                audit(email, "remove-account", name, False)
                return JSONResponse({"error": str(e)}, status_code=502)
        audit(email, "remove-account", name, True)
        return {"ok": True}

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

    # --- hand login: the remote browser, seen through noVNC -------------------------------------------------------

    login_writes: list[float] = []

    def browser_call(fn, *args):
        try:
            return fn(*args)
        except BrowserdError as e:
            raise HTTPException(502, str(e)) from None

    @app.get("/login")
    def login_page(email: str = Depends(current_email)):
        return FileResponse(STATIC / "login.html")

    @app.get("/login.js")
    def login_script(email: str = Depends(current_email)):
        return FileResponse(STATIC / "login.js", media_type="text/javascript")

    @app.get("/novnc/{path:path}")
    def novnc(path: str, email: str = Depends(current_email)):
        """The noVNC client, from the image. Resolved inside its directory only."""
        root = Path(settings.novnc_dir).resolve()
        target = (root / path).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(404, "not found")
        return FileResponse(target)

    def public_status(st: dict) -> dict:
        # the VNC password has its own route; expense_url is the site Done sends the person to (our own setting)
        return {
            **{k: v for k, v in st.items() if k != "vnc_password"},
            "expense_url": settings.expense_url,
            # the institutions Refresh data can fetch from: Done only goes to the expense app for these
            "fetch_institutions": sorted(
                n for n, i in institutions.INSTITUTIONS.items() if i.download
            ),
        }

    @app.get("/api/login")
    def login_status(email: str = Depends(current_email)):
        return public_status(browser_call(browser.status))

    @app.get("/api/login/session")
    def login_session(email: str = Depends(current_email)):
        """The one-time VNC password for the running session; only the logged-in person gets it, and only while it runs."""
        st = browser_call(browser.status)
        if st.get("state") != "running" or not st.get("vnc_password"):
            raise HTTPException(404, "no login session is running")
        return {"password": st["vnc_password"], "account": st["account"]}

    @app.post("/api/login/stop")
    def login_stop(email: str = Depends(json_guard)):
        st = browser_call(browser.stop)
        audit(email, "login-stop", st.get("account") or "-", True)
        return public_status(st)

    @app.post("/api/login/{name}/start")
    def login_start(name: str, email: str = Depends(write_guard)):
        if institutions.find(name) is None:
            raise HTTPException(409, "there is no sign-in flow for this account yet")
        now = time.time()
        login_writes[:] = [t for t in login_writes if now - t < 60]
        if len(login_writes) >= 6:
            raise HTTPException(429, "slow down")
        login_writes.append(now)
        try:
            st = browser.start(name)
        except BrowserdError as e:
            audit(email, "login-start", name, False)
            return JSONResponse({"error": str(e)}, status_code=409)
        audit(email, "login-start", name, True)
        return public_status(st)

    def ws_email(ws: WebSocket) -> str | None:
        """Same trust as the HTTP routes, plus Origin: a page on another site could otherwise open this socket with the
        person's cookies (browsers send them) and take over the remote browser."""
        if ws.headers.get("origin") != settings.public_origin:
            return None
        if settings.dev_user:
            return settings.dev_user
        if (ws.client.host if ws.client else None) not in settings.trusted_proxies:
            return None
        email = ws.headers.get("x-email", "").strip().lower()
        return email if email in settings.allowed_emails else None

    bridge_open: list[bool] = [False]

    @app.websocket("/ws/vnc")
    async def vnc_bridge(ws: WebSocket):
        email = ws_email(ws)
        if email is None:
            await ws.close(
                code=1008
            )  # before accept: the handshake is refused (HTTP 403)
            return
        try:
            st = await asyncio.to_thread(browser.status)
        except BrowserdError:
            await ws.close(code=1011)
            return
        if st.get("state") != "running" or bridge_open[0]:
            await ws.close(code=1008)
            return
        try:
            reader, writer = await open_vnc(settings.vnc_host, settings.vnc_port)
        except OSError:
            await ws.close(code=1011)
            return
        bridge_open[0] = True
        offered = ws.scope.get("subprotocols", [])
        await ws.accept(subprotocol="binary" if "binary" in offered else None)

        async def to_vnc():
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    return
                data = msg.get("bytes") or (msg.get("text") or "").encode()
                if data:
                    writer.write(data)
                    await writer.drain()

        async def to_browser():
            while True:
                data = await reader.read(65536)
                if not data:
                    return
                await ws.send_bytes(data)

        tasks = [asyncio.ensure_future(to_vnc()), asyncio.ensure_future(to_browser())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            writer.close()
            bridge_open[0] = False
            # either side may be gone already (the phone navigated away, or Chrome was closed): that is the normal end of
            # a session, not an error, so nothing here may raise or leave a task's exception unretrieved
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await ws.close()
            except (RuntimeError, WebSocketDisconnect):
                pass

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
    if len(settings.browserd_token) < 24:
        raise SystemExit("set BROWSERD_TOKEN (the browser service's shared token)")
    app = create_app(settings, vault_mod.Vault.from_env())
    uvicorn.run(
        app,
        host=os.environ.get("LISTEN_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8095")),
        proxy_headers=False,  # request.client must stay the TCP peer: X-Forwarded-For is client-controlled
        access_log=False,
    )
