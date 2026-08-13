"""Every router, aggregated into the single router that `main` mounts under /api."""

from fastapi import APIRouter

from app.api.routes import (
    ai,
    applications,
    auth,
    automation,
    health,
    jobs,
    portals,
    profile,
    searches,
    settings,
    stats,
    users,
    ws,
)

api_router = APIRouter()
# Health first so a probe never depends on anything else being importable.
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(profile.router)
api_router.include_router(settings.router)
api_router.include_router(searches.router)
api_router.include_router(jobs.router)
api_router.include_router(applications.router)
api_router.include_router(automation.router)
api_router.include_router(portals.router)
api_router.include_router(ai.router)
api_router.include_router(stats.router)
api_router.include_router(ws.router)

__all__ = ["api_router"]
