"""Dashboard metrics."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.stats import DashboardStats, OutcomeStats
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=DashboardStats)
async def read_stats(user: CurrentUser, session: SessionDep) -> DashboardStats:
    """Totals, score distribution, the last seven days and today's remaining quota."""
    return await stats_service.build_dashboard_stats(session, user)


@router.get("/outcomes", response_model=OutcomeStats)
async def read_outcome_stats(user: CurrentUser, session: SessionDep) -> OutcomeStats:
    """Interview rate by match-score band — whether a high score predicts interviews."""
    return await stats_service.build_outcome_stats(session, user)
