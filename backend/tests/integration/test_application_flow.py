"""The application lifecycle, from a scored job to a submitted application.

The path is deliberately interrupted: preparing stops at `AWAITING_REVIEW`, and
submitting is a separate call that only runs after an approval recorded against
that one application. AI trouble — a refusal, or an answer the model is not sure
about — has to degrade into "a human should look at this", never into a silent
guess and never into a crash.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.models import (
    AIAnalysis,
    ApplicationEvent,
    ApplicationEventType,
    ApplicationStatus,
    AutomationRunKind,
    AutomationRunStatus,
    JobStatus,
)
from app.observability.audit import record_event, to_live_event
from tests.automation import ai_seam, application_for_job, reload_run
from tests.fixtures.factories import (
    create_application,
    create_job,
    create_run,
    create_user,
    make_form_question,
)
from tests.fixtures.fake_ai import FakeAIClient
from tests.fixtures.fake_linkedin import FakeLinkedInService


async def prepare_run(session: AsyncSession, user: Any) -> Any:
    return await create_run(
        session, user, kind=AutomationRunKind.PREPARE, status=AutomationRunStatus.PENDING
    )


async def events_for(session: AsyncSession, application_id: int) -> list[ApplicationEvent]:
    session.expire_all()
    result = await session.execute(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == application_id)
        .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
    )
    return list(result.scalars().all())


async def analyses_for(session: AsyncSession, job_id: int) -> list[AIAnalysis]:
    session.expire_all()
    result = await session.execute(select(AIAnalysis).where(AIAnalysis.job_id == job_id))
    return list(result.scalars().all())


class TestAuditTrail:
    async def test_records_an_event_and_mirrors_it_to_the_live_feed(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="audit1@example.com")
        job = await create_job(session, user)
        application = await create_application(session, user, job)

        event = await record_event(
            session,
            application_id=application.id,
            event_type=ApplicationEventType.AWAITING_REVIEW,
            message="Form filled, waiting for your approval.",
            payload={"unanswered": 0},
            user_id=user.id,
            job_id=job.id,
        )
        await session.commit()

        assert event.id is not None
        live = to_live_event(event, job_id=job.id)
        assert live is not None
        assert live.name == "application.awaiting_review"
        assert live.application_id == application.id
        assert live.level == "info"

    async def test_an_error_event_is_marked_as_an_error_in_the_feed(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="audit2@example.com")
        job = await create_job(session, user)
        application = await create_application(session, user, job)

        event = await record_event(
            session,
            application_id=application.id,
            event_type=ApplicationEventType.ERROR,
            message="The form changed shape.",
            is_error=True,
        )
        await session.commit()

        live = to_live_event(event)
        assert live is not None
        assert live.level == "error"

    async def test_an_internal_event_is_not_pushed_to_the_feed(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="audit3@example.com")
        job = await create_job(session, user)
        application = await create_application(session, user, job)

        event = await record_event(
            session,
            application_id=application.id,
            event_type=ApplicationEventType.QUESTION_ANSWERED,
            message="Answered: years of experience.",
        )
        await session.commit()

        assert to_live_event(event) is None


class TestPrepareThenSubmit:
    async def test_the_prepared_application_waits_for_a_human(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="flow1@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.status == ApplicationStatus.AWAITING_REVIEW
        assert application.approved_at is None
        assert application.submitted_at is None
        assert fake_linkedin.submit_called is False

    @ai_seam
    async def test_the_draft_carries_the_generated_content(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="flow2@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.cover_letter
        assert application.screening_answers

    async def test_an_approved_application_is_submitted_exactly_once(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="flow3@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)
        user_id, job_id = user.id, job.id
        await automation_engine.prepare_applications(user_id, run.id, [job_id])

        application = await application_for_job(session, job_id)
        assert application is not None
        # The approval the user gives on the review screen.
        application.approved_at = utcnow()
        await session.commit()
        application_id = application.id

        await automation_engine.submit_application(user_id, application_id)

        submitted = await application_for_job(session, job_id)
        assert submitted is not None
        assert submitted.status == ApplicationStatus.SUBMITTED
        assert submitted.submitted_at is not None
        assert fake_linkedin.call_count("submit") == 1

    async def test_submitting_marks_the_job_applied(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="flow4@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)
        user_id, job_id = user.id, job.id
        await automation_engine.prepare_applications(user_id, run.id, [job_id])
        application = await application_for_job(session, job_id)
        assert application is not None
        application.approved_at = utcnow()
        await session.commit()

        await automation_engine.submit_application(user_id, application.id)

        session.expire_all()
        await session.refresh(job)
        assert job.status == JobStatus.APPLIED

    async def test_the_whole_path_is_written_to_the_audit_trail(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="flow5@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)
        user_id, job_id = user.id, job.id
        await automation_engine.prepare_applications(user_id, run.id, [job_id])
        application = await application_for_job(session, job_id)
        assert application is not None
        application.approved_at = utcnow()
        await session.commit()
        application_id = application.id
        await automation_engine.submit_application(user_id, application_id)

        recorded = {event.event_type for event in await events_for(session, application_id)}
        assert ApplicationEventType.AWAITING_REVIEW in recorded
        assert ApplicationEventType.SUBMITTED in recorded

    async def test_the_prepare_run_reports_what_it_prepared(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="flow6@example.com", settings={"dry_run": False})
        jobs = [
            await create_job(session, user, status=JobStatus.ANALYZED, score=88) for _ in range(2)
        ]
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(
            user.id, run.id, [job.id for job in jobs]
        )

        stored = await reload_run(session, run.id)
        assert stored.status == AutomationRunStatus.COMPLETED
        assert stored.applications_prepared == 2


class TestAIRefusalDegradesGracefully:
    async def test_a_refusal_still_leaves_a_draft_for_a_human(
        self,
        session: AsyncSession,
        automation_engine: Any,
        fake_ai: FakeAIClient,
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        fake_ai.refused = True
        user = await create_user(session, email="refuse1@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.status == ApplicationStatus.AWAITING_REVIEW
        assert fake_linkedin.submit_called is False

    async def test_a_refusal_asks_for_a_human_instead_of_inventing_content(
        self, session: AsyncSession, automation_engine: Any, fake_ai: FakeAIClient
    ) -> None:
        fake_ai.refused = True
        user = await create_user(session, email="refuse2@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert not application.cover_letter
        assert application.needs_human_input is True

    @ai_seam
    async def test_the_refusal_is_recorded_for_audit(
        self, session: AsyncSession, automation_engine: Any, fake_ai: FakeAIClient
    ) -> None:
        fake_ai.refused = True
        user = await create_user(session, email="refuse3@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        rows = await analyses_for(session, job.id)
        assert rows, "a refusal still costs a call and must be recorded"
        assert any(row.was_refusal for row in rows)

    async def test_the_run_still_completes(
        self, session: AsyncSession, automation_engine: Any, fake_ai: FakeAIClient
    ) -> None:
        """An AI refusal is not an automation failure."""
        fake_ai.refused = True
        user = await create_user(session, email="refuse4@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        assert (await reload_run(session, run.id)).status == AutomationRunStatus.COMPLETED

    async def test_an_api_failure_also_degrades_to_a_reviewable_draft(
        self,
        session: AsyncSession,
        automation_engine: Any,
        fake_ai: FakeAIClient,
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        fake_ai.api_error = True
        user = await create_user(session, email="refuse5@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.needs_human_input is True
        assert fake_linkedin.submit_called is False


class TestLowConfidenceForcesReview:
    async def test_a_low_confidence_answer_flags_the_application(
        self,
        session: AsyncSession,
        automation_engine: Any,
        fake_ai: FakeAIClient,
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        fake_ai.low_confidence = True
        user = await create_user(session, email="lowconf1@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)
        fake_linkedin.questions = [
            make_form_question("q-llamas", "How many llamas do you own?", "number")
        ]

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.needs_human_input is True
        assert fake_linkedin.submit_called is False

    async def test_the_stored_answer_keeps_the_review_flag(
        self,
        session: AsyncSession,
        automation_engine: Any,
        fake_ai: FakeAIClient,
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        fake_ai.low_confidence = True
        user = await create_user(session, email="lowconf2@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)
        fake_linkedin.questions = [
            make_form_question("q-llamas", "How many llamas do you own?", "number")
        ]

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.screening_answers
        assert any(
            answer.get("needs_review") or answer.get("confidence") == "low"
            for answer in application.screening_answers
        )

    @ai_seam
    async def test_a_confident_answer_does_not_flag_the_application(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="lowconf3@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        run = await prepare_run(session, user)
        fake_linkedin.questions = [
            make_form_question("q-years", "Years of Python experience?", "number")
        ]

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.needs_human_input is False
