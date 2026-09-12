"""Anthropic provider — the original transport, behind the provider seam.

Everything here was previously inline in `AIClient._send`, including the
`output_config` compatibility shim. The retry policy stays in `AIClient` so it
applies to every provider identically; this module only translates one request
and one response.

The SDK is imported lazily. `app.api.errors` treats the Anthropic package as
optional at import time, and a user running on a free provider should not need it
installed at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from app.ai.providers.base import (
    ProviderError,
    ProviderNotConfiguredError,
    ProviderResponse,
    StopDetails,
    TextBlock,
    Usage,
)
from app.observability import get_logger

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

logger = get_logger(__name__)

# Version-compatibility shim state: SDK builds disagree on whether
# `output_config` may accompany `output_format`. Once a build rejects the pair we
# stop sending it and log the downgrade a single time.
_output_config_supported = True
_shim_logged = False


def _mentions_output_config(error: Exception) -> bool:
    message = str(error).lower()
    return "output_config" in message or "effort" in message


def _as_configuration_error(error: Exception) -> Exception:
    """Turn a rejected credential into `ProviderNotConfiguredError`.

    The taxonomy in `providers/base.py` already separates "this provider is not
    set up" from "this call failed, try again". A 401 belongs firmly in the
    first: the key is present but the API will not accept it, and no retry and
    no amount of waiting changes that. Only the operator can.

    Everything else is returned untouched, so a rate limit stays retryable and
    a genuine model refusal still degrades to manual input.
    """
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is declared
        return error

    rejected = (anthropic.AuthenticationError, anthropic.PermissionDeniedError)
    if isinstance(error, rejected):
        return ProviderNotConfiguredError(
            f"The Anthropic API rejected this key: {error}. Check ANTHROPIC_API_KEY, "
            "or point AI_PROVIDER at another provider."
        )
    return error


def _note_shim_downgrade(error: Exception) -> None:
    """Disable `output_config` for this process, logging the downgrade once."""
    global _output_config_supported, _shim_logged
    _output_config_supported = False
    if not _shim_logged:
        _shim_logged = True
        logger.warning(
            "Installed Anthropic SDK rejects output_config alongside output_format; "
            "retrying without effort control for the rest of this process (%s).",
            error,
            extra={"action": "ai.output_config_downgrade", "detail": str(error)},
        )


class AnthropicProvider:
    """Calls the Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, *, api_key: str, model: str) -> None:
        if not api_key:
            raise ProviderNotConfiguredError(
                "The anthropic provider needs ANTHROPIC_API_KEY. Set AI_PROVIDER to a "
                "free provider (ollama, groq, gemini, openrouter) to run without it."
            )
        self._api_key = api_key
        self._model = model
        self._client: AsyncAnthropic | None = None

    @property
    def model(self) -> str:
        return self._model

    def _require_client(self) -> AsyncAnthropic:
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:  # pragma: no cover - dependency is declared
                raise ProviderNotConfiguredError(
                    "The anthropic package is not installed. Install it, or set "
                    "AI_PROVIDER to a free provider."
                ) from exc
            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def send(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
        effort: str | None = None,
        output_format: type[BaseModel] | None = None,
    ) -> ProviderResponse:
        try:
            return await self._send(
                system=system,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                effort=effort,
                output_format=output_format,
            )
        except Exception as exc:
            # A key the API rejects is a *configuration* failure, not a model
            # refusal and not something a retry fixes. Left untranslated it
            # arrives upstairs as "the AI produced no score", and the app then
            # reports a cheerful 200 with whatever score the job already had —
            # so an expired key looks exactly like a working one. Raising the
            # configured-wrong error instead reaches the user as a 503 that
            # names the problem.
            raise _as_configuration_error(exc) from exc

    async def _send(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
        effort: str | None = None,
        output_format: type[BaseModel] | None = None,
    ) -> ProviderResponse:
        import anthropic

        client = self._require_client()
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if output_format is not None:
            kwargs["output_format"] = output_format

        call = client.messages.parse if output_format is not None else client.messages.create
        if effort and _output_config_supported:
            try:
                return _translate(
                    await call(**kwargs, output_config={"effort": effort}), self._model
                )
            except TypeError as exc:
                _note_shim_downgrade(exc)
            except anthropic.BadRequestError as exc:
                if not _mentions_output_config(exc):
                    raise
                _note_shim_downgrade(exc)
        return _translate(await call(**kwargs), self._model)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


def _translate(response: Any, fallback_model: str) -> ProviderResponse:
    """Copy the SDK response into the provider-agnostic shape."""
    usage = getattr(response, "usage", None)
    details = getattr(response, "stop_details", None)
    blocks = [
        TextBlock(text=block.text)
        for block in (response.content or [])
        if getattr(block, "type", None) == "text"
    ]
    return ProviderResponse(
        model=getattr(response, "model", None) or fallback_model,
        stop_reason=getattr(response, "stop_reason", None) or "end_turn",
        parsed_output=getattr(response, "parsed_output", None),
        content=blocks,
        usage=Usage(
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        ),
        stop_details=(
            StopDetails(category=getattr(details, "category", None))
            if details is not None
            else None
        ),
    )


def is_retryable(error: Exception) -> bool:
    """Transient Anthropic failures, for the retry loop in `AIClient`."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is declared
        return False
    if isinstance(error, anthropic.RateLimitError):
        return True
    if isinstance(error, anthropic.APIStatusError):
        return error.status_code >= 500
    # Covers APITimeoutError, which subclasses APIConnectionError.
    return isinstance(error, anthropic.APIConnectionError)


def is_provider_api_error(error: Exception) -> bool:
    """True for errors raised by the Anthropic SDK itself."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is declared
        return False
    return isinstance(error, anthropic.APIError)


__all__ = ["AnthropicProvider", "ProviderError", "is_provider_api_error", "is_retryable"]
