"""Loginless discovery through external job portals (Brazilian boards first)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.portal import PortalSearchRequest, PortalSearchResult
from app.services import portal_service

router = APIRouter(prefix="/portals", tags=["portals"])


@router.get("", response_model=list[str])
async def list_portals(user: CurrentUser) -> list[str]:
    """The portal adapters available in this build."""
    from app.portals import ADAPTERS

    return sorted(ADAPTERS)


@router.post("/search", response_model=PortalSearchResult)
async def search_portal(
    payload: PortalSearchRequest, user: CurrentUser, session: SessionDep
) -> PortalSearchResult:
    """Search one external portal over plain HTTP and persist what is new.

    No browser and no credentials are involved; found jobs enter the same
    scoring and review pipeline as LinkedIn ones. Applying to an external
    posting is a manual act on the company's page — this app prepares the
    materials, never the submission.
    """
    return await portal_service.run_portal_search(
        session,
        user,
        portal=payload.portal,
        keywords=payload.keywords,
        location=payload.location,
        limit=payload.limit,
    )
