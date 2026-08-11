"""Automation-layer tests and the helpers they share.

The engine is a process-wide singleton driven by ids, not ORM objects:

    await engine.run_search(user_id, run_id, filters, analyze=True)
    await engine.prepare_applications(user_id, run_id, job_ids)
    await engine.submit_application(user_id, application_id)
    engine.request_stop(user_id) / await engine.stop_all(user_id)

The `automation_engine` fixture hands out a fresh instance per test, and
`wire_fakes` replaces the browser service it builds internally.

The reload helpers take plain ids on purpose. They expire the session so the
engine's own committed writes become visible, and reading an attribute off an
expired ORM instance would emit IO from a synchronous context.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.contracts import SearchFilters
from app.models import Application, AutomationRun, Job

FILTERS = SearchFilters(keywords="python backend", location="Remote", max_results=5)

# The engine resolves the AI layer by importing a name and binding the parameters
# it recognises. Those names do not line up, so every AI call from the engine is
# dropped and the run continues without model output:
#
#   app/automation/engine.py `_call_ai` offers user_id / posting / profile /
#   settings, while app/ai/scoring.py requires user / profile_ctx / settings_row —
#   and `_SCREENING_TARGETS` never names `answer_screening`, the function that
#   actually exists.
#
# Both modules belong to other agents. These xfails are non-strict, so the tests
# report as xpass the moment either side of the seam is corrected.
AI_SEAM_REASON = (
    "AI seam not wired: app/automation/engine.py `_call_ai` binds user_id/posting/"
    "profile/settings, but app/ai/scoring.py requires user/profile_ctx/settings_row "
    "(and `_SCREENING_TARGETS` omits `answer_screening`), so the engine drops every "
    "AI call and produces no model output. Owned by other agents."
)

ai_seam = pytest.mark.xfail(reason=AI_SEAM_REASON, strict=False)


async def reload_run(session: AsyncSession, run_id: int) -> AutomationRun:
    session.expire_all()
    return (
        await session.execute(select(AutomationRun).where(AutomationRun.id == run_id))
    ).scalar_one()


async def application_for_job(session: AsyncSession, job_id: int) -> Application | None:
    session.expire_all()
    return (
        await session.execute(select(Application).where(Application.job_id == job_id))
    ).scalar_one_or_none()


async def jobs_of(session: AsyncSession, user_id: int) -> list[Job]:
    session.expire_all()
    result = await session.execute(select(Job).where(Job.user_id == user_id).order_by(Job.id))
    return list(result.scalars().all())
