"""The API. Run: uvicorn server.app:create_app --factory --no-proxy-headers   (see the Dockerfile)

Every /api route needs a logged-in user (auth.current_user) and only ever touches that user's directory.
"""

import datetime as dt
import logging
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import figures, plaid_link, queries, sqlview
from .auth import User, current_user
from .bao import PlaidKeys, PlaidUnavailable
from .direct_pull import FetcherClient
from .palette import COLORS
from .plaid_pull import make_client, pull_all
from .settings import Settings
from .store import NoData, PipelineBusy, Stores, UserStore

log = logging.getLogger("expenses")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


# --- request bodies ----------------------------------------------------------------------------------


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = Field(None, min_length=1, max_length=500)
    amount: float | None = Field(None, allow_inf_nan=False)
    date: dt.date | None = None


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: dt.date
    description: str = Field(min_length=1, max_length=500)
    amount: float = Field(allow_inf_nan=False)
    category: str = Field(min_length=1, max_length=64)

    @field_validator("amount")
    @classmethod
    def not_zero(cls, v):
        if v == 0:
            raise ValueError("amount is 0")  # 0 is how a transaction is deleted
        return v


class Rules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: dict[str, str] = {}
    category: dict[str, str] = {}
    new_categories: dict[str, str] = {}

    @field_validator("description", "category", "new_categories")
    @classmethod
    def sane(cls, v):
        for key, value in v.items():
            if not 1 <= len(key) <= 200 or not 1 <= len(value) <= 64:
                raise ValueError("rule or category name has a bad length")
        return v

    @field_validator("new_categories")
    @classmethod
    def colors(cls, v):
        for name, color in v.items():
            if not HEX_COLOR.match(color):
                raise ValueError(f"{name}: color must look like #1a2b3c")
        return v


class StateUpdate(BaseModel):
    """The sidebar's saved state: any subset of these."""

    model_config = ConfigDict(extra="forbid")
    min_date: dt.date | None = None
    max_date: dt.date | None = None
    categories_in: list[str] | None = Field(None, max_length=200)
    categories_not_in: list[str] | None = Field(None, max_length=200)
    show_sql: bool | None = None
    rules_button: bool | None = None

    @field_validator("categories_in", "categories_not_in")
    @classmethod
    def names(cls, v):
        if v is not None and any(not 1 <= len(c) <= 64 for c in v):
            raise ValueError("category name has a bad length")
        return v


class DefaultQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: dt.date | None = None
    end: dt.date | None = None
    category_in: list[str] = Field([], max_length=200)
    category_not_in: list[str] = Field([], max_length=200)
    description: str = Field("", max_length=200)
    sources: list[str] = Field([], max_length=200)


class SqlRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(max_length=5000)


class FiguresRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(max_length=5000)
    group: Literal["auto", "year", "month", "week", "day"] = "auto"


class LinkTokenRequest(BaseModel):
    """No alias: link a new bank. An alias of a linked account: reconnect it (Plaid's update mode)."""

    model_config = ConfigDict(extra="forbid")
    # any existing alias can be reconnected (older configs may hold one the stricter new-link rule would refuse)
    alias: str | None = Field(None, min_length=1, max_length=64)


class ExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    public_token: str = Field(min_length=10, max_length=200)
    alias: str = Field(pattern=plaid_link.ALIAS_RE.pattern)
    start_date: dt.date | None = None


class PipelineRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules_only: bool = False


# --- app ---------------------------------------------------------------------------------------------


