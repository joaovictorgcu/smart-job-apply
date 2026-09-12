"""Automation guardrails and AI preferences."""

# No `from __future__ import annotations` here, for the reason spelled out in
# `routes/auth.py`: slowapi wraps the rate-limited endpoint below, and FastAPI
# would resolve string annotations against slowapi's module globals.

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.ai import credentials as ai_credentials
from app.ai.client import AINotConfiguredError, get_ai_client
from app.ai.providers import ProviderError
from app.api.deps import CurrentUser, SessionDep, limiter
from app.config import get_settings
from app.observability import get_logger
from app.schemas.user import UserSettingsRead, UserSettingsUpdate
from app.services import user_service

logger = get_logger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])
settings = get_settings()


class AIProviderOption(BaseModel):
    """One provider an account may select, and where to get a key for it."""

    name: str
    key_url: str = ""


class AICredentialTest(BaseModel):
    """A provider/key pair to try before committing it to the account.

    `api_key` empty means "test what is already stored", so a user can re-check
    a key they cannot read back.
    """

    provider: str = Field(default="", max_length=30)
    api_key: str = Field(default="", max_length=400)


class AICredentialResult(BaseModel):
    ok: bool
    provider: str
    model: str = ""
    detail: str = ""


@router.get("", response_model=UserSettingsRead)
async def read_settings(user: CurrentUser, session: SessionDep) -> UserSettingsRead:
    """Return the guardrails in force for this account."""
    user_settings = await user_service.get_or_create_settings(session, user)
    return UserSettingsRead.model_validate(user_settings)


@router.put("", response_model=UserSettingsRead)
async def update_settings(
    payload: UserSettingsUpdate, user: CurrentUser, session: SessionDep
) -> UserSettingsRead:
    """Update the guardrails.

    Only the fields present in the body change, and the merged result is validated:
    delay and working-hour ranges must stay consistent. Manual approval cannot be
    disabled while the deployment runs in assisted mode.

    `ai_api_key` is write-only. Sending it stores it encrypted; sending `""`
    clears it; omitting it leaves the stored one alone. Clearing `ai_provider`
    also drops the key, which then has no reader left.
    """
    user_settings = await user_service.update_settings(session, user, payload)
    return UserSettingsRead.model_validate(user_settings)


@router.get("/ai/providers", response_model=list[AIProviderOption])
async def list_ai_providers(user: CurrentUser) -> list[AIProviderOption]:
    """Providers this account may bring a key for.

    Local providers and custom endpoints are absent by design: they are a
    deployment decision, because on a hosted install "localhost" is the server
    and a user-supplied base URL is a request the server would make on their
    behalf.
    """
    return [
        AIProviderOption(name=name, key_url=ai_credentials.key_hint(name))
        for name in sorted(ai_credentials.USER_SELECTABLE_PROVIDERS)
    ]


@router.post("/ai/test", response_model=AICredentialResult)
@limiter.limit(settings.rate_limit_auth)
async def test_ai_credentials(
    request: Request,
    payload: AICredentialTest,
    user: CurrentUser,
    session: SessionDep,
) -> AICredentialResult:
    """Send one minimal request with these credentials and report what happened.

    Rate-limited like the auth routes: it is the one endpoint a user can point
    at an outside service on demand.

    A failure is a 200 with `ok: false`, not a 5xx — "your key was rejected" is
    an answer to the question asked, and the caller is a form, not a client that
    needs to distinguish an outage. Nothing is stored: testing a key and saving
    it are separate acts, and a key that fails should not end up on the account.
    """
    user_settings = await user_service.get_or_create_settings(session, user)

    provider = payload.provider.strip().lower()
    if provider:
        resolved = ai_credentials.for_account(
            provider, payload.api_key.strip(), model=user_settings.ai_model or ""
        )
        if not resolved.enabled and not payload.api_key.strip():
            # Testing a provider the account already stores a key for: fall back
            # to the stored one rather than asking the user to retype a secret
            # the UI is not allowed to show them.
            stored = ai_credentials.for_settings_row(user_settings)
            if stored.ai_provider == provider:
                resolved = stored
    else:
        resolved = ai_credentials.for_settings_row(user_settings)

    if not resolved.enabled:
        return AICredentialResult(
            ok=False, provider=resolved.ai_provider, detail=resolved.reason
        )

    client = get_ai_client(user_settings.ai_model or None, credentials=resolved)
    try:
        await client.probe()
    except AINotConfiguredError as exc:
        return AICredentialResult(ok=False, provider=resolved.ai_provider, detail=str(exc))
    except ProviderError as exc:
        # The provider's own words, which is what makes this useful: "invalid
        # api key", "model not found", "quota exceeded" are three different
        # fixes. The key itself is never part of that text.
        logger.info(
            "AI credential test failed.",
            extra={
                "action": "settings.ai_test",
                "status": "error",
                "user_id": user.id,
                "provider": resolved.ai_provider,
            },
        )
        return AICredentialResult(ok=False, provider=resolved.ai_provider, detail=str(exc))
    finally:
        await client.aclose()

    logger.info(
        "AI credential test succeeded.",
        extra={
            "action": "settings.ai_test",
            "status": "ok",
            "user_id": user.id,
            "provider": resolved.ai_provider,
        },
    )
    return AICredentialResult(ok=True, provider=resolved.ai_provider, model=client.model)
