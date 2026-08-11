"""Dashboard metrics."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.stats import DashboardStats
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=DashboardStats)
async def read_stats(user: CurrentUser, session: SessionDep) -> DashboardStats:
    """Totals, score distribution, the last seven days and today's remaining quota."""
    return await stats_service.build_dashboard_stats(session, user)
