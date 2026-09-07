"""One provider for every OpenAI-compatible server, free ones included.

Ollama, Groq, Google's Gemini compatibility endpoint, OpenRouter, Cerebras and
llama.cpp all expose the same `POST {base_url}/chat/completions`. Supporting that
one shape is what makes the app runnable without a paid Anthropic key.

Structured output is the hard part, because "OpenAI-compatible" stops short of
it at different points on each server. This provider degrades through three
modes, remembering per-instance how far the server got so the cost is paid once:

1. `response_format: {"type": "json_schema", strict}` — the schema is enforced.
2. `response_format: {"type": "json_object"}` plus the schema in the system
   prompt — valid JSON guaranteed, conformance merely likely.
3. Plain text, with the schema in the prompt and the JSON extracted from the
   reply — the floor, for servers that reject `response_format` entirely.

A reply that still does not validate is reported as a refusal rather than raised,
which is the invariant the rest of `app.ai` is built on: the user gets the manual
fallback instead of an error page.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.providers.base import (
    STOP_END_TURN,
    STOP_MAX_TOKENS,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderResponse,
    ProviderTransientError,
    TextBlock,
    Usage,
    json_schema_for,
)
from app.observability import get_logger

logger = get_logger(__name__)

_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

# `finish_reason` values, translated into the vocabulary `client.py` branches on.
_FINISH_REASONS = {
    "stop": STOP_END_TURN,
    "length": STOP_MAX_TOKENS,
    "content_filter": "refusal",
}

# ```json ... ``` fences, which local models add even when told not to.
_FENCE = re.compile(r"```(?:json)?\s*(?P<body>.*?)\s*```", re.DOTALL)

# Effort maps onto sampling temperature: the only knob every server shares.
# Higher effort means less randomness, because these calls want the most likely
# answer, not a creative one.
_EFFORT_TEMPERATURE = {
    "low": 0.4,
    "medium": 0.3,
    "high": 0.15,
    "xhigh": 0.1,
    "max": 0.0,
}
_DEFAULT_TEMPERATURE = 0.2


class SchemaMode:
    """How far this server got with structured output. See the module docstring."""

    STRICT = "json_schema"
    JSON_OBJECT = "json_object"
    PROMPT_ONLY = "prompt_only"


class OpenAICompatProvider:
    """Chat completions against any OpenAI-compatible base URL."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        name: str = "openai_compat",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url:
            raise ProviderNotConfiguredError(
                f"The {name} provider needs AI_BASE_URL (for example "
                "http://localhost:11434/v1 for a local Ollama)."
            )
        if not model:
            raise ProviderNotConfiguredError(f"The {name} provider needs AI_MODEL.")
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._client = client
        self._owns_client = client is None
        self._schema_mode = SchemaMode.STRICT

    @property
    def model(self) -> str:
        return self._model

    def _new_client(self) -> httpx.AsyncClient:
        """Build the transport this provider will own.

        Split from `_http` so a caller can inject its own client (the tests do,
        with a `MockTransport`) and so the offline guard in `tests/conftest.py`
        can forbid *building* one without also blocking an injected one.
        """
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=_TIMEOUT)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self._new_client()
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None

    # --- request ------------------------------------------------------------

    async def send(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
        effort: str | None = None,
        output_format: type[BaseModel] | None = None,
    ) -> ProviderResponse:
        if output_format is None:
            payload = self._payload(
                system=system, user_prompt=user_prompt, max_tokens=max_tokens, effort=effort
            )
            return self._translate(await self._post(payload), output_format=None)

        schema = json_schema_for(output_format)
        # Walk down from the mode this instance last succeeded with, so a server
        # that never supported strict mode is not probed on every call.
        for mode in _modes_from(self._schema_mode):
            payload = self._payload(
                system=_system_for(mode, system, output_format, schema),
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                effort=effort,
                response_format=_response_format_for(mode, output_format, schema),
            )
            try:
                body = await self._post(payload)
            except _UnsupportedRequestError as exc:
                logger.info(
                    "Server rejected %s structured output; falling back.",
                    mode,
                    extra={
                        "action": "ai.schema_mode_downgrade",
                        "provider": self.name,
                        "mode": mode,
                        "detail": str(exc),
                    },
                )
                continue
            self._schema_mode = mode
            return self._translate(body, output_format=output_format)

        raise ProviderError(
            f"{self.name} rejected every structured-output mode for {self._model}."
        )

    def _payload(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
        effort: str | None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            # Some servers only read the newer name, others only the older one;
            # sending both is harmless and covers all of them.
            "max_completion_tokens": max_tokens,
            "temperature": _EFFORT_TEMPERATURE.get(effort or "", _DEFAULT_TEMPERATURE),
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format is not None:
            payload["response_format"] = response_format
        return payload

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._http().post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            # A connection or read failure is exactly the case a second attempt
            # can win — a cold local model, or a hosted endpoint dropping one
            # request. `_UnsupportedRequestError` is the one that never is.
            raise ProviderTransientError(
                f"{self.name} is unreachable at {self._base_url}: {exc}"
            ) from exc

        if response.status_code == 400:
            # A 400 here is almost always the request shape, not the content —
            # `send` treats it as "this structured-output mode is unsupported".
            raise _UnsupportedRequestError(_error_detail(response))
        if response.status_code == 429 or response.status_code >= 500:
            # The free tiers are rate-limited by design, so 429 is an expected
            # outcome on them rather than a misconfiguration.
            raise ProviderTransientError(
                f"{self.name} returned HTTP {response.status_code}: {_error_detail(response)}"
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"{self.name} returned HTTP {response.status_code}: {_error_detail(response)}"
            )

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name} returned a non-JSON body: {exc}") from exc
        return body

    # --- response -----------------------------------------------------------

    def _translate(
        self, body: dict[str, Any], *, output_format: type[BaseModel] | None
    ) -> ProviderResponse:
        choices = body.get("choices") or []
        if not choices:
            raise ProviderError(f"{self.name} returned no choices for {self._model}.")

        choice = choices[0] or {}
        message = choice.get("message") or {}
        model = str(body.get("model") or self._model)
        usage_body = body.get("usage") or {}
        usage = Usage(
            input_tokens=_as_int(usage_body.get("prompt_tokens")),
            output_tokens=_as_int(usage_body.get("completion_tokens")),
        )

        # An explicit refusal field is OpenAI's shape; `content_filter` is how the
        # rest signal the same thing. Either way it is a normal outcome.
        refusal = message.get("refusal")
        finish_reason = str(choice.get("finish_reason") or "stop")
        if refusal:
            return ProviderResponse.refusal(model, category=str(refusal)[:200])
        if _FINISH_REASONS.get(finish_reason) == "refusal":
            return ProviderResponse.refusal(model, category="content_filter")

        text = _message_text(message)
        stop_reason = _FINISH_REASONS.get(finish_reason, STOP_END_TURN)

        if output_format is None:
            return ProviderResponse(
                model=model,
                stop_reason=stop_reason,
                content=[TextBlock(text=text)],
                usage=usage,
            )

        parsed = _parse_json_into(output_format, text)
        if parsed is None:
            # Deliberately not an error: the caller's fallback path is what turns
            # this into "review it yourself" instead of a failed run.
            logger.warning(
                "Could not validate %s output from %s.",
                output_format.__name__,
                self.name,
                extra={
                    "action": "ai.unparsed_structured_output",
                    "provider": self.name,
                    "model": model,
                    "schema": output_format.__name__,
                },
            )
            return ProviderResponse(
                model=model,
                stop_reason=stop_reason,
                content=[TextBlock(text=text)],
                usage=usage,
            )

        return ProviderResponse(
            model=model,
            stop_reason=stop_reason,
            parsed_output=parsed,
            content=[TextBlock(text=text)],
            usage=usage,
        )


