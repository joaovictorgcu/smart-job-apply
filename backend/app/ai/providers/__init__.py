"""Provider selection: which model answers, decided by configuration alone.

`AI_PROVIDER` names one of the presets below. The presets exist so that running
on a free provider is one line of `.env`, not a research task: each carries the
base URL and a default model that is actually available on that service's free
tier, and `AI_BASE_URL` / `AI_MODEL` override either of them.

    AI_PROVIDER=ollama       # local, no key, no quota, nothing leaves the machine
    AI_PROVIDER=groq         # free tier, needs GROQ/AI_API_KEY
    AI_PROVIDER=gemini       # free tier, needs an AI Studio key
    AI_PROVIDER=openrouter   # free `:free` models, needs a key
    AI_PROVIDER=cerebras     # free tier, needs a key
    AI_PROVIDER=stub         # offline, deterministic; used by the test suite
    AI_PROVIDER=anthropic    # the paid original

Resumes and screening answers carry a lot of personal data. `ollama` is the
default recommendation for exactly that reason: a local model sends none of it
anywhere. The hosted free tiers are a convenience, and their terms — including
whether prompts train the model — are the user's call, not ours.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.providers.base import (
    ChatProvider,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderResponse,
    StopDetails,
    TextBlock,
    Usage,
    json_schema_for,
)
from app.ai.providers.openai_compat import OpenAICompatProvider, SchemaMode
from app.ai.providers.stub import STUB_MODEL, StubProvider

ANTHROPIC = "anthropic"
STUB = "stub"


@dataclass(frozen=True)
class Preset:
    """An OpenAI-compatible service, pinned to a model its free tier serves."""

    base_url: str
    model: str
    #: False for a server that needs no credential (a local one).
    requires_key: bool = True
    #: Shown when the key is missing, so the message says where to get one.
    key_hint: str = ""


PRESETS: dict[str, Preset] = {
    "ollama": Preset(
        base_url="http://localhost:11434/v1",
        # Small enough for a laptop, and reliable at JSON output — which matters
        # more here than raw quality, since every reply is a validated schema.
        model="qwen2.5:7b-instruct",
        requires_key=False,
    ),
    "llamacpp": Preset(
        base_url="http://localhost:8080/v1",
        model="local-model",
        requires_key=False,
    ),
    "groq": Preset(
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.3-70b-versatile",
        key_hint="Create a free key at https://console.groq.com/keys",
    ),
    "gemini": Preset(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-2.5-flash",
        key_hint="Create a free key at https://aistudio.google.com/apikey",
    ),
    "openrouter": Preset(
        base_url="https://openrouter.ai/api/v1",
        model="deepseek/deepseek-chat-v3.1:free",
        key_hint="Create a key at https://openrouter.ai/keys",
    ),
    "cerebras": Preset(
        base_url="https://api.cerebras.ai/v1",
        model="llama-3.3-70b",
        key_hint="Create a free key at https://cloud.cerebras.ai/",
    ),
    # Escape hatch for any server not listed: supply AI_BASE_URL and AI_MODEL.
    "openai_compat": Preset(base_url="", model="", requires_key=False),
}

#: Every accepted value of `AI_PROVIDER`.
PROVIDER_NAMES = (ANTHROPIC, STUB, *PRESETS)


def build_provider(settings: object) -> ChatProvider:
    """The provider `AI_PROVIDER` selects, configured from `settings`.

    Raises `ProviderNotConfiguredError` with a message naming the missing value,
    because "AI silently did nothing" is the failure this seam exists to prevent.
    """
    name = _selected(settings)

    if name == STUB:
        forced = getattr(settings, "ai_stub_score", None)
        return StubProvider(
            model=str(getattr(settings, "ai_model", "") or STUB_MODEL),
            forced_score=forced if isinstance(forced, int) else None,
        )

    if name == ANTHROPIC:
        from app.ai.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=str(getattr(settings, "anthropic_api_key", "") or ""),
            model=str(getattr(settings, "anthropic_model", "") or "claude-opus-5"),
        )

    preset = PRESETS.get(name)
    if preset is None:
        raise ProviderNotConfiguredError(
            f"Unknown AI_PROVIDER {name!r}. Choose one of: {', '.join(PROVIDER_NAMES)}."
        )

    base_url = str(getattr(settings, "ai_base_url", "") or preset.base_url)
    model = str(getattr(settings, "ai_model", "") or preset.model)
    api_key = str(getattr(settings, "ai_api_key", "") or "")

    if preset.requires_key and not api_key:
        hint = f" {preset.key_hint}." if preset.key_hint else ""
        raise ProviderNotConfiguredError(
            f"AI_PROVIDER={name} needs AI_API_KEY.{hint}"
        )

    return OpenAICompatProvider(base_url=base_url, model=model, api_key=api_key, name=name)


def _selected(settings: object) -> str:
    """The provider name, preferring `Settings.resolved_ai_provider`.

    Read through the property rather than the raw field so the "no key means
    offline, not disabled" rule lives in one place. `getattr` keeps this usable
    with any object that carries the same attribute names, which is what the
    provider tests pass in.
    """
    resolved = getattr(settings, "resolved_ai_provider", None)
    if isinstance(resolved, str) and resolved.strip():
        return resolved.strip().lower()
    return str(getattr(settings, "ai_provider", "") or ANTHROPIC).strip().lower()


def describe_provider(settings: object) -> str:
    """`provider/model`, for logs and the health endpoint."""
    name = _selected(settings)
    if name == ANTHROPIC:
        return f"{ANTHROPIC}/{getattr(settings, 'anthropic_model', '') or 'claude-opus-5'}"
    explicit = str(getattr(settings, "ai_model", "") or "")
    if explicit:
        return f"{name}/{explicit}"
    preset = PRESETS.get(name)
    return f"{name}/{preset.model if preset else STUB_MODEL}"


__all__ = [
    "ANTHROPIC",
    "PRESETS",
    "PROVIDER_NAMES",
    "STUB",
    "ChatProvider",
    "OpenAICompatProvider",
    "Preset",
    "ProviderError",
    "ProviderNotConfiguredError",
    "ProviderResponse",
    "SchemaMode",
    "StopDetails",
    "StubProvider",
    "TextBlock",
    "Usage",
    "build_provider",
    "describe_provider",
    "json_schema_for",
]
