"""FastAPI application. Wires routes, the database, and error envelopes."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.calls import router as calls_router
from app.api.patients import fail, router as patients_router
from app.config import ROOT, Settings, get_settings
from app.db.seed import seed_if_empty
from app.db.session import dispose_engine, get_engine, get_session_factory, init_engine
from app.realtime.hub import hub
from app.voice.webhooks import router as voice_router

logger = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.loop = asyncio.get_running_loop()
        init_engine(settings)
        app.state.settings = settings
        if settings.seed_on_startup:
            db = get_session_factory()()
            try:
                seed_if_empty(db)
            finally:
                db.close()
        yield
        dispose_engine()

    app = FastAPI(
        title="Voice Patient Registration",
        version="1.0.0",
        lifespan=lifespan,
        description="Patient registration API and voice-tool webhooks. Fake data only.",
    )
    app.include_router(patients_router)
    app.include_router(calls_router)
    app.include_router(voice_router)

    static_dir = ROOT / "app" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/health")
    def health() -> JSONResponse:
        database = "ok"
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            logger.exception("health check database failure")
            database = "error"
        status = 200 if database == "ok" else 503
        return JSONResponse(
            status_code=status,
            content={"data": {"status": "ok" if database == "ok" else "degraded", "database": database}, "error": None},
        )

    @app.get("/")
    def root() -> JSONResponse:
        return JSONResponse(
            content={
                "data": {
                    "service": "voice-patient-registration",
                    "health": "/health",
                    "docs": "/docs",
                    "dashboard": "/dashboard",
                    "patients": "/patients",
                },
                "error": None,
            }
        )

    @app.get("/dashboard")
    def dashboard() -> FileResponse:
        return FileResponse(static_dir / "dashboard" / "index.html")

    @app.get("/dashboard/calls/{call_id}")
    def flight(call_id: str) -> RedirectResponse:
        return RedirectResponse(url=f"/dashboard#call={call_id}")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return fail(exc.status_code, "HTTP_ERROR", message)

    @app.exception_handler(RequestValidationError)
    async def bad_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = {}
        for item in exc.errors():
            loc = ".".join(str(part) for part in item.get("loc", [])) or "body"
            fields[loc] = item.get("msg", "Invalid value.")
        return fail(400, "BAD_REQUEST", "Malformed request.", fields)

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        return fail(500, "INTERNAL_ERROR", "An unexpected error occurred.")

    return app


app = create_app()