class _UnsupportedRequestError(ProviderError):
    """HTTP 400 — this request shape is not supported by this server."""


def _modes_from(mode: str) -> list[str]:
    order = [SchemaMode.STRICT, SchemaMode.JSON_OBJECT, SchemaMode.PROMPT_ONLY]
    return order[order.index(mode) :]


def _response_format_for(
    mode: str, output_format: type[BaseModel], schema: dict[str, Any]
) -> dict[str, Any] | None:
    if mode == SchemaMode.STRICT:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": output_format.__name__,
                "strict": True,
                "schema": schema,
            },
        }
    if mode == SchemaMode.JSON_OBJECT:
        return {"type": "json_object"}
    return None


def _system_for(
    mode: str, system: str, output_format: type[BaseModel], schema: dict[str, Any]
) -> str:
    """In strict mode the server enforces the schema; otherwise the prompt must."""
    if mode == SchemaMode.STRICT:
        return system
    return (
        f"{system}\n\n"
        f"Reply with a single JSON object and nothing else — no prose, no markdown "
        f"fence. It must validate against this JSON Schema for {output_format.__name__}:\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )


def _message_text(message: dict[str, Any]) -> str:
    """The assistant text, from either the string or the block-list content shape."""
    content = message.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        )
    else:
        text = ""

    # Reasoning models expose the answer separately from their thinking; the
    # thinking is not the answer, so it is only used when nothing else is there.
    if not text.strip():
        text = str(message.get("reasoning_content") or "")
    return text.strip()


def _parse_json_into(output_format: type[BaseModel], text: str) -> BaseModel | None:
    """Validate `text` into the model, tolerating fences and surrounding prose."""
    for candidate in _json_candidates(text):
        try:
            return output_format.model_validate_json(candidate)
        except (ValidationError, ValueError):
            continue
    return None


def _json_candidates(text: str) -> list[str]:
    """The raw reply, its fenced body, and its outermost {...} — in that order."""
    stripped = text.strip()
    if not stripped:
        return []

    candidates = [stripped]
    fenced = _FENCE.search(stripped)
    if fenced:
        candidates.append(fenced.group("body").strip())
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:400]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)[:400]
    return str(error or body)[:400]


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


__all__ = ["OpenAICompatProvider", "SchemaMode"]
