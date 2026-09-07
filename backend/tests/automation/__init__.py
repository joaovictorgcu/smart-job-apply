"""Automation-layer tests and the helpers they share.

The engine is a process-wide singleton driven by ids, not ORM objects:

    await engine.run_search(user_id, run_id, filters, analyze=True)
    await engine.prepare_applications(user_id, run_id, job_ids)
    await engine.submit_application(user_id, application_id)
    engine.request_stop(user_id) / await engine.stop_all(user_id)

The `automation_engine` fixture hands out a fresh instance per test, and
`wire_fakes` replaces the browser service it builds internally.

The engine commits through its own sessions, so the test's session has to be told
to re-read. The reload helpers do that with `populate_existing`, which refreshes
only the rows they return — expiring the whole session instead would leave every
other object in the test emitting IO from synchronous attribute access.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.contracts import SearchFilters
from app.models import Application, AutomationRun, Job

FILTERS = SearchFilters(keywords="python backend", location="Remote", max_results=5)


async def reload_run(session: AsyncSession, run_id: int) -> AutomationRun:
    return (
        await session.execute(
            select(AutomationRun)
            .where(AutomationRun.id == run_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def application_for_job(session: AsyncSession, job_id: int) -> Application | None:
    return (
        await session.execute(
            select(Application)
            .where(Application.job_id == job_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def jobs_of(session: AsyncSession, user_id: int) -> list[Job]:
    result = await session.execute(
        select(Job)
        .where(Job.user_id == user_id)
        .order_by(Job.id)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())
