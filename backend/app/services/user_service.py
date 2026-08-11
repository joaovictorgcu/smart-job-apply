"""Users, profile, settings, resume file and LinkedIn session metadata.

Every function is scoped to a single user. Nothing here commits: the request
session commits once, at the end of the request.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AuthenticationError, ConflictError, ValidationError
from app.auth.crypto import encrypt_json
from app.auth.security import hash_password, verify_password
from app.automation.contracts import ProfileContext
from app.config import get_settings
from app.database.base import utcnow
from app.models import LinkedInAccount, Profile, User, UserSettings
from app.observability import get_logger
from app.schemas.user import ProfileUpdate, UserSettingsUpdate

logger = get_logger(__name__)

MAX_RESUME_BYTES = 5 * 1024 * 1024
ALLOWED_RESUME_SUFFIXES = (".pdf", ".docx")


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.strip().lower()))
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


def _seed_settings(user_id: int) -> UserSettings:
    """Create the guardrails from the deployment defaults.

    `require_manual_approval` and `dry_run` always start enabled: a fresh account
    can never submit anything by accident.
    """
    config = get_settings()
    action_min, action_max = config.default_action_delay_range
    apply_min, apply_max = config.default_apply_delay_range
    hour_start, hour_end = config.default_working_hours
    return UserSettings(
        user_id=user_id,
        daily_cap=config.default_daily_cap,
        min_score=config.default_min_score,
        action_delay_min=action_min,
        action_delay_max=action_max,
        apply_delay_min=apply_min,
        apply_delay_max=apply_max,
        working_hour_start=hour_start,
        working_hour_end=hour_end,
        require_manual_approval=True,
        dry_run=True,
        ai_model=None,
        cover_letter_tone="professional",
        content_language="job",
        generate_cover_letter=True,
    )


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
) -> User:
    """Create a user with an empty profile and default guardrails."""
    normalized = email.strip().lower()
    if await get_by_email(session, normalized) is not None:
        raise ConflictError("An account with this email already exists.")

    try:
        hashed = hash_password(password)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    user = User(
        email=normalized,
        hashed_password=hashed,
        full_name=(full_name or "").strip() or None,
        is_active=True,
        is_admin=False,
    )
    session.add(user)
    await session.flush()

    session.add(Profile(user_id=user.id))
    session.add(_seed_settings(user.id))
    await session.flush()

    logger.info(
        "Account created.", extra={"action": "user.register", "status": "ok", "user_id": user.id}
    )
    return user


async def authenticate(session: AsyncSession, *, email: str, password: str) -> User:
    """Verify credentials and stamp the login time."""
    user = await get_by_email(session, email)
    if user is None or not verify_password(password, user.hashed_password):
        # Same message for unknown email and wrong password: no account enumeration.
        raise AuthenticationError("Invalid email or password.")
    if not user.is_active:
        raise AuthenticationError("This account is disabled.")

    user.last_login_at = utcnow()
    await session.flush()
    logger.info(
        "Login accepted.", extra={"action": "user.login", "status": "ok", "user_id": user.id}
    )
    return user


async def get_or_create_profile(session: AsyncSession, user: User) -> Profile:
    result = await session.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = Profile(user_id=user.id)
        session.add(profile)
        await session.flush()
    return profile


async def update_profile(session: AsyncSession, user: User, payload: ProfileUpdate) -> Profile:
    profile = await get_or_create_profile(session, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await session.flush()
    logger.info(
        "Profile updated.", extra={"action": "profile.update", "status": "ok", "user_id": user.id}
    )
    return profile


async def get_or_create_settings(session: AsyncSession, user: User) -> UserSettings:
    result = await session.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    user_settings = result.scalar_one_or_none()
    if user_settings is None:
        user_settings = _seed_settings(user.id)
        session.add(user_settings)
        await session.flush()
    return user_settings


async def update_settings(
    session: AsyncSession, user: User, payload: UserSettingsUpdate
) -> UserSettings:
    """Apply only the fields the client actually sent, then re-check invariants.

    A partial update can break a range that was valid before (for example raising
    `action_delay_min` above the stored `action_delay_max`), so the merged values
    are validated, not just the incoming ones.
    """
    user_settings = await get_or_create_settings(session, user)
    changes = payload.model_dump(exclude_unset=True)

    if changes.get("require_manual_approval") is False and get_settings().assisted_mode_only:
        raise ValidationError(
            "Manual approval cannot be disabled: this deployment runs in assisted mode only."
        )

    for field, value in changes.items():
        setattr(user_settings, field, value)

    if user_settings.action_delay_min > user_settings.action_delay_max:
        raise ValidationError("action_delay_min cannot be greater than action_delay_max.")
    if user_settings.apply_delay_min > user_settings.apply_delay_max:
        raise ValidationError("apply_delay_min cannot be greater than apply_delay_max.")
    if user_settings.working_hour_start >= user_settings.working_hour_end:
        raise ValidationError("working_hour_start must be smaller than working_hour_end.")

    await session.flush()
    logger.info(
        "Settings updated.",
        extra={
            "action": "settings.update",
            "status": "ok",
            "user_id": user.id,
            "fields": sorted(changes),
        },
    )
    return user_settings


def resume_path(filename: str) -> Path:
    """Absolute path of a stored resume (the name already carries the user id)."""
    return get_settings().resumes_dir / filename


# The extracted text is fed to the AI on every scoring call, so it is capped: past
# this point a resume is padding, and the tokens are paid for on each request.
MAX_EXTRACTED_RESUME_CHARS = 20_000


def _extract_resume_text(content: bytes, suffix: str) -> str | None:
    """Best-effort plain text from an uploaded resume.

    The stored file is what LinkedIn receives; this text is what the AI actually
    reads to score jobs and write cover letters. Extraction is therefore a
    convenience, never a requirement: a scanned (image-only) PDF legitimately
    yields nothing, and no failure here may block the upload.
    """
    try:
        if suffix == ".pdf":
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                # A password-protected resume cannot be read; the user pastes it.
                return None
            pages = (page.extract_text() or "" for page in reader.pages)
        elif suffix == ".docx":
            import docx  # python-docx, optional

            document = docx.Document(io.BytesIO(content))
            pages = (paragraph.text for paragraph in document.paragraphs)
        else:
            return None
    except ImportError:
        return None
    except Exception:
        # Corrupt file, unsupported encoding, parser bug — the upload still succeeded.
        return None

    text = "\n".join(part.strip() for part in pages if part and part.strip()).strip()
    if not text:
        return None
    return text[:MAX_EXTRACTED_RESUME_CHARS]


async def save_resume_file(
    session: AsyncSession, user: User, *, filename: str, content: bytes
) -> Profile:
    """Store the resume on disk under a per-user name and link it to the profile."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_RESUME_SUFFIXES:
        raise ValidationError("Only PDF and DOCX resumes are accepted.")
    if not content:
        raise ValidationError("The uploaded file is empty.")
    if len(content) > MAX_RESUME_BYTES:
        raise ValidationError("The resume must be 5 MB or smaller.")

    profile = await get_or_create_profile(session, user)
    stored_name = f"user_{user.id}_resume{suffix}"
    target = resume_path(stored_name)
    await asyncio.to_thread(target.write_bytes, content)

    previous = profile.resume_filename
    if previous and previous != stored_name:
        # A previous upload with another extension would otherwise linger on disk.
        await asyncio.to_thread(resume_path(previous).unlink, missing_ok=True)

    profile.resume_filename = stored_name

    # Pre-fill resume_text so the AI has something to reason about without the user
    # retyping the resume. Only when empty: text the user wrote or corrected is
    # theirs, and a re-upload must never silently discard it.
    extracted_chars = 0
    if not (profile.resume_text or "").strip():
        extracted = await asyncio.to_thread(_extract_resume_text, content, suffix)
        if extracted:
            profile.resume_text = extracted
            extracted_chars = len(extracted)

    await session.flush()
    logger.info(
        "Resume stored.",
        extra={
            "action": "profile.resume",
            "status": "ok",
            "user_id": user.id,
            "bytes": len(content),
            "extracted_chars": extracted_chars,
        },
    )
    return profile


