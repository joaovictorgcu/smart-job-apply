"""The kill switch.

`stop_all` is cooperative: it flips `stop_requested` and the engine notices between
steps. The run then has to end as `STOPPED` — not `FAILED`, because the user asking
to stop is not an error — and nothing may touch the browser afterwards.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.contracts import SearchFilters
from app.automation.errors import StopRequestedError
from app.models import AutomationRun, AutomationRunKind, AutomationRunStatus, Job, JobStatus
from tests import missing
from tests.automation import (
    ENGINE_MODULES,
    ENGINE_NAMES,
    AutomationEngine,
    build_engine,
    invoke,
    prepare_method,
    search_method,
    stop_method,
)
from tests.fixtures.factories import create_job, create_run, create_user
from tests.fixtures.fake_ai import FakeAIClient
from tests.fixtures.fake_linkedin import FakeLinkedInService, make_postings

pytestmark = pytest.mark.xfail(
    AutomationEngine is None, reason=missing(ENGINE_NAMES[0], *ENGINE_MODULES)
)

FILTERS = SearchFilters(keywords="python backend", max_results=10)


async def stop_all(engine: Any) -> Any:
    return await invoke(stop_method(engine), ((), {}))


async def active_runs(session: AsyncSession, user: Any) -> list[AutomationRun]:
    result = await session.execute(select(AutomationRun).where(AutomationRun.user_id == user.id))
    return list(result.scalars().all())


class TestStopRequestFlag:
    async def test_flips_stop_requested_on_a_running_run(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="kill1@example.com")
        run = await create_run(
            session, user, kind=AutomationRunKind.SEARCH, status=AutomationRunStatus.RUNNING
        )
        engine = build_engine(session, user, FakeLinkedInService(), fake_ai)

        await stop_all(engine)

        await session.refresh(run)
        assert run.stop_requested is True

    async def test_leaves_a_finished_run_alone(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="kill2@example.com")
        done = await create_run(session, user, status=AutomationRunStatus.COMPLETED)
        engine = build_engine(session, user, FakeLinkedInService(), fake_ai)

        await stop_all(engine)

        await session.refresh(done)
        assert done.status == AutomationRunStatus.COMPLETED

    async def test_does_not_reach_into_another_users_runs(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="kill3@example.com")
        stranger = await create_user(session, email="stranger@example.com")
        theirs = await create_run(session, stranger, status=AutomationRunStatus.RUNNING)
        engine = build_engine(session, user, FakeLinkedInService(), fake_ai)

        await stop_all(engine)

        await session.refresh(theirs)
        assert theirs.stop_requested is False


class TestRunEndsStopped:
    async def test_a_search_stopped_mid_flight_ends_stopped_not_failed(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="kill4@example.com")
        linkedin = FakeLinkedInService(postings=make_postings(8))
        engine = build_engine(session, user, linkedin, fake_ai)

        # Stop is requested as soon as the browser hands back the first result set.
        original_search = linkedin.search_jobs

        async def search_then_stop(filters: SearchFilters) -> Any:
            postings = await original_search(filters)
            await stop_all(engine)
            return postings

        linkedin.search_jobs = search_then_stop  # type: ignore[method-assign]

        try:
            await invoke(search_method(engine), ((FILTERS,), {}), ((), {"filters": FILTERS}))
        except StopRequestedError:
            pass

        runs = await active_runs(session, user)
        assert runs, "the stopped run must still be recorded"
        for run in runs:
            await session.refresh(run)
        assert any(run.status == AutomationRunStatus.STOPPED for run in runs), [
            run.status for run in runs
        ]
        assert all(run.status != AutomationRunStatus.FAILED for run in runs)

    async def test_no_browser_call_happens_after_the_stop(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="kill5@example.com")
        linkedin = FakeLinkedInService(postings=make_postings(8))
        engine = build_engine(session, user, linkedin, fake_ai)

        original_search = linkedin.search_jobs

        async def search_then_stop(filters: SearchFilters) -> Any:
            postings = await original_search(filters)
            await stop_all(engine)
            return postings

        linkedin.search_jobs = search_then_stop  # type: ignore[method-assign]

        try:
            await invoke(search_method(engine), ((FILTERS,), {}), ((), {"filters": FILTERS}))
        except StopRequestedError:
            pass

        after_stop = linkedin.browser_calls[linkedin.browser_calls.index("search_jobs") + 1 :]
        assert after_stop == [], after_stop

    async def test_a_stopped_prepare_never_submits(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="kill6@example.com", settings={"dry_run": False})
        jobs = [
            await create_job(session, user, status=JobStatus.ANALYZED, score=90) for _ in range(4)
        ]
        linkedin = FakeLinkedInService()
        engine = build_engine(session, user, linkedin, fake_ai)

        original_open = linkedin.open_easy_apply

        async def open_then_stop(external_id: str) -> Any:
            questions = await original_open(external_id)
            await stop_all(engine)
            return questions

        linkedin.open_easy_apply = open_then_stop  # type: ignore[method-assign]

        try:
            await invoke(
                prepare_method(engine),
                (([job.id for job in jobs],), {}),
                ((), {"job_ids": [job.id for job in jobs]}),
            )
        except StopRequestedError:
            pass

        assert linkedin.submit_called is False
        # It stops after the job it was already inside, not after all four.
        assert linkedin.call_count("open_easy_apply") < len(jobs)


class TestStopIsIdempotent:
    async def test_stopping_twice_is_harmless(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="kill7@example.com")
        run = await create_run(session, user, status=AutomationRunStatus.RUNNING)
        engine = build_engine(session, user, FakeLinkedInService(), fake_ai)

        await stop_all(engine)
        await stop_all(engine)

        await session.refresh(run)
        assert run.stop_requested is True

    async def test_stopping_with_nothing_running_is_harmless(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="kill8@example.com")
        engine = build_engine(session, user, FakeLinkedInService(), fake_ai)

        await stop_all(engine)

        assert await active_runs(session, user) == []
