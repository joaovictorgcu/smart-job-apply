"""The provider seam: one response shape, whatever model produced it.

`AIClient` used to talk to the Anthropic SDK directly, so its refusal handling
(`stop_reason == "refusal"`, `parsed_output`, `usage.input_tokens`) was written
against that SDK's response object. Rather than rewrite that logic per provider —
and risk one of them losing the "a refusal is a normal outcome" invariant —
every provider returns a `ProviderResponse` with the same attribute names.

`AIClient` therefore reads one shape and keeps its degradation rules intact:
a refusal, an unparsable answer and an empty answer all still become an empty
value plus `AIUsage.refused`, never an exception.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

# Mirrors Anthropic's own vocabulary, because that is what the refusal handling in
# `app.ai.client` already branches on. An OpenAI-compatible `finish_reason` is
# translated into these on the way in.
STOP_END_TURN = "end_turn"
STOP_MAX_TOKENS = "max_tokens"
STOP_REFUSAL = "refusal"


class ProviderError(RuntimeError):
    """A provider call failed in a way the caller must record and move on from."""


class ProviderNotConfiguredError(ProviderError):
    """The selected provider is missing the settings it needs to run."""


class ProviderTransientError(ProviderError):
    """A failure worth retrying: a timeout, a 5xx, or a rate limit.

    Typed rather than inferred from the message, so `AIClient`'s retry loop never
    has to pattern-match error text to decide whether a second attempt is sane.
    """


@dataclass(frozen=True)
class TextBlock:
    """One content block, matching what `_first_text` in `client.py` reads."""

    text: str
    type: str = "text"


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class StopDetails:
    """Anthropic's refusal detail object; `category` is the only field read."""

    category: str | None = None


@dataclass
class ProviderResponse:
    """Normalized model reply.

    Attribute names are deliberately the Anthropic SDK's: `client.py` reads
    `.stop_reason`, `.parsed_output`, `.content`, `.usage`, `.model` and
    `.stop_details`, and nothing there needs to know which provider answered.
    """

    model: str
    stop_reason: str = STOP_END_TURN
    parsed_output: BaseModel | None = None
    content: list[TextBlock] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    stop_details: StopDetails | None = None

    @property
    def text(self) -> str:
        for block in self.content:
            if block.type == "text":
                return block.text
        return ""

    @classmethod
    def refusal(cls, model: str, *, category: str | None = None) -> ProviderResponse:
        return cls(
            model=model,
            stop_reason=STOP_REFUSAL,
            stop_details=StopDetails(category=category),
        )


@runtime_checkable
class ChatProvider(Protocol):
    """One request to one model.

    `output_format` being non-None means the caller wants validated structured
    output: the provider must return `parsed_output` as an instance of that model,
    or a refusal. `effort` is a hint — a provider without an equivalent knob
    ignores it rather than failing.
    """

    #: Identifier used in logs, audit rows and the pricing table.
    name: str

    @property
    def model(self) -> str:
        """The model this provider instance will call."""
        ...

    async def send(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
        effort: str | None = None,
        output_format: type[BaseModel] | None = None,
    ) -> ProviderResponse: ...

    async def aclose(self) -> None:
        """Release any transport held open. Safe to call more than once."""
        ...


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """A JSON Schema for `model` that strict structured-output modes accept.

    Pydantic's own schema is close but not sufficient: the strict modes offered by
    OpenAI-compatible servers reject `default`/`title` annotations, require
    `additionalProperties: false` on every object, and require every declared
    property to appear in `required` (optionality is expressed by allowing null,
    not by omission). This rewrites the schema in place to satisfy all three.

    Making defaulted fields required is intentional: the model has to emit them,
    and Pydantic validates them normally on the way back. The alternative —
    omitting them — is what makes strict mode reject the request outright.
    """
    schema = model.model_json_schema()
    _tighten(schema)
    for definition in (schema.get("$defs") or {}).values():
        _tighten(definition)
    return schema


# Annotations that carry no constraint for the model but that strict modes treat
# as unknown keywords and reject.
_STRIPPED_KEYS = ("default", "title", "examples", "$comment", "deprecated")


def _tighten(node: Any) -> None:
    """Recursively make one schema node acceptable to strict structured output."""
    if isinstance(node, list):
        for item in node:
            _tighten(item)
        return
    if not isinstance(node, dict):
        return

    for key in _STRIPPED_KEYS:
        node.pop(key, None)

    if node.get("type") == "object" or "properties" in node:
        properties = node.get("properties") or {}
        node["additionalProperties"] = False
        # Every property required; nullability, not absence, expresses "optional".
        node["required"] = list(properties.keys())

    for key, value in node.items():
        # `required` is a list of plain strings, and `properties` keys are field
        # names — neither is a schema node, but the values under `properties` are.
        if key == "required":
            continue
        _tighten(value)


__all__ = [
    "STOP_END_TURN",
    "STOP_MAX_TOKENS",
    "STOP_REFUSAL",
    "ChatProvider",
    "ProviderError",
    "ProviderNotConfiguredError",
    "ProviderResponse",
    "ProviderTransientError",
    "StopDetails",
    "TextBlock",
    "Usage",
    "json_schema_for",
]