async def build_profile_context(session: AsyncSession, user: User) -> ProfileContext:
    """Snapshot of the user for the AI and the form filler — no ORM objects leak."""
    profile = await get_or_create_profile(session, user)
    path: str | None = None
    if profile.resume_filename:
        candidate = resume_path(profile.resume_filename)
        path = str(candidate) if candidate.exists() else None
    return ProfileContext(
        full_name=user.full_name,
        email=user.email,
        headline=profile.headline,
        location=profile.location,
        phone=profile.phone,
        years_of_experience=profile.years_of_experience,
        summary=profile.summary,
        resume_text=profile.resume_text,
        resume_path=path,
        skills=list(profile.skills or []),
        answer_bank=dict(profile.answer_bank or {}),
        preferred_languages=list(profile.preferred_languages or []),
    )


async def get_linkedin_account(session: AsyncSession, user: User) -> LinkedInAccount | None:
    result = await session.execute(
        select(LinkedInAccount).where(LinkedInAccount.user_id == user.id)
    )
    return result.scalar_one_or_none()


async def upsert_linkedin_account(
    session: AsyncSession,
    user: User,
    *,
    display_name: str | None = None,
    storage_state: dict | None = None,
    browser_profile_dir: str | None = None,
    is_connected: bool | None = None,
) -> LinkedInAccount:
    """Persist LinkedIn session metadata; cookies are encrypted before they land.

    No LinkedIn password is ever accepted or stored — only the session state the
    browser produced after the user logged in manually.
    """
    account = await get_linkedin_account(session, user)
    if account is None:
        account = LinkedInAccount(user_id=user.id)
        session.add(account)

    if display_name is not None:
        account.display_name = display_name
    if browser_profile_dir is not None:
        account.browser_profile_dir = browser_profile_dir
    if storage_state is not None:
        account.encrypted_storage_state = encrypt_json(storage_state)
    if is_connected is not None:
        account.is_connected = is_connected
        if is_connected:
            account.last_verified_at = utcnow()

    await session.flush()
    return account
