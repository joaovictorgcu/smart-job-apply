"""The user's row-level context: settings, throttle, resume and profile.

Everything the rest of the engine needs to know about *this* user before it
touches the browser or the AI layer, read fresh from the database each time so a
long run picks up a settings change.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.contracts import ProfileContext
from app.automation.engine.base import EngineBase
from app.automation.throttle import Throttle
from app.config import get_settings
from app.database.session import session_scope
from app.models import Profile, User, UserSettings
from app.services import resume_service


class ContextMixin(EngineBase):
    """Reads the per-user configuration the other phases run against."""

    @staticmethod
    async def _settings(session: AsyncSession, user_id: int) -> UserSettings | None:
        return await session.scalar(select(UserSettings).where(UserSettings.user_id == user_id))

    async def _throttle(self, user_id: int) -> Throttle:
        async with session_scope() as session:
            return Throttle(await self._settings(session, user_id))

    async def _resume_path(self, user_id: int) -> str | None:
        async with session_scope() as session:
            filename = await session.scalar(
                select(Profile.resume_filename).where(Profile.user_id == user_id)
            )
        if not filename:
            return None
        path = get_settings().resumes_dir / filename
        return str(path) if path.exists() else None

    async def _application_resume_path(self, user_id: int, application_id: int) -> str | None:
        """The file this one application should attach.

        The adapted document, drawn as a PDF, so the employer receives the
        resume the user reviewed rather than the one generic upload. Falls back
        to that upload whenever there is nothing honest to draw — no snapshot,
        or a renderer that refused — because a submission must never be blocked
        by a layout engine.
        """
        async with session_scope() as session:
            rendered = await resume_service.render_application_pdf(
                session, user_id, application_id
            )
        if rendered is not None:
            return str(rendered)
        return await self._resume_path(user_id)

    async def _profile_context(self, session: AsyncSession, user_id: int) -> ProfileContext:
        user = await session.get(User, user_id)
        profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
        resume_path = await self._resume_path(user_id) if profile else None
        return ProfileContext(
            full_name=user.full_name if user else None,
            email=user.email if user else None,
            headline=profile.headline if profile else None,
            location=profile.location if profile else None,
            phone=profile.phone if profile else None,
            years_of_experience=profile.years_of_experience if profile else None,
            summary=profile.summary if profile else None,
            resume_text=profile.resume_text if profile else None,
            resume_path=resume_path,
            skills=list(profile.skills or []) if profile else [],
            answer_bank=dict(profile.answer_bank or {}) if profile else {},
            preferred_languages=list(profile.preferred_languages or []) if profile else [],
        )
