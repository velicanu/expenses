"""The API. Run: uvicorn server.app:create_app --factory --no-proxy-headers   (see the Dockerfile)

Every /api route needs a logged-in user (auth.current_user) and only ever touches that user's directory.
"""

import datetime as dt
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import queries
from .auth import User, current_user
from .bao import PlaidKeys, PlaidUnavailable
from .palette import COLORS
from .plaid_pull import pull_all
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


class PipelineRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules_only: bool = False


# --- app ---------------------------------------------------------------------------------------------


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="expenses",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.stores = Stores(settings.data_root)
    app.state.plaid = PlaidKeys(settings.bao)

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
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'",
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

    @app.post("/api/accounts/pull")
    def pull(request: Request, store: UserStore = Depends(store_for)):
        return pull_all(store, request.app.state.plaid)

    # --- the web app -----------------------------------------------------------------------------

    static = settings.static_dir
    if static and Path(static).is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="web")
    return app
