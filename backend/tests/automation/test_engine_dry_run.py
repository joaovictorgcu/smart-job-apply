"""The engine in dry-run mode, and where a live run is required to stop.

Two properties are pinned down here:

* dry-run produces content and events but never drives the browser;
* a live run fills the form and stops — `submit()` is never reached without a
  separate, explicitly confirmed action.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient
from app.automation.contracts import LinkedInService
from app.automation.errors import AutomationError
from app.automation.linkedin.service import LinkedInBrowserService
from app.models import (
    ApplicationEventType,
    ApplicationStatus,
    AutomationRunKind,
    AutomationRunStatus,
    JobStatus,
)
from tests.automation import FILTERS, ai_seam, application_for_job, jobs_of, reload_run
from tests.fixtures.factories import create_job, create_run, create_search, create_user
from tests.fixtures.fake_ai import FakeAIClient
from tests.fixtures.fake_linkedin import FakeLinkedInService, make_postings


async def prepare_run(session: AsyncSession, user: Any) -> Any:
    return await create_run(
        session, user, kind=AutomationRunKind.PREPARE, status=AutomationRunStatus.PENDING
    )


class TestTheFakeIsAFaithfulSubstitute:
    """If the fake drifts from the boundary, every test below it proves nothing."""

    def test_it_satisfies_the_linkedin_service_protocol(self) -> None:
        assert isinstance(FakeLinkedInService(), LinkedInService)

    def test_it_implements_every_method_the_real_service_exposes(self) -> None:
        fake = FakeLinkedInService()
        required = {
            name
            for name in dir(LinkedInBrowserService)
            if not name.startswith("_") and callable(getattr(LinkedInBrowserService, name, None))
        }
        assert required <= {name for name in dir(fake) if callable(getattr(fake, name, None))}

    def test_it_matches_the_ai_clients_public_surface(self) -> None:
        fake = FakeAIClient()
        for name in ("score_job", "write_cover_letter", "answer_questions"):
            assert callable(getattr(fake, name))
            assert inspect.iscoroutinefunction(getattr(AIClient, name))
        assert fake.is_configured is True


async def search_run(session: AsyncSession, user: Any, search: Any = None) -> Any:
    return await create_run(
        session,
        user,
        kind=AutomationRunKind.SEARCH,
        status=AutomationRunStatus.PENDING,
        search_id=search.id if search is not None else None,
    )


class TestSearch:
    async def test_persists_the_postings_it_finds(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="search1@example.com")
        search = await create_search(session, user)
        run = await search_run(session, user, search)
        fake_linkedin.postings = make_postings(3)
        user_id = user.id

        await automation_engine.run_search(user_id, run.id, FILTERS, analyze=False)

        jobs = await jobs_of(session, user_id)
        assert len(jobs) == 3
        assert {job.external_id for job in jobs} == {"job-1", "job-2", "job-3"}

    async def test_completes_the_run_and_counts_what_it_found(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="search2@example.com")
        run = await search_run(session, user)
        fake_linkedin.postings = make_postings(2)

        await automation_engine.run_search(user.id, run.id, FILTERS, analyze=False)

        stored = await reload_run(session, run.id)
        assert stored.status == AutomationRunStatus.COMPLETED
        assert stored.jobs_found == 2
        assert stored.finished_at is not None

    @ai_seam
    async def test_scores_the_jobs_when_analysis_is_on(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="search3@example.com", settings={"min_score": 70})
        run = await search_run(session, user)
        fake_linkedin.postings = make_postings(2)

        await automation_engine.run_search(user.id, run.id, FILTERS, analyze=True)

        jobs = await jobs_of(session, user.id)
        assert jobs
        assert all(job.score == 85 for job in jobs)
        assert all(job.status == JobStatus.ANALYZED for job in jobs)

    @ai_seam
    async def test_a_weak_job_is_skipped_rather_than_queued(
        self,
        session: AsyncSession,
        automation_engine: Any,
        fake_linkedin: FakeLinkedInService,
        fake_ai: FakeAIClient,
    ) -> None:
        user = await create_user(session, email="search4@example.com", settings={"min_score": 90})
        run = await search_run(session, user)
        fake_linkedin.postings = make_postings(1)
        fake_ai.score = 30

        await automation_engine.run_search(user.id, run.id, FILTERS, analyze=True)

        jobs = await jobs_of(session, user.id)
        assert jobs
        assert jobs[0].status == JobStatus.SKIPPED
        assert jobs[0].skip_reason

    async def test_searching_never_opens_the_application_form(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """Searching is a separate step from applying, always."""
        user = await create_user(session, email="search5@example.com")
        run = await search_run(session, user)
        fake_linkedin.postings = make_postings(3)

        await automation_engine.run_search(user.id, run.id, FILTERS, analyze=True)

        assert fake_linkedin.call_count("open_easy_apply") == 0
        assert fake_linkedin.call_count("fill_and_advance") == 0
        assert fake_linkedin.submit_called is False


class TestCheckpointHaltsTheRun:
    async def test_a_checkpoint_blocks_the_run_instead_of_failing_it(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="blocked1@example.com")
        run = await search_run(session, user)
        fake_linkedin.checkpoint_on = "search_jobs"
        fake_linkedin.checkpoint_reason = "Security verification detected."

        await automation_engine.run_search(user.id, run.id, FILTERS, analyze=False)

        stored = await reload_run(session, run.id)
        assert stored.status == AutomationRunStatus.BLOCKED
        assert stored.blocked_reason
        assert stored.status != AutomationRunStatus.FAILED

    async def test_nothing_is_retried_against_the_checkpoint(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="blocked2@example.com")
        run = await search_run(session, user)
        fake_linkedin.checkpoint_on = "search_jobs"

        await automation_engine.run_search(user.id, run.id, FILTERS, analyze=False)

        assert fake_linkedin.call_count("search_jobs") == 1
        assert fake_linkedin.call_count("open_easy_apply") == 0
        assert fake_linkedin.submit_called is False

    async def test_a_checkpoint_while_preparing_blocks_the_run_and_never_submits(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(
            session, email="blocked3@example.com", settings={"dry_run": False}
        )
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)
        fake_linkedin.checkpoint_on = "open_easy_apply"

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        stored = await reload_run(session, run.id)
        assert stored.status == AutomationRunStatus.BLOCKED
        assert stored.blocked_reason
        assert fake_linkedin.submit_called is False


class TestDryRunPrepare:
    async def test_never_drives_the_browser(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="dry1@example.com", settings={"dry_run": True})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        assert fake_linkedin.call_count("open_easy_apply") == 0
        assert fake_linkedin.call_count("fill_and_advance") == 0
        assert fake_linkedin.submit_called is False
        assert fake_linkedin.browser_calls == []

    async def test_still_produces_a_reviewable_draft(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="dry2@example.com", settings={"dry_run": True})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.status == ApplicationStatus.AWAITING_REVIEW
        assert application.was_dry_run is True

    @ai_seam
    async def test_the_draft_carries_the_generated_content(
        self, session: AsyncSession, automation_engine: Any, fake_ai: FakeAIClient
    ) -> None:
        """Dry-run is about not touching LinkedIn, not about skipping the drafting."""
        user = await create_user(session, email="dry3@example.com", settings={"dry_run": True})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.cover_letter
        assert fake_ai.call_count("write_cover_letter") == 1

    async def test_the_run_completes_and_counts_the_draft(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="dry4@example.com", settings={"dry_run": True})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        stored = await reload_run(session, run.id)
        assert stored.status == AutomationRunStatus.COMPLETED
        assert stored.applications_prepared == 1


class TestLivePrepareStopsAtReview:
    async def test_fills_the_form_and_stops(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="live1@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        assert fake_linkedin.call_count("open_easy_apply") == 1
        assert fake_linkedin.call_count("fill_and_advance") == 1
        # The one call that must never happen without explicit approval.
        assert fake_linkedin.submit_called is False

    async def test_leaves_the_application_awaiting_review_and_unapproved(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="live2@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.status == ApplicationStatus.AWAITING_REVIEW
        assert application.approved_at is None
        assert application.submitted_at is None

    async def test_records_the_review_stop_in_the_audit_trail(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="live3@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        await session.refresh(application, ["events"])
        recorded = {event.event_type for event in application.events}
        assert ApplicationEventType.AWAITING_REVIEW in recorded

    async def test_an_unanswerable_question_asks_for_a_human(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        from tests.fixtures.factories import make_form_question

        user = await create_user(session, email="live4@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)
        fake_linkedin.unanswered = [
            make_form_question("q-clearance", "Do you hold a security clearance?", "radio")
        ]

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.needs_human_input is True
        assert fake_linkedin.submit_called is False

    async def test_a_job_without_easy_apply_is_skipped_without_failing_the_run(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """One unusable posting must not take the rest of the batch down with it."""
        user = await create_user(session, email="live6@example.com", settings={"dry_run": False})
        blocked = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        usable = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)
        fake_linkedin.no_easy_apply_ids = {blocked.external_id}
        blocked_id, usable_id = blocked.id, usable.id

        await automation_engine.prepare_applications(user.id, run.id, [blocked_id, usable_id])

        assert await application_for_job(session, blocked_id) is None
        assert await application_for_job(session, usable_id) is not None
        assert (await reload_run(session, run.id)).status == AutomationRunStatus.COMPLETED
        assert fake_linkedin.submit_called is False

    async def test_a_posting_linkedin_says_was_already_applied_to_is_skipped(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="live7@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)
        fake_linkedin.already_applied_ids = {job.external_id}
        job_id = job.id

        await automation_engine.prepare_applications(user.id, run.id, [job_id])

        assert await application_for_job(session, job_id) is None
        assert fake_linkedin.submit_called is False

    async def test_a_job_belonging_to_someone_else_is_refused(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="live5@example.com", settings={"dry_run": False})
        stranger = await create_user(session, email="live5-other@example.com")
        theirs = await create_job(session, stranger, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [theirs.id])

        assert await application_for_job(session, theirs.id) is None
        assert fake_linkedin.submit_called is False


class TestSubmitRequiresApproval:
    async def test_an_unapproved_application_is_never_submitted(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """Even the engine's own submit path refuses without a recorded approval."""
        from tests.fixtures.factories import create_application

        user = await create_user(session, email="submit1@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.QUEUED, score=90)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW, approved_at=None
        )

        with pytest.raises(AutomationError, match="approved"):
            await automation_engine.submit_application(user.id, application.id)

        assert fake_linkedin.submit_called is False

    async def test_a_dry_run_application_is_never_submitted(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        from app.database.base import utcnow
        from tests.fixtures.factories import create_application

        user = await create_user(session, email="submit2@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.QUEUED, score=90)
        application = await create_application(
            session,
            user,
            job,
            status=ApplicationStatus.AWAITING_REVIEW,
            approved_at=utcnow(),
            was_dry_run=True,
        )

        with pytest.raises(AutomationError, match="[Dd]ry run"):
            await automation_engine.submit_application(user.id, application.id)

        assert fake_linkedin.submit_called is False

    async def test_submitting_without_an_open_draft_is_refused(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """Nothing is clicked blind: the filled form has to still be on screen."""
        from app.database.base import utcnow
        from tests.fixtures.factories import create_application

        user = await create_user(session, email="submit3@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.QUEUED, score=90)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW, approved_at=utcnow()
        )
        fake_linkedin.current_external_id = None

        with pytest.raises(AutomationError, match="no longer open"):
            await automation_engine.submit_application(user.id, application.id)

        assert fake_linkedin.submit_called is False
        reverted = await application_for_job(session, job.id)
        assert reverted is not None
        assert reverted.status == ApplicationStatus.AWAITING_REVIEW
