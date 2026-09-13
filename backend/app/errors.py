"""The failures a service can raise, with no framework attached.

These classes used to live in `app/api/errors.py`, next to the handlers that
render them. Every service raises them, so every service imported the HTTP
package — and through it FastAPI — to say "this job does not exist". That is the
dependency arrow pointing the wrong way: the layer that owns the rules was
importing the layer that owns the transport, and `tools/guards.py` G9 now fails
a build that does it again.

The status code stays on the class on purpose. It is not the HTTP layer leaking
downwards: "not found" and "the resource is not in a state that allows this" are
distinctions the service layer is *making*, and the number is the shortest name
the industry has for each of them. `http.HTTPStatus` is standard library, so
carrying it costs nothing and imports nothing.

`app/api/errors.py` keeps the handlers, and re-exports these names so the
existing spelling still resolves.
"""

from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    """Base of every application-level failure the API knows how to render."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    default_detail: str = "Unexpected error."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    """The requested resource does not exist, or does not belong to the caller."""

    status_code = HTTPStatus.NOT_FOUND
    default_detail = "Resource not found."


class ConflictError(AppError):
    """The request collides with existing data (duplicate email, duplicate job)."""

    status_code = HTTPStatus.CONFLICT
    default_detail = "Resource already exists."


class ValidationError(AppError):
    """The payload is syntactically valid but semantically wrong."""

    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    default_detail = "Invalid request."


class PermissionDeniedError(AppError):
    """Authenticated, but not allowed to perform this action."""

    status_code = HTTPStatus.FORBIDDEN
    default_detail = "Operation not allowed."


class AuthenticationError(AppError):
    """Missing, invalid or expired credentials."""

    status_code = HTTPStatus.UNAUTHORIZED
    default_detail = "Invalid credentials."


class UpstreamError(AppError):
    """A dependency we do not control (the AI, LinkedIn's UI) failed."""

    status_code = HTTPStatus.BAD_GATEWAY
    default_detail = "An upstream service failed."


class PreconditionFailedError(AppError):
    """The resource is not in a state that allows this action.

    This is the error that guards assisted mode: submitting an application that
    is not awaiting review, or submitting without explicit confirmation.
    """

    status_code = HTTPStatus.PRECONDITION_FAILED
    default_detail = "The resource is not in a state that allows this operation."


__all__ = [
    "AppError",
    "AuthenticationError",
    "ConflictError",
    "NotFoundError",
    "PermissionDeniedError",
    "PreconditionFailedError",
    "UpstreamError",
    "ValidationError",
]
