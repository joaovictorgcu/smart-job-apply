"""The engine in dry-run mode, and where a live run is required to stop.

Two properties are pinned down here:

* dry-run produces content and events but never drives the browser;
* a live prepare reads the form and closes it — nothing is typed in and
  `submit()` is never reached without a separate, explicitly confirmed action.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient
from app.automation.contracts import FormQuestion, LinkedInService
from app.automation.errors import AutomationError
from app.automation.linkedin.service import LinkedInBrowserService
from app.models import (
    ApplicationEventType,
    ApplicationStatus,
    AutomationRunKind,
    AutomationRunStatus,
    JobStatus,
    UserSettings,
)
from tests.automation import FILTERS, application_for_job, jobs_of, reload_run
from tests.fixtures.factories import (
    create_job,
    create_resume_history,
    create_run,
    create_search,
    create_user,
)
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
    async def test_reads_the_form_and_closes_it_without_typing_anything(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """Preparing is an inspection pass; the answers are typed in after approval."""
        user = await create_user(session, email="live1@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        assert fake_linkedin.call_count("open_easy_apply") == 1
        assert fake_linkedin.call_count("fill_and_advance") == 0
        assert fake_linkedin.call_count("discard") == 1
        # The one call that must never happen without explicit approval.
        assert fake_linkedin.submit_called is False

    async def test_it_leaves_no_form_open_in_the_browser(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """The draft lives in the database, not in a tab that the next job replaces."""
        user = await create_user(session, email="live8@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        assert fake_linkedin.has_open_draft() is False

    async def test_it_records_the_shape_of_the_form_the_user_reviews(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        """Without this, submitting cannot tell the reviewed form from a new one."""
        user = await create_user(session, email="live9@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.form_fingerprint
        assert len(application.form_fingerprint) == 64

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
        self,
        session: AsyncSession,
        automation_engine: Any,
        fake_linkedin: FakeLinkedInService,
        fake_ai: FakeAIClient,
    ) -> None:
        """A required field neither the model nor the profile can fill stops here."""
        from tests.fixtures.factories import make_form_question

        user = await create_user(session, email="live4@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)
        fake_ai.answer_value = ""
        fake_linkedin.questions = [
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

        failed = await application_for_job(session, blocked_id)
        assert failed is not None
        assert failed.status == ApplicationStatus.FAILED
        assert failed.error_message
        # The rest of the batch still ran, and the run is not a failure.
        prepared = await application_for_job(session, usable_id)
        assert prepared is not None
        assert prepared.status == ApplicationStatus.AWAITING_REVIEW
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

        application = await application_for_job(session, job_id)
        assert application is not None
        assert application.status == ApplicationStatus.FAILED
        assert application.error_message
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

    async def test_an_application_with_no_recorded_form_is_refused(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """Nothing is typed in blind.

        A draft the engine never fingerprinted cannot be shown to be the one the
        user reviewed, so the form it re-opens is treated as an unknown form.
        """
        from app.database.base import utcnow
        from tests.fixtures.factories import create_application

        user = await create_user(session, email="submit3@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.QUEUED, score=90)
        application = await create_application(
            session,
            user,
            job,
            status=ApplicationStatus.AWAITING_REVIEW,
            approved_at=utcnow(),
            form_fingerprint=None,
        )

        with pytest.raises(AutomationError, match="Nothing was submitted"):
            await automation_engine.submit_application(user.id, application.id)

        assert fake_linkedin.submit_called is False
        assert fake_linkedin.call_count("fill_and_advance") == 0
        reverted = await application_for_job(session, job.id)
        assert reverted is not None
        assert reverted.status == ApplicationStatus.AWAITING_REVIEW


class TestBatchPreparingPacesItself:
    """Preparing opens the real form, so a batch has to be spaced like one.

    The pacing is the only thing standing between a fifty-job batch and fifty
    form openings seconds apart, which is the burst pattern that gets an account
    looked at. `sleep_spy` records the durations without waiting for them, so
    this asserts the schedule rather than the wall clock.
    """

    # The test factory zeroes every delay so the suite does not wait, which
    # would make both ranges indistinguishable at 0.0. These are set apart by an
    # order of magnitude on purpose: a recorded duration inside APPLY_RANGE came
    # from `wait_between_applications` and from nothing else.
    ACTION_RANGE = (0.5, 1.0)
    APPLY_RANGE = (40.0, 90.0)

    @classmethod
    def _long_pauses(cls, recorded: list[float]) -> list[float]:
        low, high = cls.APPLY_RANGE
        return [delay for delay in recorded if low <= delay <= high]

    @classmethod
    async def _paced_user(cls, session: AsyncSession) -> Any:
        user = await create_user(session)
        rows = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        row = rows.scalar_one()
        row.action_delay_min, row.action_delay_max = cls.ACTION_RANGE
        row.apply_delay_min, row.apply_delay_max = cls.APPLY_RANGE
        await session.flush()
        return user

    @staticmethod
    async def _preparable(session: AsyncSession, user: Any, count: int) -> list[Any]:
        return [
            await create_job(
                session,
                user,
                external_id=f"pace-{index}",
                status=JobStatus.ANALYZED,
                score=90,
            )
            for index in range(count)
        ]

    async def test_it_waits_the_between_applications_interval_between_jobs(
        self, session: AsyncSession, automation_engine: Any, sleep_spy: list[float]
    ) -> None:
        user = await self._paced_user(session)
        jobs = await self._preparable(session, user, 3)
        run = await prepare_run(session, user)

        sleep_spy.clear()
        await automation_engine.prepare_applications(user.id, run.id, [job.id for job in jobs])

        # Two gaps for three jobs: the pause separates two form openings, so
        # the last job is not followed by one.
        assert len(self._long_pauses(sleep_spy)) == 2, sorted(sleep_spy)

    async def test_it_does_not_pause_after_the_last_job(
        self, session: AsyncSession, automation_engine: Any, sleep_spy: list[float]
    ) -> None:
        user = await self._paced_user(session)
        jobs = await self._preparable(session, user, 1)
        run = await prepare_run(session, user)

        sleep_spy.clear()
        await automation_engine.prepare_applications(user.id, run.id, [jobs[0].id])

        assert self._long_pauses(sleep_spy) == []

    async def test_every_pause_is_randomised_rather_than_fixed(
        self, session: AsyncSession, automation_engine: Any, sleep_spy: list[float]
    ) -> None:
        """A constant interval is itself a fingerprint."""
        user = await self._paced_user(session)
        jobs = await self._preparable(session, user, 6)
        run = await prepare_run(session, user)

        sleep_spy.clear()
        await automation_engine.prepare_applications(user.id, run.id, [job.id for job in jobs])

        pauses = self._long_pauses(sleep_spy)
        assert len(pauses) == 5, sorted(sleep_spy)
        assert len(set(pauses)) > 1, "the interval must vary, not repeat"


class TestTheCoverLetterBoxDoesNotBlockApproval:
    """The regression this guards is a gate that fires on every posting.

    Most Easy Apply forms have a free-text box for a letter. Asked as a
    screening question it comes back flagged, `needs_human_input` goes true, and
    "Aprovar e enviar" is disabled — for a field the cover-letter path had
    already filled. A gate that always fires is a gate nobody reads.

    These run with dry_run off on purpose: in a dry run the form is never
    opened, so there are no questions and the bug cannot appear.
    """

    COVER_LETTER = FormQuestion(
        field_id="textarea-cover-letter",
        label="Cover letter",
        kind="textarea",
    )
    ANSWERABLE = FormQuestion(
        field_id="numeric-years",
        label="Years of Python experience?",
        kind="number",
        required=True,
    )

    @staticmethod
    async def _prepared(
        session: AsyncSession,
        engine: Any,
        fake_linkedin: FakeLinkedInService,
        email: str,
        questions: list[FormQuestion],
    ) -> Any:
        user = await create_user(session, email=email, settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)
        fake_linkedin.questions = questions

        await engine.prepare_applications(user.id, run.id, [job.id])
        return await application_for_job(session, job.id)

    async def test_a_form_with_a_cover_letter_box_stays_approvable(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        application = await self._prepared(
            session,
            automation_engine,
            fake_linkedin,
            "cover1@example.com",
            [self.ANSWERABLE, self.COVER_LETTER],
        )

        assert application is not None
        assert application.status == ApplicationStatus.AWAITING_REVIEW
        assert application.needs_human_input is False, (
            "the cover-letter box must not count as an unanswered question: "
            f"{application.screening_answers}"
        )

    async def test_the_box_is_not_recorded_as_a_screening_answer(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        application = await self._prepared(
            session,
            automation_engine,
            fake_linkedin,
            "cover2@example.com",
            [self.ANSWERABLE, self.COVER_LETTER],
        )

        assert application is not None
        labels = {entry["question"] for entry in application.screening_answers}
        # The real question is still recorded; only the letter box drops out.
        assert "Years of Python experience?" in labels
        assert "Cover letter" not in labels

    async def test_a_flagged_answer_still_blocks_approval(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService,
        fake_ai: FakeAIClient,
    ) -> None:
        """The gate has to keep firing for the case it exists for."""
        fake_ai.low_confidence = True

        application = await self._prepared(
            session,
            automation_engine,
            fake_linkedin,
            "cover3@example.com",
            [self.ANSWERABLE, self.COVER_LETTER],
        )

        assert application is not None
        assert application.needs_human_input is True


class TestTheFileTheFormAttaches:
    """The employer receives the resume the user reviewed, not the generic upload.

    Before this, every application attached `Profile.resume_filename` — one PDF
    for every posting — while the screen showed a document adapted to each. The
    gap between those two was the product's largest unkept promise.
    """

    @staticmethod
    async def _prepare(
        session: AsyncSession,
        engine: Any,
        fake_linkedin: FakeLinkedInService,
        email: str,
        **user_kwargs: Any,
    ) -> Any:
        user = await create_user(session, email=email, settings={"dry_run": False}, **user_kwargs)
        await create_resume_history(session, user)
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await engine.prepare_applications(user.id, run.id, [job.id])
        return user

    async def test_the_attached_file_is_this_application_s_own(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await self._prepare(session, automation_engine, fake_linkedin, "pdf1@example.com")

        assert fake_linkedin.resume_path is not None
        assert f"user_{user.id}_application_" in fake_linkedin.resume_path
        content = await asyncio.to_thread(Path(fake_linkedin.resume_path).read_bytes)
        assert content.startswith(b"%PDF")

    async def test_it_falls_back_to_the_upload_when_there_is_nothing_to_draw(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        # No profile at all, so no master resume, so no snapshot and nothing
        # honest to render. A submission must never be blocked by a layout
        # engine: the session's own configuration — the uploaded PDF, or none —
        # is what the form keeps.
        user = await create_user(
            session,
            email="pdf2@example.com",
            settings={"dry_run": False},
            with_profile=False,
        )
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        assert fake_linkedin.resume_path is None or "application_" not in fake_linkedin.resume_path

    async def test_configuring_the_file_does_not_drop_the_throttle(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        # The engine calls `configure(resume_path=...)` before every form. The
        # real service leaves an omitted throttle alone, and so must the fake.
        await self._prepare(session, automation_engine, fake_linkedin, "pdf3@example.com")

        assert fake_linkedin.throttle is not None
