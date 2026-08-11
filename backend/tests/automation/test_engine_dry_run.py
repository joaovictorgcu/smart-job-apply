"""The engine in dry-run mode, and where a live run is required to stop.

Two properties are being pinned down here:

* dry-run produces content and events but never drives the browser;
* a live run fills the form and stops — `submit()` is never reached without a
  separate, explicitly confirmed action.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.contracts import SearchFilters
from app.automation.errors import SecurityCheckpointError
from app.models import (
    Application,
    ApplicationStatus,
    AutomationRun,
    AutomationRunStatus,
    Job,
    JobStatus,
    UserSettings,
)
from tests import missing
from tests.automation import (
    ENGINE_MODULES,
    ENGINE_NAMES,
    AutomationEngine,
    build_engine,
    invoke,
    prepare_method,
    search_method,
)
from tests.fixtures.factories import create_job, create_search, create_user
from tests.fixtures.fake_ai import FakeAIClient
from tests.fixtures.fake_linkedin import FakeLinkedInService, make_postings

pytestmark = pytest.mark.xfail(
    AutomationEngine is None, reason=missing(ENGINE_NAMES[0], *ENGINE_MODULES)
)

FILTERS = SearchFilters(keywords="python backend", location="Remote", max_results=5)


async def set_dry_run(session: AsyncSession, user: Any, *, dry_run: bool) -> None:
    settings = (
        await session.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    ).scalar_one()
    settings.dry_run = dry_run
    await session.commit()


async def reload_run(session: AsyncSession, run: Any) -> AutomationRun:
    run_id = getattr(run, "id", run)
    return (
        await session.execute(select(AutomationRun).where(AutomationRun.id == run_id))
    ).scalar_one()


async def run_a_search(engine: Any, search: Any = None) -> Any:
    return await invoke(
        search_method(engine),
        ((FILTERS,), {"search": search}) if search is not None else ((FILTERS,), {}),
        ((FILTERS,), {}),
        ((), {"filters": FILTERS}),
    )


async def prepare(engine: Any, job_ids: list[int]) -> Any:
    return await invoke(
        prepare_method(engine), ((job_ids,), {}), ((), {"job_ids": job_ids})
    )


class TestSearch:
    async def test_persists_the_postings_it_finds(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="search@example.com")
        linkedin = FakeLinkedInService(postings=make_postings(3))
        engine = build_engine(session, user, linkedin, fake_ai)
        search = await create_search(session, user)

        run = await run_a_search(engine, search)

        jobs = (await session.execute(select(Job).where(Job.user_id == user.id))).scalars().all()
        assert len(jobs) == 3
        assert await reload_run(session, run) is not None

    async def test_never_opens_the_application_form(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        """Searching is a separate step from applying, always."""
        user = await create_user(session, email="search2@example.com")
        linkedin = FakeLinkedInService(postings=make_postings(3))
        engine = build_engine(session, user, linkedin, fake_ai)

        await run_a_search(engine)

        assert linkedin.call_count("open_easy_apply") == 0
        assert linkedin.submit_called is False

    async def test_a_checkpoint_blocks_the_run_instead_of_failing_it(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="blocked@example.com")
        linkedin = FakeLinkedInService(
            postings=make_postings(3),
            checkpoint_on="search_jobs",
            checkpoint_reason="Security verification detected.",
        )
        engine = build_engine(session, user, linkedin, fake_ai)

        try:
            run = await run_a_search(engine)
            run_id = getattr(run, "id", run)
        except SecurityCheckpointError:
            run_id = None

        runs = (
            (await session.execute(select(AutomationRun).where(AutomationRun.user_id == user.id)))
            .scalars()
            .all()
        )
        assert runs, "a run must be recorded even when it is blocked"
        blocked = next((r for r in runs if r.id == run_id), runs[-1])
        assert blocked.status is AutomationRunStatus.BLOCKED
        assert blocked.blocked_reason
        assert blocked.status is not AutomationRunStatus.FAILED

    async def test_stops_at_the_checkpoint_without_further_browser_calls(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="blocked2@example.com")
        linkedin = FakeLinkedInService(postings=make_postings(3), checkpoint_on="search_jobs")
        engine = build_engine(session, user, linkedin, fake_ai)

        try:
            await run_a_search(engine)
        except SecurityCheckpointError:
            pass

        # The checkpoint call itself is the last browser interaction, and nothing
        # is ever retried against it.
        assert linkedin.call_count("search_jobs") == 1
        assert linkedin.call_count("open_easy_apply") == 0
        assert linkedin.submit_called is False


class TestDryRunPrepare:
    async def test_never_drives_the_browser(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="dry@example.com", settings={"dry_run": True})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        linkedin = FakeLinkedInService()
        engine = build_engine(session, user, linkedin, fake_ai)

        await prepare(engine, [job.id])

        assert linkedin.call_count("open_easy_apply") == 0
        assert linkedin.call_count("fill_and_advance") == 0
        assert linkedin.submit_called is False

    async def test_still_produces_a_reviewable_draft(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="dry2@example.com", settings={"dry_run": True})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        engine = build_engine(session, user, FakeLinkedInService(), fake_ai)

        await prepare(engine, [job.id])

        application = (
            await session.execute(select(Application).where(Application.job_id == job.id))
        ).scalar_one()
        assert application.status is ApplicationStatus.AWAITING_REVIEW
        assert application.was_dry_run is True
        assert application.cover_letter

    async def test_the_ai_is_still_exercised(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        """Dry-run is about not touching LinkedIn, not about skipping the drafting."""
        user = await create_user(session, email="dry3@example.com", settings={"dry_run": True})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        engine = build_engine(session, user, FakeLinkedInService(), fake_ai)

        await prepare(engine, [job.id])

        assert fake_ai.calls, "the draft has to come from somewhere"


class TestLivePrepareStopsAtReview:
    async def test_fills_the_form_and_stops(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="live@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        linkedin = FakeLinkedInService()
        engine = build_engine(session, user, linkedin, fake_ai)

        await prepare(engine, [job.id])

        assert linkedin.call_count("open_easy_apply") == 1
        assert linkedin.call_count("fill_and_advance") == 1
        # The one call that must never happen without explicit approval.
        assert linkedin.submit_called is False

    async def test_leaves_the_application_awaiting_review(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        user = await create_user(session, email="live2@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        engine = build_engine(session, user, FakeLinkedInService(), fake_ai)

        await prepare(engine, [job.id])

        application = (
            await session.execute(select(Application).where(Application.job_id == job.id))
        ).scalar_one()
        assert application.status is ApplicationStatus.AWAITING_REVIEW
        assert application.submitted_at is None
        assert application.approved_at is None

    async def test_an_unanswerable_question_asks_for_a_human(
        self, session: AsyncSession, fake_ai: FakeAIClient
    ) -> None:
        from tests.fixtures.factories import make_form_question

        user = await create_user(session, email="live3@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        linkedin = FakeLinkedInService(
            unanswered=[make_form_question("q-clearance", "Do you hold a clearance?", "radio")]
        )
        engine = build_engine(session, user, linkedin, fake_ai)

        await prepare(engine, [job.id])

        application = (
            await session.execute(select(Application).where(Application.job_id == job.id))
        ).scalar_one()
        assert application.needs_human_input is True
        assert linkedin.submit_called is False
