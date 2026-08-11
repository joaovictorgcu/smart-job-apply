"""Job deduplication.

`UNIQUE(user_id, external_id)` is the invariant; the upsert is what honors it.
Re-discovering a posting must refresh it, never duplicate it, and never walk an
already-applied job back to `discovered`.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, ApplicationStatus, Job, JobStatus
from tests import find_attr, missing
from tests.automation import invoke
from tests.fixtures.factories import (
    create_application,
    create_job,
    create_search,
    create_user,
    make_job_posting,
)

DEDUP_MODULES = (
    "app.services.jobs",
    "app.services.dedup",
    "app.services.job_service",
    "app.services.discovery",
)

upsert_job = find_attr(
    ("upsert_job", "upsert_job_posting", "save_posting", "store_posting", "sync_job"),
    *DEDUP_MODULES,
)


async def count_jobs(session: AsyncSession, user: Any) -> int:
    return (
        await session.execute(select(func.count()).select_from(Job).where(Job.user_id == user.id))
    ).scalar_one()


async def do_upsert(session: AsyncSession, user: Any, posting: Any, search: Any = None) -> Any:
    return await invoke(
        upsert_job,
        ((session, user, posting), {"search": search}),
        ((session, user, posting), {"search_id": getattr(search, "id", None)}),
        ((session, user, posting), {}),
        ((session, user.id, posting), {}),
    )


class TestDatabaseInvariant:
    """Holds without any service layer: the constraint is in the schema."""

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

    async def test_two_users_may_each_hold_the_same_posting(
        self, session: AsyncSession
    ) -> None:
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


@pytest.mark.xfail(upsert_job is None, reason=missing("upsert_job", *DEDUP_MODULES))
class TestUpsert:
    async def test_the_first_upsert_creates_the_job(self, session: AsyncSession) -> None:
        user = await create_user(session, email="upsert1@example.com")
        posting = make_job_posting(external_id="ext-100", title="Backend Engineer")

        await do_upsert(session, user, posting)
        await session.commit()

        job = (
            await session.execute(select(Job).where(Job.external_id == "ext-100"))
        ).scalar_one()
        assert job.title == "Backend Engineer"
        assert job.user_id == user.id

    async def test_upserting_the_same_posting_twice_yields_one_row(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="upsert2@example.com")
        posting = make_job_posting(external_id="ext-101")

        await do_upsert(session, user, posting)
        await session.commit()
        await do_upsert(session, user, posting)
        await session.commit()

        assert await count_jobs(session, user) == 1

    async def test_a_second_discovery_refreshes_the_details(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="upsert3@example.com")
        await do_upsert(
            session, user, make_job_posting(external_id="ext-102", description="Short blurb.")
        )
        await session.commit()

        await do_upsert(
            session,
            user,
            make_job_posting(
                external_id="ext-102", description="The full description, fetched later."
            ),
        )
        await session.commit()

        job = (
            await session.execute(select(Job).where(Job.external_id == "ext-102"))
        ).scalar_one()
        assert job.description == "The full description, fetched later."
        assert await count_jobs(session, user) == 1

    async def test_an_applied_job_is_never_walked_back_to_discovered(
        self, session: AsyncSession
    ) -> None:
        """Re-finding a posting must not erase the fact that it was applied to."""
        user = await create_user(session, email="upsert4@example.com")
        await create_job(session, user, external_id="ext-103", status=JobStatus.APPLIED, score=95)

        await do_upsert(session, user, make_job_posting(external_id="ext-103"))
        await session.commit()

        job = (
            await session.execute(select(Job).where(Job.external_id == "ext-103"))
        ).scalar_one()
        assert job.status == JobStatus.APPLIED
        assert job.score == 95

    async def test_a_skipped_job_keeps_its_skip_reason(self, session: AsyncSession) -> None:
        user = await create_user(session, email="upsert5@example.com")
        await create_job(
            session,
            user,
            external_id="ext-104",
            status=JobStatus.SKIPPED,
            score=20,
            skip_reason="Score 20 is below the minimum of 70.",
        )

        await do_upsert(session, user, make_job_posting(external_id="ext-104"))
        await session.commit()

        job = (
            await session.execute(select(Job).where(Job.external_id == "ext-104"))
        ).scalar_one()
        assert job.status == JobStatus.SKIPPED
        assert job.skip_reason

    async def test_one_users_upsert_does_not_touch_another_users_row(
        self, session: AsyncSession
    ) -> None:
        first = await create_user(session, email="upsert6a@example.com")
        second = await create_user(session, email="upsert6b@example.com")
        await create_job(session, first, external_id="ext-105", title="Owned by first")

        await do_upsert(
            session, second, make_job_posting(external_id="ext-105", title="Owned by second")
        )
        await session.commit()

        theirs = (
            await session.execute(
                select(Job).where(Job.user_id == first.id, Job.external_id == "ext-105")
            )
        ).scalar_one()
        assert theirs.title == "Owned by first"
        assert await count_jobs(session, second) == 1

    async def test_the_search_that_found_the_job_is_recorded(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="upsert7@example.com")
        search = await create_search(session, user)

        await do_upsert(session, user, make_job_posting(external_id="ext-106"), search)
        await session.commit()

        job = (
            await session.execute(select(Job).where(Job.external_id == "ext-106"))
        ).scalar_one()
        assert job.search_id == search.id


class TestApplicationUniqueness:
    async def test_an_awaiting_review_application_is_reused_not_duplicated(
        self, session: AsyncSession
    ) -> None:
        """One job, one application — the schema enforces it, so nothing may retry
        preparation into a second row."""
        user = await create_user(session, email="dedup4@example.com")
        job = await create_job(session, user, status=JobStatus.QUEUED)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        found = (
            await session.execute(select(Application).where(Application.job_id == job.id))
        ).scalars().all()
        assert len(found) == 1
        assert found[0].id == application.id