def create_app(
    settings: Settings | None = None, plaid_client_factory=make_client
) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="expenses",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.plaid_client_factory = plaid_client_factory
    app.state.stores = Stores(settings.data_root)
    app.state.plaid = PlaidKeys(settings.bao)
    app.state.fetcher = (
        FetcherClient(
            settings.fetcher.url, settings.fetcher.token, settings.fetcher.login_url
        )
        if settings.fetcher
        else None
    )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # State changes only from this site: the login cookie is SameSite=Lax, and this checks again.
        if request.method in UNSAFE:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse(
                    {"detail": "cross-site request refused"}, status_code=403
                )
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://cdn.plaid.com; frame-src https://cdn.plaid.com; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'",
        )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        elif request.url.path.startswith("/assets/"):
            # Vite names these by content hash, so they never change under the same name
            response.headers.setdefault(
                "Cache-Control", "public, max-age=31536000, immutable"
            )
        return response

    def store_for(request: Request, user: User = Depends(current_user)) -> UserStore:
        return request.app.state.stores.get(user.name)

    @app.exception_handler(NoData)
    async def _no_data(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(PipelineBusy)
    async def _busy(request, exc):
        return JSONResponse(
            {"detail": "the pipeline is already running"}, status_code=409
        )

    @app.exception_handler(PlaidUnavailable)
    async def _plaid(request, exc):
        return JSONResponse({"detail": f"Plaid is unavailable: {exc}"}, status_code=503)

    @app.exception_handler(plaid_link.PlaidError)
    async def _plaid_api(request, exc):
        return JSONResponse(
            {"detail": f"Plaid: {exc}", "code": exc.code}, status_code=502
        )

    @app.exception_handler(ValueError)
    async def _bad_value(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    def filters(
        start: dt.date | None = None,
        end: dt.date | None = None,
        category_in: list[str] = Query([]),
        category_not_in: list[str] = Query([]),
        source: list[str] = Query([]),
        q: str = Query("", max_length=200),
    ) -> queries.Filters:
        return queries.Filters(start, end, category_in, category_not_in, source, q)

    # --- who and what ----------------------------------------------------------------------------

    @app.get("/api/me")
    def me(user: User = Depends(current_user)):
        return {"user": user.name, "email": user.email}

    @app.get("/api/meta")
    def meta(request: Request, store: UserStore = Depends(store_for)):
        out = store.meta()
        out["colors"] = {**COLORS, **out.pop("new_category_colors")}
        out["plaid_configured"] = request.app.state.plaid.configured
        out["plaid_oauth_ready"] = bool(request.app.state.settings.plaid_redirect_uri)
        return out

    # --- transactions ----------------------------------------------------------------------------

    @app.get("/api/transactions")
    def transactions(
        f: queries.Filters = Depends(filters),
        sort: str = "date",
        order: str = Query("desc", pattern="^(asc|desc)$"),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        store: UserStore = Depends(store_for),
    ):
        df = queries.apply_filters(store.expenses(), f)
        rows = queries.page(df, sort, order == "desc", offset, limit)
        return {
            "total": int(len(df)),
            "sum": round(float(df["amount"].sum()), 2),
            "rows": store.to_rows(rows),
        }

    @app.get("/api/summary/by-category")
    def by_category(
        f: queries.Filters = Depends(filters), store: UserStore = Depends(store_for)
    ):
        return queries.by_category(queries.apply_filters(store.expenses(), f))

    @app.get("/api/summary/over-time")
    def over_time(
        f: queries.Filters = Depends(filters),
        bin: str = "auto",
        store: UserStore = Depends(store_for),
    ):
        return queries.over_time(queries.apply_filters(store.expenses(), f), bin)

    @app.post("/api/transactions", status_code=201)
    def add_transaction(body: TransactionCreate, store: UserStore = Depends(store_for)):
        row = store.add_transaction(
            body.date, body.description, body.amount, body.category
        )
        return {"pk": row["pk"]}

    @app.patch("/api/transactions/{pk}")
    def update_transaction(
        pk: str, body: TransactionUpdate, store: UserStore = Depends(store_for)
    ):
        updates = {
            k: getattr(body, k)
            for k in body.model_fields_set
            if getattr(body, k) is not None
        }
        if not updates:
            raise HTTPException(422, "nothing to change")
        try:
            store.update_transaction(pk, updates)
        except KeyError:
            raise HTTPException(404, "no such transaction") from None
        return {"pk": pk}

    @app.delete("/api/transactions/{pk}", status_code=204)
    def delete_transaction(pk: str, store: UserStore = Depends(store_for)):
        try:
            store.delete_transaction(pk)
        except KeyError:
            raise HTTPException(404, "no such transaction") from None

    # --- the old sidebar's saved state, its SQL box, and its two charts ---------------------------

    @app.get("/api/state")
    def get_state(store: UserStore = Depends(store_for)):
        return store.state()

    @app.put("/api/state")
    def put_state(body: StateUpdate, store: UserStore = Depends(store_for)):
        updates = {}
        for key in body.model_fields_set:
            value = getattr(body, key)
            if key in ("min_date", "max_date"):
                updates[key] = value.isoformat() if value else None
            elif value is not None:
                updates[key] = value
        return store.update_state(updates)

    @app.post("/api/sql/default")
    def sql_default(body: DefaultQuery, store: UserStore = Depends(store_for)):
        query, warning = sqlview.default_query(
            store.sql_frame(),
            body.start,
            body.end,
            body.category_in,
            body.category_not_in,
            body.description,
            body.sources,
        )
        return {"query": query, "description_warning": warning}

    @app.post("/api/sql/run")
    def sql_run(body: SqlRun, store: UserStore = Depends(store_for)):
        return sqlview.rows_for_json(sqlview.run_query(store.sql_frame(), body.query))

    @app.post("/api/figures")
    def get_figures(body: FiguresRequest, store: UserStore = Depends(store_for)):
        df = sqlview.run_query(store.sql_frame(), body.query)
        if df.empty:
            empty = {"message": None, "figure": None}
            return {
                "rows": 0,
                "category": {**empty, "total": None, "table": []},
                "over_time": {**empty, "group": body.group},
            }
        new_categories = store.rules()["new_categories"]
        return {
            "rows": int(len(df)),
            "category": figures.category_chart(df, new_categories),
            "over_time": figures.over_time_chart(df, new_categories, body.group),
        }

    # --- rules -----------------------------------------------------------------------------------

    @app.get("/api/rules")
    def get_rules(store: UserStore = Depends(store_for)):
        return store.rules()

    @app.put("/api/rules")
    def put_rules(body: Rules, store: UserStore = Depends(store_for)):
        store.set_rules(body.model_dump())
        return store.rules()

    # --- files and the pipeline ------------------------------------------------------------------

    @app.get("/api/files")
    def files(store: UserStore = Depends(store_for)):
        return store.raw_files()

    @app.post("/api/files")
    def upload(
        request: Request,
        files: list[UploadFile] = File(...),
        store: UserStore = Depends(store_for),
    ):
        limit = request.app.state.settings.max_upload_bytes
        payload = []
        for f in files:
            data = f.file.read(limit + 1)
            if len(data) > limit:
                raise HTTPException(
                    413, f"{f.filename}: over the {limit // (1024 * 1024)} MB limit"
                )
            payload.append((f.filename, data))
        result = store.save_uploads(payload)
        result["pipeline"] = store.run_pipeline() if result["saved"] else None
        return result

    @app.delete("/api/files/{name}", status_code=204)
    def delete_file(name: str, store: UserStore = Depends(store_for)):
        try:
            store.delete_raw(name)
        except KeyError:
            raise HTTPException(404, "no such file") from None

    @app.post("/api/pipeline/run")
    def run_pipeline(
        body: PipelineRun | None = None, store: UserStore = Depends(store_for)
    ):
        return store.run_pipeline(rules_only=bool(body and body.rules_only))

    # --- Plaid -----------------------------------------------------------------------------------

    @app.get("/api/accounts")
    def accounts(store: UserStore = Depends(store_for)):
        return store.accounts()

    class PullIn(BaseModel):
        only: str | None = Field(
            default=None, max_length=64
        )  # refresh just this account
        after_login: bool = False  # a person has just logged in to it (the hand-login page's Done sends this)

    @app.post("/api/accounts/pull")
    def pull(
        request: Request,
        body: PullIn | None = None,
        store: UserStore = Depends(store_for),
    ):
        return pull_all(
            store,
            request.app.state.plaid,
            client_factory=request.app.state.plaid_client_factory,
            fetcher=request.app.state.fetcher,
            only=body.only if body else None,
            fresh_login=bool(body and body.after_login),
        )

    @app.post("/api/accounts/status")
    def accounts_status(request: Request, store: UserStore = Depends(store_for)):
        """Is each linked connection healthy, or does it need a reconnect (an expired bank login)?"""
        accounts = store.accounts()
        if not accounts:
            return []
        client = request.app.state.plaid_client_factory(request.app.state.plaid.get())
        out = []
        for a in accounts:
            token = store.account_token(a["alias"])
            status = (
                plaid_link.item_status(client, token)
                if token
                else {
                    "ok": False,
                    "error_code": "NO_TOKEN",
                    "needs_reconnect": False,
                    "consent_expires": None,
                }
            )
            out.append({**a, **status})
        return out

    @app.post("/api/plaid/link-token")
    def plaid_link_token(
        body: LinkTokenRequest,
        request: Request,
        user: User = Depends(current_user),
        store: UserStore = Depends(store_for),
    ):
        token = None
        if body.alias:
            token = store.account_token(body.alias)
            if not token:
                raise HTTPException(404, "no such linked account")
        client = request.app.state.plaid_client_factory(request.app.state.plaid.get())
        link_token = plaid_link.create_link_token(
            client,
            user.name,
            request.app.state.settings.plaid_redirect_uri,
            access_token=token,
        )
        return {"link_token": link_token, "mode": "update" if token else "new"}

    @app.post("/api/plaid/exchange", status_code=201)
    def plaid_exchange(
        body: ExchangeRequest, request: Request, store: UserStore = Depends(store_for)
    ):
        if store.has_account(body.alias):
            raise HTTPException(
                409,
                f"'{body.alias}' is already linked: use Reconnect, or pick another alias",
            )
        client = request.app.state.plaid_client_factory(request.app.state.plaid.get())
        access_token = plaid_link.exchange_public_token(client, body.public_token)
        try:
            institution = plaid_link.institution_name(client, access_token)
        except plaid_link.PlaidError:
            institution = None  # the link worked; the name is only a label
        start = (
            body.start_date.isoformat()
            if body.start_date
            else plaid_link.default_start_date()
        )
        store.add_account(body.alias, institution, start, access_token)
        return {"alias": body.alias, "institution": institution, "start_date": start}

    # --- the web app -----------------------------------------------------------------------------

    static = settings.static_dir
    if static and Path(static).is_dir():

        @app.get("/plaid-oauth", include_in_schema=False)
        def plaid_oauth_return():
            return FileResponse(Path(static) / "index.html")

        app.mount("/", StaticFiles(directory=static, html=True), name="web")
    return app
