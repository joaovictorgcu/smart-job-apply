"""Discovery through external job portals.

Pure HTTP discovery: postings found here enter the same jobs table, dedup rule
and scoring/review pipeline as LinkedIn ones. Nothing in this module applies to
anything — an external posting is applied to by the user, on the company's own
page, with the materials this app prepared.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ValidationError
from app.models import Job, JobStatus, User
from app.observability import get_logger
from app.portals import ADAPTERS, PortalAdapter
from app.schemas.portal import PortalSearchResult

logger = get_logger(__name__)


def get_adapter(portal: str) -> PortalAdapter:
    adapter_cls = ADAPTERS.get(portal)
    if adapter_cls is None:
        known = ", ".join(sorted(ADAPTERS))
        raise ValidationError(f"Unknown portal '{portal}'. Available: {known}.")
    return adapter_cls()


async def run_portal_search(
    session: AsyncSession,
    user: User,
    *,
    portal: str,
    keywords: str,
    location: str | None = None,
    limit: int = 25,
    adapter: PortalAdapter | None = None,
) -> PortalSearchResult:
    """Search one portal and persist what is new for this user.

    The `(user, external_id)` unique constraint is honoured by checking first:
    re-running a search never duplicates or rewrites a posting the user may
    already have scored or applied to.
    """
    resolved = adapter or get_adapter(portal)
    postings = await resolved.search(keywords, location=location, limit=limit)

    existing = {
        row[0]
        for row in (
            await session.execute(
                select(Job.external_id).where(
                    Job.user_id == user.id,
                    Job.external_id.in_([posting.external_id for posting in postings]),
                )
            )
        ).all()
    }

    new_jobs = 0
    for posting in postings:
        if posting.external_id in existing:
            continue
        session.add(
            Job(
                user_id=user.id,
                external_id=posting.external_id,
                source=resolved.name,
                title=posting.title,
                company=posting.company,
                location=posting.location,
                url=posting.url,
                description=posting.description,
                workplace_type=posting.workplace_type,
                # External portals have no Easy Apply: filling is not automated,
                # so this stays false and the apply step is explicitly manual.
                easy_apply=False,
                posted_at=posting.posted_at,
                status=JobStatus.DISCOVERED,
            )
        )
        new_jobs += 1
    await session.flush()

    logger.info(
        "Portal search persisted.",
        extra={
            "action": "portal.search",
            "status": "ok",
            "user_id": user.id,
            "portal": resolved.name,
            "found": len(postings),
            "new": new_jobs,
        },
    )
    return PortalSearchResult(portal=resolved.name, jobs_found=len(postings), jobs_new=new_jobs)
