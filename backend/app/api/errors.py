"""The handlers that render an application failure as clean JSON.

The exceptions themselves live in [`app/errors.py`](../errors.py), framework-free,
because services raise them and a service must not import the HTTP layer to do
so. They are re-exported here so `from app.api.errors import NotFoundError`
keeps working, and so this module still reads as one subject.

This is the only place that turns one into a status code and a body. Every
response has the same shape, `{"detail": "..."}`, so the frontend never has to
branch on where the error came from.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.automation.errors import (
    AlreadyAppliedError,
    AutomationError,
    BrowserNotReadyError,
    EasyApplyUnavailableError,
    ManualInputRequiredError,
    NotLoggedInError,
    SecurityCheckpointError,
    StopRequestedError,
    ThrottleLimitError,
    UnexpectedPageError,
)
from app.errors import (
    AppError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    PreconditionFailedError,
    UpstreamError,
    ValidationError,
)
from app.observability import get_logger

logger = get_logger(__name__)


# A checkpoint is never bypassed, so it is reported as "locked": the user has to
# resolve it in the browser themselves.
_AUTOMATION_STATUS: dict[type[Exception], int] = {
    SecurityCheckpointError: status.HTTP_423_LOCKED,
    ThrottleLimitError: status.HTTP_429_TOO_MANY_REQUESTS,
    NotLoggedInError: status.HTTP_409_CONFLICT,
    BrowserNotReadyError: status.HTTP_409_CONFLICT,
    AlreadyAppliedError: status.HTTP_409_CONFLICT,
    EasyApplyUnavailableError: status.HTTP_409_CONFLICT,
    StopRequestedError: status.HTTP_409_CONFLICT,
    ManualInputRequiredError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    # A page we do not recognise means LinkedIn changed its UI: an upstream fault.
    UnexpectedPageError: status.HTTP_502_BAD_GATEWAY,
    AutomationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _status_for_automation_error(exc: Exception) -> int:
    for klass in type(exc).__mro__:
        code = _AUTOMATION_STATUS.get(klass)  # type: ignore[arg-type]
        if code is not None:
            return code
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _log(request: Request, exc: Exception, status_code: int) -> None:
    logger.warning(
        str(exc) or type(exc).__name__,
        extra={
            "action": "http.error",
            "status": status_code,
            "error_type": type(exc).__name__,
            "path": request.url.path,
            "method": request.method,
        },
    )


def _json(status_code: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render an `AppError` with its own status code."""
    error = exc if isinstance(exc, AppError) else AppError(str(exc))
    _log(request, error, error.status_code)
    headers = (
        {"WWW-Authenticate": "Bearer"}
        if error.status_code == status.HTTP_401_UNAUTHORIZED
        else None
    )
    return _json(error.status_code, error.detail, headers)


async def automation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render any `app.automation.errors` exception."""
    status_code = _status_for_automation_error(exc)
    _log(request, exc, status_code)
    detail = str(exc) or "Automation failed."
    headers = None
    if isinstance(exc, SecurityCheckpointError):
        detail = (
            f"{exc.reason} Automation stopped. Resolve the verification in the browser "
            "window yourself, then start a new run."
        )
    elif isinstance(exc, ThrottleLimitError):
        headers = {"Retry-After": "3600"}
    return _json(status_code, detail, headers)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort: never leak a traceback to the client."""
    logger.error(
        "Unhandled error while serving the request.",
        exc_info=exc,
        extra={
            "action": "http.error",
            "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "error_type": type(exc).__name__,
            "path": request.url.path,
            "method": request.method,
        },
    )
    return _json(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


def register_exception_handlers(app: FastAPI) -> None:
    """Wire every domain exception to its HTTP representation."""
    app.add_exception_handler(AppError, app_error_handler)
    # Starlette walks the MRO, so registering the base class covers every subclass.
    app.add_exception_handler(AutomationError, automation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    try:
        from app.ai import AINotConfiguredError
    except ImportError:
        # The AI layer is optional at import time (its SDK may not be installed).
        logger.warning(
            "AI layer unavailable; its error handler was not registered.",
            extra={"action": "startup.ai_handler", "status": "skipped"},
        )
        return

    async def ai_not_configured_handler(request: Request, exc: Exception) -> JSONResponse:
        _log(request, exc, status.HTTP_503_SERVICE_UNAVAILABLE)
        return _json(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            str(exc) or "AI is not configured. Set ANTHROPIC_API_KEY and restart the server.",
        )

    app.add_exception_handler(AINotConfiguredError, ai_not_configured_handler)


# Re-exported so the HTTP layer stays one import for anyone reading it, and so
# the spelling every call site already uses keeps resolving.
__all__ = [
    "AppError",
    "AuthenticationError",
    "ConflictError",
    "NotFoundError",
    "PermissionDeniedError",
    "PreconditionFailedError",
    "UpstreamError",
    "ValidationError",
    "app_error_handler",
    "automation_error_handler",
    "register_exception_handlers",
    "unhandled_error_handler",
]
