"""Job deduplication.

`UNIQUE(user_id, external_id)` is the invariant; `upsert_job_from_posting` is what
honors it. Re-discovering a posting must refresh it, never duplicate it, and never
walk an already-applied job back to an earlier state.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, ApplicationStatus, Job, JobStatus
from app.services.job_service import upsert_job_from_posting
from tests.fixtures.factories import (
    create_application,
    create_job,
    create_search,
    create_user,
    make_job_posting,
)


async def count_jobs(session: AsyncSession, user: Any) -> int:
    return (
        await session.execute(select(func.count()).select_from(Job).where(Job.user_id == user.id))
    ).scalar_one()


async def job_by_external_id(session: AsyncSession, user: Any, external_id: str) -> Job:
    return (
        await session.execute(
            select(Job).where(Job.user_id == user.id, Job.external_id == external_id)
        )
    ).scalar_one()


class TestDatabaseInvariant:
    async def test_the_same_external_id_cannot_be_stored_twice_for_one_user(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="dedup1@example.com")
        await create_job(session, user, external_id="ext-shared")

        session.add(
            Job(user_id=user.id, external_id="ext-shared", title="Duplicate", company="Acme")
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_two_users_may_each_hold_the_same_posting(self, session: AsyncSession) -> None:
        first = await create_user(session, email="dedup2a@example.com")
        second = await create_user(session, email="dedup2b@example.com")

        await create_job(session, first, external_id="ext-shared")
        await create_job(session, second, external_id="ext-shared")

        assert await count_jobs(session, first) == 1
        assert await count_jobs(session, second) == 1

    async def test_a_job_carries_at_most_one_application(self, session: AsyncSession) -> None:
        user = await create_user(session, email="dedup3@example.com")
        job = await create_job(session, user)
        await create_application(session, user, job)

        session.add(Application(user_id=user.id, job_id=job.id))
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


class TestUpsert:
    async def test_the_first_upsert_creates_the_job(self, session: AsyncSession) -> None:
        user = await create_user(session, email="upsert1@example.com")

        job, created = await upsert_job_from_posting(
            session, user, make_job_posting(external_id="ext-100", title="Backend Engineer")
        )
        await session.commit()

        assert created is True
        assert job.title == "Backend Engineer"
        assert job.status == JobStatus.DISCOVERED

    async def test_upserting_the_same_posting_twice_yields_one_row(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="upsert2@example.com")
        posting = make_job_posting(external_id="ext-101")

        first, created_first = await upsert_job_from_posting(session, user, posting)
        await session.commit()
        second, created_second = await upsert_job_from_posting(session, user, posting)
        await session.commit()

        assert created_first is True
        assert created_second is False
        assert first.id == second.id
        assert await count_jobs(session, user) == 1

    async def test_a_second_discovery_refreshes_the_details(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="upsert3@example.com")
        await upsert_job_from_posting(
            session, user, make_job_posting(external_id="ext-102", description="Short blurb.")
        )
        await session.commit()

        await upsert_job_from_posting(
            session,
            user,
            make_job_posting(
                external_id="ext-102", description="The full description, fetched later."
            ),
        )
        await session.commit()

        job = await job_by_external_id(session, user, "ext-102")
        assert job.description == "The full description, fetched later."
        assert await count_jobs(session, user) == 1

    async def test_a_listing_without_a_description_does_not_erase_the_stored_one(
        self, session: AsyncSession
    ) -> None:
        """Search results are summaries; they must not overwrite a fetched detail page."""
        user = await create_user(session, email="upsert4@example.com")
        await upsert_job_from_posting(
            session, user, make_job_posting(external_id="ext-103", description="The full text.")
        )
        await session.commit()

        await upsert_job_from_posting(
            session, user, make_job_posting(external_id="ext-103", description=None)
        )
        await session.commit()

        job = await job_by_external_id(session, user, "ext-103")
        assert job.description == "The full text."

    async def test_an_applied_job_is_never_walked_back(self, session: AsyncSession) -> None:
        """Re-finding a posting must not erase the fact that it was applied to."""
        user = await create_user(session, email="upsert5@example.com")
        await create_job(session, user, external_id="ext-104", status=JobStatus.APPLIED, score=95)

        await upsert_job_from_posting(
            session, user, make_job_posting(external_id="ext-104")
        )
        await session.commit()

        job = await job_by_external_id(session, user, "ext-104")
        assert job.status == JobStatus.APPLIED
        assert job.score == 95
        assert await count_jobs(session, user) == 1

    async def test_a_skipped_job_keeps_its_status_and_reason(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="upsert6@example.com")
        await create_job(
            session,
            user,
            external_id="ext-105",
            status=JobStatus.SKIPPED,
            score=20,
            skip_reason="Score 20 is below the minimum of 70.",
        )

        await upsert_job_from_posting(session, user, make_job_posting(external_id="ext-105"))
        await session.commit()

        job = await job_by_external_id(session, user, "ext-105")
        assert job.status == JobStatus.SKIPPED
        assert job.skip_reason

    async def test_a_posting_linkedin_reports_as_applied_is_marked_applied(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="upsert7@example.com")

        await upsert_job_from_posting(
            session, user, make_job_posting(external_id="ext-106", already_applied=True)
        )
        await session.commit()

        job = await job_by_external_id(session, user, "ext-106")
        assert job.status == JobStatus.APPLIED

    async def test_one_users_upsert_does_not_touch_another_users_row(
        self, session: AsyncSession
    ) -> None:
        first = await create_user(session, email="upsert8a@example.com")
        second = await create_user(session, email="upsert8b@example.com")
        await create_job(session, first, external_id="ext-107", title="Owned by first")

        await upsert_job_from_posting(
            session, second, make_job_posting(external_id="ext-107", title="Owned by second")
        )
        await session.commit()

        theirs = await job_by_external_id(session, first, "ext-107")
        assert theirs.title == "Owned by first"
        assert await count_jobs(session, second) == 1

    async def test_the_search_that_found_the_job_is_recorded(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="upsert9@example.com")
        search = await create_search(session, user)

        job, _ = await upsert_job_from_posting(
            session, user, make_job_posting(external_id="ext-108"), search_id=search.id
        )
        await session.commit()

        assert job.search_id == search.id

    async def test_a_repeat_search_does_not_multiply_the_rows(
        self, session: AsyncSession
    ) -> None:
        """Running the same saved search twice is the normal case, not an error."""
        user = await create_user(session, email="upsert10@example.com")
        search = await create_search(session, user)
        postings = [make_job_posting(external_id=f"ext-2{index}") for index in range(5)]

        for _ in range(3):
            for posting in postings:
                await upsert_job_from_posting(session, user, posting, search_id=search.id)
            await session.commit()

        assert await count_jobs(session, user) == 5


class TestApplicationUniqueness:
    async def test_one_job_keeps_exactly_one_application(self, session: AsyncSession) -> None:
        user = await create_user(session, email="dedup4@example.com")
        job = await create_job(session, user, status=JobStatus.QUEUED)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        found = (
            (await session.execute(select(Application).where(Application.job_id == job.id)))
            .scalars()
            .all()
        )
        assert [row.id for row in found] == [application.id]
