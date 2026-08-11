"""The application lifecycle, from a scored job to a submitted application.

The path is deliberately interrupted: preparing stops at `AWAITING_REVIEW`, and
submitting is a separate call that only happens after an explicit approval. AI
trouble — a refusal, or an answer the model is not sure about — has to degrade into
"a human should look at this", never into a silent guess and never into a crash.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AIAnalysis,
    Application,
    ApplicationEvent,
    ApplicationEventType,
    ApplicationStatus,
    Job,
    JobStatus,
)
from app.observability.audit import record_event, to_live_event
from tests import missing
from tests.automation import (
    ENGINE_MODULES,
    ENGINE_NAMES,
    AutomationEngine,
    build_engine,
    invoke,
    prepare_method,
    submit_method,
)
from tests.fixtures.factories import create_application, create_job, create_user, make_form_question
from tests.fixtures.fake_ai import FakeAIClient
from tests.fixtures.fake_linkedin import FakeLinkedInService

engine_missing = pytest.mark.xfail(
    AutomationEngine is None, reason=missing(ENGINE_NAMES[0], *ENGINE_MODULES)
)


async def prepare(engine: Any, job_ids: list[int]) -> Any:
    return await invoke(prepare_method(engine), ((job_ids,), {}), ((), {"job_ids": job_ids}))


async def submit(engine: Any, application_id: int) -> Any:
    return await invoke(
        submit_method(engine),
        ((application_id,), {"confirmed": True}),
        ((application_id,), {"confirm": True}),
        ((application_id,), {}),
    )


async def application_for(session: AsyncSession, job: Job) -> Application:
    return (
        await session.execute(select(Application).where(Application.job_id == job.id))
    ).scalar_one()


async def events_for(session: AsyncSession, application: Application) -> list[ApplicationEvent]:
    result = await session.execute(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == application.id)
        .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
    )
    return list(result.scalars().all())


class TestAuditTrail:
    """Runs today: the audit helper is part of the finished core."""

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


@engine_missing
class TestPrepareStopsForReview:
    async def test_the_application_waits_for_a_human(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="flow1@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        linkedin = FakeLinkedInService()
        engine = build_engine(session, user, linkedin, fake_ai)

        await prepare(engine, [job.id])

        application = await application_for(session, job)
        assert application.status == ApplicationStatus.AWAITING_REVIEW
        assert application.approved_at is None
        assert application.submitted_at is None
        assert linkedin.submit_called is False

    async def test_the_draft_carries_the_generated_content(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="flow2@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        engine = build_engine(session, user, FakeLinkedInService(), fake_ai)

        await prepare(engine, [job.id])

        application = await application_for(session, job)
        assert application.cover_letter
        assert application.screening_answers

    async def test_the_preparation_is_written_to_the_audit_trail(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="flow3@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        engine = build_engine(session, user, FakeLinkedInService(), fake_ai)

        await prepare(engine, [job.id])

        application = await application_for(session, job)
        recorded = {event.event_type for event in await events_for(session, application)}
        assert ApplicationEventType.AWAITING_REVIEW in recorded


@engine_missing
class TestSubmitAfterApproval:
    async def test_an_approved_application_is_submitted_once(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="flow4@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.QUEUED, score=88)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )
        linkedin = FakeLinkedInService()
        engine = build_engine(session, user, linkedin, fake_ai)

        await submit(engine, application.id)

        await session.refresh(application)
        await session.refresh(job)
        assert application.status == ApplicationStatus.SUBMITTED
        assert application.submitted_at is not None
        assert job.status == JobStatus.APPLIED
        assert linkedin.submit_called is True
        assert linkedin.call_count("submit") == 1

    async def test_a_draft_application_is_not_submittable(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="flow5@example.com", settings={"dry_run": False})
        job = await create_job(session, user)
        application = await create_application(
            session, user, job, status=ApplicationStatus.DRAFT
        )
        linkedin = FakeLinkedInService()
        engine = build_engine(session, user, linkedin, fake_ai)

        with pytest.raises((RuntimeError, ValueError)):
            await submit(engine, application.id)

        assert linkedin.submit_called is False

    async def test_an_already_submitted_application_is_not_submitted_again(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="flow6@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.APPLIED)
        application = await create_application(
            session, user, job, status=ApplicationStatus.SUBMITTED
        )
        linkedin = FakeLinkedInService()
        engine = build_engine(session, user, linkedin, fake_ai)

        with pytest.raises((RuntimeError, ValueError)):
            await submit(engine, application.id)

        assert linkedin.submit_called is False


@engine_missing
class TestAIRefusalDegradesGracefully:
    async def test_a_refusal_asks_for_a_human_instead_of_raising(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="refuse1@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        linkedin = FakeLinkedInService()
        engine = build_engine(session, user, linkedin, FakeAIClient(refused=True))

        await prepare(engine, [job.id])

        application = await application_for(session, job)
        assert application.needs_human_input is True
        assert application.status in {
            ApplicationStatus.AWAITING_REVIEW,
            ApplicationStatus.DRAFT,
        }
        assert linkedin.submit_called is False

    async def test_the_refusal_is_recorded_for_audit(self, session: AsyncSession) -> None:
        user = await create_user(session, email="refuse2@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        engine = build_engine(session, user, FakeLinkedInService(), FakeAIClient(refused=True))

        await prepare(engine, [job.id])

        analyses = (
            (await session.execute(select(AIAnalysis).where(AIAnalysis.job_id == job.id)))
            .scalars()
            .all()
        )
        assert analyses, "a refusal still costs a call and must be recorded"
        assert any(analysis.was_refusal for analysis in analyses)


@engine_missing
class TestLowConfidenceForcesReview:
    async def test_a_low_confidence_answer_flags_the_application(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="lowconf1@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        linkedin = FakeLinkedInService(
            questions=[make_form_question("q-salary", "Expected salary?", "text")]
        )
        engine = build_engine(session, user, linkedin, FakeAIClient(low_confidence=True))

        await prepare(engine, [job.id])

        application = await application_for(session, job)
        assert application.needs_human_input is True
        assert linkedin.submit_called is False

    async def test_the_answer_itself_keeps_the_review_flag(self, session: AsyncSession) -> None:
        user = await create_user(session, email="lowconf2@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)
        linkedin = FakeLinkedInService(
            questions=[make_form_question("q-salary", "Expected salary?", "text")]
        )
        engine = build_engine(session, user, linkedin, FakeAIClient(low_confidence=True))

        await prepare(engine, [job.id])

        application = await application_for(session, job)
        assert application.screening_answers
        assert any(
            answer.get("needs_review") or answer.get("confidence") == "low"
            for answer in application.screening_answers
        )
