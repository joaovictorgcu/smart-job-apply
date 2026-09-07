"""The score's history: one row per verdict, appended and never overwritten.

`jobs.score` is a column, so re-scoring after a profile edit destroys what the
previous pass concluded. `JobScore` is the record that survives it — which is what
makes "62 before you added Kubernetes, 81 after" a fact the app can show, and what
a calibration against real interview outcomes will be fitted on.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.scoring import analyze_job, profile_fingerprint
from app.models import AIAnalysis, JobScore, JobStatus
from tests.fixtures.factories import create_job, create_user, make_profile_context
from tests.fixtures.fake_ai import FakeAIClient


def settings_row(**overrides: Any) -> Any:
    """A plain object: `app.ai.scoring` only reads attributes off the settings."""
    values: dict[str, Any] = {"min_score": 70, "ai_model": None}
    values.update(overrides)
    return type("Settings", (), values)()


async def history(session: AsyncSession, job_id: int) -> list[JobScore]:
    """Every verdict recorded for a job, oldest first."""
    result = await session.execute(
        select(JobScore).where(JobScore.job_id == job_id).order_by(JobScore.id)
    )
    return list(result.scalars().all())


async def score_once(
    session: AsyncSession, user: Any, job: Any, client: FakeAIClient, **overrides: Any
) -> None:
    await analyze_job(
        session,
        user=user,
        job=job,
        profile_ctx=overrides.pop("profile_ctx", None) or make_profile_context(),
        settings_row=settings_row(**overrides),
        client=client,
    )


class TestEveryVerdictIsKept:
    async def test_a_second_scoring_appends_rather_than_replaces(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="history-append@example.com")
        job = await create_job(session, user)

        await score_once(session, user, job, FakeAIClient(score=62))
        await score_once(session, user, job, FakeAIClient(score=81))

        rows = await history(session, job.id)
        assert [row.overall for row in rows] == [62, 81]

    async def test_the_job_still_carries_the_latest_score(self, session: AsyncSession) -> None:
        """The denormalised column is what listing and ordering read; it must move."""
        user = await create_user(session, email="history-latest@example.com")
        job = await create_job(session, user)

        await score_once(session, user, job, FakeAIClient(score=62))
        await score_once(session, user, job, FakeAIClient(score=81))

        assert job.score == 81
        assert job.status == JobStatus.ANALYZED

    async def test_the_row_records_what_produced_the_number(self, session: AsyncSession) -> None:
        user = await create_user(session, email="history-detail@example.com")
        job = await create_job(session, user)
        profile = make_profile_context()

        await score_once(session, user, job, FakeAIClient(score=88), profile_ctx=profile)

        row = (await history(session, job.id))[0]
        assert row.user_id == user.id
        assert row.overall == 88
        assert row.verdict == "strong"
        assert [item["dimension"] for item in row.dimensions] == ["skills", "experience"]
        assert [item["gate"] for item in row.gates] == ["eligibility", "language"]
        assert row.model == "claude-opus-5"
        assert row.depth == "deep"
        assert row.profile_fingerprint == profile_fingerprint(profile)

    async def test_a_profile_edit_is_visible_as_a_different_fingerprint(
        self, session: AsyncSession
    ) -> None:
        """The attribution the history exists for: same job, different profile."""
        user = await create_user(session, email="history-fingerprint@example.com")
        job = await create_job(session, user)

        await score_once(session, user, job, FakeAIClient(score=62))
        await score_once(
            session,
            user,
            job,
            FakeAIClient(score=81),
            profile_ctx=make_profile_context(skills=["Python", "Kubernetes"]),
        )

        before, after = await history(session, job.id)
        assert before.profile_fingerprint != after.profile_fingerprint

    async def test_a_skipped_job_still_records_its_verdict(self, session: AsyncSession) -> None:
        """Below the threshold is a verdict too — and the one calibration needs most."""
        user = await create_user(session, email="history-skipped@example.com")
        job = await create_job(session, user)

        await score_once(session, user, job, FakeAIClient(score=40), min_score=80)

        assert job.status == JobStatus.SKIPPED
        row = (await history(session, job.id))[0]
        assert (row.overall, row.verdict) == (40, "weak")


class TestNoVerdictMeansNoRow:
    async def test_a_refusal_appends_nothing(self, session: AsyncSession) -> None:
        """There is no verdict to record — but the call itself is still audited."""
        user = await create_user(session, email="history-refusal@example.com")
        job = await create_job(session, user)

        await score_once(session, user, job, FakeAIClient(refused=True))

        assert await history(session, job.id) == []
        audited = await session.execute(select(AIAnalysis).where(AIAnalysis.job_id == job.id))
        assert len(list(audited.scalars().all())) == 1

    async def test_an_api_failure_appends_nothing(self, session: AsyncSession) -> None:
        user = await create_user(session, email="history-failure@example.com")
        job = await create_job(session, user)

        await score_once(session, user, job, FakeAIClient(api_error=True))

        assert await history(session, job.id) == []
