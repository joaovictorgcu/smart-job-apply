"""FastAPI application factory and ASGI entry point (`uvicorn app.main:app`)."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import __version__
from app.api.deps import limiter
from app.api.errors import register_exception_handlers
from app.api.routes import api_router
from app.config import PROJECT_ROOT, get_settings
from app.database.session import dispose_engine, init_models
from app.observability import bind_context, clear_context, configure_logging, get_logger
from app.services import automation_service

settings = get_settings()
configure_logging("DEBUG" if settings.debug else "INFO", as_json=not settings.debug)
logger = get_logger(__name__)

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
API_PREFIX = "/api"


class RequestContextMiddleware:
    """Bind a request id to the log context and log one line per request.

    Implemented as raw ASGI rather than `BaseHTTPMiddleware` on purpose: the
    dependency that resolves the current user binds `user_id` into a context
    variable, and only same-task middleware sees that binding.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:12]
        clear_context()
        bind_context(request_id=request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode("ascii")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "Request handled.",
                extra={
                    "action": "http.request",
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_code,
                    "duration_ms": duration_ms,
                },
            )
            clear_context()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create missing tables on startup; close browsers and the pool on shutdown."""
    await init_models()
    logger.info(
        "API started.",
        extra={
            "action": "startup",
            "status": "ok",
            "version": __version__,
            "environment": settings.environment,
            "ai_configured": settings.ai_enabled,
        },
    )
    try:
        yield
    finally:
        await automation_service.shutdown_engine()
        await dispose_engine()
        logger.info("API stopped.", extra={"action": "shutdown", "status": "ok"})


async def rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    """Same `{"detail": ...}` shape as every other error."""
    detail = "Too many requests. Slow down and try again shortly."
    logger.warning(
        detail,
        extra={
            "action": "http.rate_limit",
            "status": status.HTTP_429_TOO_MANY_REQUESTS,
            "path": request.url.path,
        },
    )
    response = JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={"detail": detail}
    )
    if isinstance(exc, RateLimitExceeded):
        response.headers["Retry-After"] = "60"
    return response


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built single-page app, or explain how to build it."""
    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index = FRONTEND_DIST / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def spa(full_path: str) -> FileResponse | JSONResponse:
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Unknown API endpoint."}
            )
        if not index.is_file():
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "detail": (
                        "The frontend has not been built. Run 'npm run dev' in ./frontend for "
                        "development, or 'npm run build' to have this server serve it."
                    ),
                    "api_docs": "/docs",
                },
            )
        # A real file (favicon, manifest, robots.txt) wins; anything else is a
        # client-side route and must receive index.html. Containment is checked
        # before the file test so no crafted path can read outside the build.
        candidate = (FRONTEND_DIST / full_path).resolve()
        inside = candidate.is_relative_to(FRONTEND_DIST.resolve())
        if full_path and inside and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


def create_app() -> FastAPI:
    """Build the application: routers, middleware, error handling, static files."""
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Assisted-mode LinkedIn application helper. Searching, scoring and filling are "
            "separate steps, and no application is ever submitted without an explicit, "
            "per-application confirmation."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    register_exception_handlers(app)

    app.include_router(api_router, prefix=API_PREFIX)

    # Added last, so it wraps everything and can log the final status code.
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    _mount_frontend(app)
    return app


app = create_app()
