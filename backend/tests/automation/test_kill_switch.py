"""The kill switch.

`request_stop` / `stop_all` are cooperative: they flip `stop_requested` and the
engine notices between steps. The run then has to end as `STOPPED` — not `FAILED`,
because a user asking to stop is not an error — and nothing may touch the browser
afterwards.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.contracts import SearchFilters
from app.models import AutomationRunKind, AutomationRunStatus, JobStatus
from tests.automation import FILTERS, application_for_job, reload_run
from tests.fixtures.factories import create_job, create_run, create_user
from tests.fixtures.fake_linkedin import FakeLinkedInService, make_postings


async def a_run(
    session: AsyncSession,
    user: Any,
    *,
    kind: AutomationRunKind = AutomationRunKind.SEARCH,
    status: AutomationRunStatus = AutomationRunStatus.PENDING,
) -> Any:
    return await create_run(session, user, kind=kind, status=status)


class TestStopRequestFlag:
    async def test_flips_stop_requested_on_a_running_run(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="kill1@example.com")
        run = await a_run(session, user, status=AutomationRunStatus.RUNNING)

        await automation_engine.stop_all(user.id)

        assert (await reload_run(session, run.id)).stop_requested is True

    async def test_flips_stop_requested_on_a_pending_run(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="kill2@example.com")
        run = await a_run(session, user, status=AutomationRunStatus.PENDING)

        await automation_engine.stop_all(user.id)

        assert (await reload_run(session, run.id)).stop_requested is True

    async def test_leaves_a_finished_run_alone(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="kill3@example.com")
        done = await a_run(session, user, status=AutomationRunStatus.COMPLETED)

        await automation_engine.stop_all(user.id)

        stored = await reload_run(session, done.id)
        assert stored.status == AutomationRunStatus.COMPLETED
        assert stored.stop_requested is False

    async def test_does_not_reach_into_another_users_runs(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="kill4@example.com")
        stranger = await create_user(session, email="kill4-other@example.com")
        theirs = await a_run(session, stranger, status=AutomationRunStatus.RUNNING)

        await automation_engine.stop_all(user.id)

        assert (await reload_run(session, theirs.id)).stop_requested is False

    async def test_stopping_twice_is_harmless(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="kill5@example.com")
        run = await a_run(session, user, status=AutomationRunStatus.RUNNING)

        await automation_engine.stop_all(user.id)
        await automation_engine.stop_all(user.id)

        assert (await reload_run(session, run.id)).stop_requested is True

    async def test_stopping_with_nothing_running_is_harmless(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        user = await create_user(session, email="kill6@example.com")

        await automation_engine.stop_all(user.id)


class TestRunEndsStopped:
    async def test_a_search_stopped_mid_flight_ends_stopped_not_failed(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="kill8@example.com")
        run = await a_run(session, user)
        fake_linkedin.postings = make_postings(8)

        original_search = fake_linkedin.search_jobs

        async def search_then_stop(filters: SearchFilters) -> Any:
            postings = await original_search(filters)
            automation_engine.request_stop(user.id)
            return postings

        fake_linkedin.search_jobs = search_then_stop  # type: ignore[method-assign]

        await automation_engine.run_search(user.id, run.id, FILTERS, analyze=True)

        stored = await reload_run(session, run.id)
        assert stored.status == AutomationRunStatus.STOPPED
        assert stored.status != AutomationRunStatus.FAILED
        assert stored.finished_at is not None

    async def test_no_browser_call_happens_after_the_stop(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="kill9@example.com")
        run = await a_run(session, user)
        fake_linkedin.postings = make_postings(8)

        original_search = fake_linkedin.search_jobs

        async def search_then_stop(filters: SearchFilters) -> Any:
            postings = await original_search(filters)
            automation_engine.request_stop(user.id)
            return postings

        fake_linkedin.search_jobs = search_then_stop  # type: ignore[method-assign]

        await automation_engine.run_search(user.id, run.id, FILTERS, analyze=True)

        after = fake_linkedin.browser_calls
        assert after[-1] == "search_jobs", after
        assert fake_linkedin.submit_called is False

    async def test_a_stopped_prepare_run_stops_early_and_never_submits(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="kill10@example.com", settings={"dry_run": False})
        jobs = [
            await create_job(session, user, status=JobStatus.ANALYZED, score=90) for _ in range(4)
        ]
        run = await a_run(session, user, kind=AutomationRunKind.PREPARE)

        original_open = fake_linkedin.open_easy_apply

        async def open_then_stop(external_id: str) -> Any:
            questions = await original_open(external_id)
            automation_engine.request_stop(user.id)
            return questions

        fake_linkedin.open_easy_apply = open_then_stop  # type: ignore[method-assign]

        await automation_engine.prepare_applications(
            user.id, run.id, [job.id for job in jobs]
        )

        assert fake_linkedin.submit_called is False
        # It finishes the job it was already inside, then stops — not all four.
        assert fake_linkedin.call_count("open_easy_apply") < len(jobs)
        assert (await reload_run(session, run.id)).status == AutomationRunStatus.STOPPED

    async def test_the_draft_already_prepared_before_the_stop_is_kept(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """Stopping must not throw away work the user can still review."""
        user = await create_user(session, email="kill11@example.com", settings={"dry_run": False})
        first = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        second = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await a_run(session, user, kind=AutomationRunKind.PREPARE)

        original_fill = fake_linkedin.fill_and_advance

        async def fill_then_stop(answers: Any, *, cover_letter: Any = None) -> Any:
            draft = await original_fill(answers, cover_letter=cover_letter)
            automation_engine.request_stop(user.id)
            return draft

        fake_linkedin.fill_and_advance = fill_then_stop  # type: ignore[method-assign]
        first_id, second_id = first.id, second.id

        await automation_engine.prepare_applications(user.id, run.id, [first_id, second_id])

        assert await application_for_job(session, first_id) is not None
        assert await application_for_job(session, second_id) is None
        assert fake_linkedin.submit_called is False


class TestStopIsRecorded:
    async def test_the_stopped_run_keeps_the_counters_it_earned(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        user = await create_user(session, email="kill12@example.com", settings={"dry_run": False})
        jobs = [
            await create_job(session, user, status=JobStatus.ANALYZED, score=90) for _ in range(3)
        ]
        run = await a_run(session, user, kind=AutomationRunKind.PREPARE)

        original_fill = fake_linkedin.fill_and_advance

        async def fill_then_stop(answers: Any, *, cover_letter: Any = None) -> Any:
            draft = await original_fill(answers, cover_letter=cover_letter)
            automation_engine.request_stop(user.id)
            return draft

        fake_linkedin.fill_and_advance = fill_then_stop  # type: ignore[method-assign]

        await automation_engine.prepare_applications(
            user.id, run.id, [job.id for job in jobs]
        )

        stored = await reload_run(session, run.id)
        assert stored.status == AutomationRunStatus.STOPPED
        assert stored.applications_prepared == 1
