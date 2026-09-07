"""What the engine does when the AI layer cannot answer.

`app.ai.scoring` already degrades on its own: an API error or a refusal becomes an
audit row and a refused result, never an exception. The one thing it deliberately
raises is `AINotConfiguredError`, which is a configuration fault the user has to
see. The engine used to wrap every AI call in a bare `except Exception` that
logged and returned `None`, so a broken seam looked exactly like a finished run.
It must not do that again.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AINotConfiguredError
from app.ai.port import AIOrchestrator
from app.ai.schemas import CoverLetter, JobAnalysis, ScreeningAnswer
from app.automation.contracts import FormQuestion
from app.models import AutomationRunKind, AutomationRunStatus, JobStatus
from tests.automation import FILTERS, jobs_of, reload_run
from tests.fixtures.factories import create_job, create_run, create_user
from tests.fixtures.fake_linkedin import FakeLinkedInService, make_postings

UNCONFIGURED = "AI features are not configured."


class UnconfiguredOrchestrator:
    """An `AIOrchestrator` for a deployment with no API key."""

    async def analyze_job(
        self,
        session: AsyncSession,
        *,
        user: Any,
        job: Any,
        profile_ctx: Any,
        settings_row: Any,
    ) -> JobAnalysis:
        raise AINotConfiguredError(UNCONFIGURED)

    async def generate_cover_letter(
        self,
        session: AsyncSession,
        *,
        user: Any,
        job: Any,
        profile_ctx: Any,
        settings_row: Any,
    ) -> CoverLetter | None:
        raise AINotConfiguredError(UNCONFIGURED)

    async def answer_screening(
        self,
        session: AsyncSession,
        *,
        user: Any,
        job: Any,
        profile_ctx: Any,
        questions: list[FormQuestion],
    ) -> list[ScreeningAnswer]:
        raise AINotConfiguredError(UNCONFIGURED)


@pytest.fixture
def unconfigured_ai(monkeypatch: pytest.MonkeyPatch, automation_engine: Any) -> Any:
    """Inject the fake into the engine the fixture built with no arguments."""
    orchestrator = UnconfiguredOrchestrator()
    monkeypatch.setattr(automation_engine, "_ai", orchestrator)
    return automation_engine


class TestTheFakeIsAFaithfulSubstitute:
    def test_it_satisfies_the_orchestrator_protocol(self) -> None:
        assert isinstance(UnconfiguredOrchestrator(), AIOrchestrator)


class TestAFailingAILayerIsNotSwallowed:
    async def test_a_search_surfaces_the_failure_instead_of_finishing(
        self, session: AsyncSession, unconfigured_ai: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="seam1@example.com")
        run = await create_run(
            session, user, kind=AutomationRunKind.SEARCH, status=AutomationRunStatus.PENDING
        )
        fake_linkedin.postings = make_postings(2)

        with pytest.raises(AINotConfiguredError):
            await unconfigured_ai.run_search(user.id, run.id, FILTERS, analyze=True)

        stored = await reload_run(session, run.id)
        assert stored.status == AutomationRunStatus.FAILED
        assert stored.error_message

    async def test_the_jobs_are_not_reported_as_analyzed(
        self, session: AsyncSession, unconfigured_ai: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """An unscored job must stay unscored, not pass as reviewed and skipped."""
        user = await create_user(session, email="seam2@example.com")
        run = await create_run(
            session, user, kind=AutomationRunKind.SEARCH, status=AutomationRunStatus.PENDING
        )
        fake_linkedin.postings = make_postings(1)

        with pytest.raises(AINotConfiguredError):
            await unconfigured_ai.run_search(user.id, run.id, FILTERS, analyze=True)

        jobs = await jobs_of(session, user.id)
        assert jobs
        assert all(job.status == JobStatus.DISCOVERED for job in jobs)
        assert all(job.score is None for job in jobs)
        assert (await reload_run(session, run.id)).jobs_analyzed == 0

    async def test_preparing_surfaces_the_failure_instead_of_a_contentless_draft(
        self, session: AsyncSession, unconfigured_ai: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="seam3@example.com", settings={"dry_run": True})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await create_run(
            session, user, kind=AutomationRunKind.PREPARE, status=AutomationRunStatus.PENDING
        )

        with pytest.raises(AINotConfiguredError):
            await unconfigured_ai.prepare_applications(user.id, run.id, [job.id])

        assert (await reload_run(session, run.id)).status == AutomationRunStatus.FAILED
        assert fake_linkedin.submit_called is False
