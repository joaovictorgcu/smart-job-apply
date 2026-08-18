"""The seam between the automation engine and the AI layer.

The engine used to reach into `app.ai` by importing a name at call time and
binding whichever keyword arguments happened to match, which meant a renamed
parameter degraded into "the AI simply never ran". `AIOrchestrator` replaces that
with a Protocol: one declared shape, checkable by a test and by a type checker.

`app.ai.scoring` is imported inside the methods rather than at module scope
because it pulls in the Anthropic SDK, which the rest of the app treats as
optional at import time (see `app.api.errors.register_exception_handlers`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.ai.schemas import CoverLetter, JobAnalysis, ScreeningAnswer
    from app.automation.contracts import FormQuestion, ProfileContext


@runtime_checkable
class AIOrchestrator(Protocol):
    """Persistence-aware AI operations the automation engine may invoke.

    Distinct from `AIClient`, which is the provider adapter: each method here owns
    an `AIAnalysis` audit row and, for scoring, the job's resulting status.
    """

    async def analyze_job(
        self,
        session: AsyncSession,
        *,
        user: Any,
        job: Any,
        profile_ctx: ProfileContext,
        settings_row: Any,
    ) -> JobAnalysis:
        """Score the job, and write its score, gates and resulting status."""
        ...

    async def generate_cover_letter(
        self,
        session: AsyncSession,
        *,
        user: Any,
        job: Any,
        profile_ctx: ProfileContext,
        settings_row: Any,
    ) -> CoverLetter | None:
        """Draft a letter, or `None` when it is disabled, refused or failed."""
        ...

    async def answer_screening(
        self,
        session: AsyncSession,
        *,
        user: Any,
        job: Any,
        profile_ctx: ProfileContext,
        questions: list[FormQuestion],
    ) -> list[ScreeningAnswer]:
        """Answer the form's questions, preferring the profile's answer bank."""
        ...


class ScoringOrchestrator:
    """`AIOrchestrator` backed by the module-level functions in `app.ai.scoring`.

    Deliberately nothing but a pass-through: the persistence, the audit rows and
    the degradation rules stay in one place, and this class exists only so the
    engine can depend on the Protocol instead of on import names.
    """

    async def analyze_job(
        self,
        session: AsyncSession,
        *,
        user: Any,
        job: Any,
        profile_ctx: ProfileContext,
        settings_row: Any,
    ) -> JobAnalysis:
        from app.ai import scoring

        return await scoring.analyze_job(
            session, user=user, job=job, profile_ctx=profile_ctx, settings_row=settings_row
        )

    async def generate_cover_letter(
        self,
        session: AsyncSession,
        *,
        user: Any,
        job: Any,
        profile_ctx: ProfileContext,
        settings_row: Any,
    ) -> CoverLetter | None:
        from app.ai import scoring

        return await scoring.generate_cover_letter(
            session, user=user, job=job, profile_ctx=profile_ctx, settings_row=settings_row
        )

    async def answer_screening(
        self,
        session: AsyncSession,
        *,
        user: Any,
        job: Any,
        profile_ctx: ProfileContext,
        questions: list[FormQuestion],
    ) -> list[ScreeningAnswer]:
        from app.ai import scoring

        return await scoring.answer_screening(
            session, user=user, job=job, profile_ctx=profile_ctx, questions=questions
        )


_orchestrator: AIOrchestrator | None = None


def get_orchestrator() -> AIOrchestrator:
    """The process-wide orchestrator, used unless a caller injects its own."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ScoringOrchestrator()
    return _orchestrator


__all__ = ["AIOrchestrator", "ScoringOrchestrator", "get_orchestrator"]
