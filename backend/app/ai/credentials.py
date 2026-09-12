"""Whose key answers for this account.

`app.ai.providers` decides *which* provider runs from a settings-shaped object.
This module decides *whose settings that is* — the deployment's, or the
account's own — and returns one object of that shape either way.

The reason the choice exists is a quota, not a preference. Every free tier this
app supports is rate-limited **per key**: one shared `AI_API_KEY` across fifty
accounts is one 429 for all fifty on the first busy afternoon. An account that
brings its own free key gets its own quota, and the deployment pays for nothing.

Three rules shape what an account is allowed to bring:

* **A key, never an endpoint.** `AI_BASE_URL` stays deployment-level. Letting a
  user point the server at a URL of their choosing is a server-side request
  forgery with extra steps — the server would happily fetch `169.254.169.254`
  and hand back whatever it found. The providers an account may select are
  named presets whose base URLs are compiled in.
* **No local providers either.** `ollama` and `llamacpp` are localhost, and on a
  hosted deployment "localhost" is the *server*, not the user's laptop. A
  deployment that runs a local model selects it globally; an account leaves the
  provider blank and inherits it.
* **Failing to resolve is not failing silently.** A key that cannot be decrypted
  (an `ENCRYPTION_KEY` rotated without re-entry, most likely) yields credentials
  that are disabled and carry the reason, which `AIClient` raises on first use.
  It never falls back to the deployment key: that would quietly bill the
  account's work to everybody else's quota.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from app.ai.providers import ANTHROPIC, PRESETS
from app.auth.crypto import decrypt_text
from app.config import Settings, get_settings
from app.observability import get_logger

logger = get_logger(__name__)

#: The credentials came from `.env` — one key, shared by every account.
DEPLOYMENT = "deployment"
#: The credentials came from the account's own settings row.
ACCOUNT = "account"

#: Providers an account may select for itself: the hosted presets that take a
#: key, plus the paid Anthropic path. Derived from `PRESETS` rather than listed,
#: so adding a preset there makes it selectable here without a second edit —
#: and a keyless (local) preset stays deployment-only by construction.
USER_SELECTABLE_PROVIDERS = frozenset(
    {ANTHROPIC, *(name for name, preset in PRESETS.items() if preset.requires_key)}
)


def key_hint(provider: str) -> str:
    """Where to get a key for `provider`, for a message that can be acted on."""
    if provider == ANTHROPIC:
        return "Create a key at https://console.anthropic.com/settings/keys"
    preset = PRESETS.get(provider)
    return preset.key_hint if preset else ""


@dataclass(frozen=True, slots=True)
class AICredentials:
    """A settings-shaped object naming one provider and one key.

    The field names are `Settings`' own, because `build_provider` and
    `describe_provider` read them by name off whatever they are handed. That
    duck typing is what lets an account's credentials travel the same path as
    the deployment's without a branch anywhere downstream.
    """

    ai_provider: str
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    ai_stub_score: int | None = None
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    scoring_effort: str = "low"
    #: DEPLOYMENT or ACCOUNT — surfaced in the UI so "why did this run out of
    #: quota" has an answer that does not require reading the server's `.env`.
    source: str = DEPLOYMENT
    enabled: bool = False
    #: Why not, when `enabled` is False. Raised verbatim on first use.
    reason: str = ""

    @property
    def resolved_ai_provider(self) -> str:
        """Already resolved at construction; `build_provider` prefers this."""
        return self.ai_provider

    @property
    def ai_enabled(self) -> bool:
        return self.enabled


def for_deployment(settings: Settings | None = None) -> AICredentials:
    """What `.env` configured, resolved the way `Settings` already resolves it."""
    current = settings or get_settings()
    return AICredentials(
        ai_provider=current.resolved_ai_provider,
        ai_api_key=current.ai_api_key,
        ai_base_url=current.ai_base_url,
        ai_model=current.ai_model,
        ai_stub_score=current.ai_stub_score,
        anthropic_api_key=current.anthropic_api_key,
        anthropic_model=current.anthropic_model,
        scoring_effort=current.scoring_effort,
        source=DEPLOYMENT,
        enabled=current.ai_enabled,
        reason=(
            ""
            if current.ai_enabled
            else (
                "This deployment has no AI provider configured, and this account "
                "has not added a key of its own."
            )
        ),
    )


def for_account(
    provider: str,
    api_key: str,
    *,
    model: str = "",
    settings: Settings | None = None,
) -> AICredentials:
    """Credentials for one account's own key.

    Used both by the settings row and by the "test this key" endpoint, so what
    the test exercises is exactly what a scoring run will use.
    """
    current = settings or get_settings()
    provider = provider.strip().lower()
    model = model.strip()

    if provider not in USER_SELECTABLE_PROVIDERS:
        return AICredentials(
            ai_provider=provider,
            source=ACCOUNT,
            enabled=False,
            reason=(
                f"{provider!r} cannot be selected per account. Choose one of: "
                f"{', '.join(sorted(USER_SELECTABLE_PROVIDERS))}."
            ),
        )

    if not api_key:
        hint = key_hint(provider)
        return AICredentials(
            ai_provider=provider,
            ai_model=model,
            source=ACCOUNT,
            enabled=False,
            reason=f"No API key stored for {provider}." + (f" {hint}." if hint else ""),
        )

    return AICredentials(
        ai_provider=provider,
        ai_api_key=api_key if provider != ANTHROPIC else "",
        # Deliberately empty: the preset's compiled-in URL is the only endpoint
        # an account-selected provider is ever pointed at.
        ai_base_url="",
        ai_model=model,
        anthropic_api_key=api_key if provider == ANTHROPIC else "",
        anthropic_model=model or current.anthropic_model,
        scoring_effort=current.scoring_effort,
        source=ACCOUNT,
        enabled=True,
    )


def for_settings_row(row: Any, *, settings: Settings | None = None) -> AICredentials:
    """The credentials this account's work should run on.

    An account with no provider of its own inherits the deployment's, keeping
    its model override — which is how `ai_model` behaved before accounts could
    bring a provider at all.
    """
    current = settings or get_settings()
    provider = _text(row, "ai_provider")
    model = _text(row, "ai_model")

    if not provider:
        return _with_model(for_deployment(current), model)

    token = _text(row, "ai_api_key_encrypted")
    if not token:
        return for_account(provider, "", model=model, settings=current)

    try:
        api_key = decrypt_text(token)
    except Exception:
        # The token itself is never logged, and neither is what it decrypts to.
        logger.warning(
            "Stored AI key could not be decrypted.",
            extra={"action": "ai.credentials", "status": "error", "provider": provider},
        )
        return AICredentials(
            ai_provider=provider,
            ai_model=model,
            source=ACCOUNT,
            enabled=False,
            reason=(
                "The API key stored for this account could not be decrypted. "
                "Enter it again in Settings."
            ),
        )

    return for_account(provider, api_key, model=model, settings=current)


def _with_model(credentials: AICredentials, model: str) -> AICredentials:
    """`credentials` with an account's model override applied, if it set one."""
    if not model:
        return credentials
    return replace(credentials, ai_model=model, anthropic_model=model)


def _text(row: Any, field: str) -> str:
    if row is None:
        return ""
    value = getattr(row, field, "") or ""
    return str(value).strip()


__all__ = [
    "ACCOUNT",
    "DEPLOYMENT",
    "USER_SELECTABLE_PROVIDERS",
    "AICredentials",
    "for_account",
    "for_deployment",
    "for_settings_row",
    "key_hint",
]
