"""Every router, aggregated into the single router that `main` mounts under /api."""

from fastapi import APIRouter

from app.api.routes import (
    admin,
    ai,
    applications,
    auth,
    automation,
    health,
    jobs,
    portals,
    preferences,
    profile,
    resumes,
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
api_router.include_router(preferences.router)
api_router.include_router(resumes.router)
api_router.include_router(settings.router)
api_router.include_router(searches.router)
api_router.include_router(jobs.router)
api_router.include_router(applications.router)
api_router.include_router(automation.router)
api_router.include_router(portals.router)
api_router.include_router(ai.router)
api_router.include_router(stats.router)
# Platform-wide and admin-only; its own router carries the authorization
# dependency, so mounting it here grants nothing on its own.
api_router.include_router(admin.router)
api_router.include_router(ws.router)

__all__ = ["api_router"]
