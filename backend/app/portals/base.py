"""The contract every job-portal adapter satisfies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


class PortalError(RuntimeError):
    """A portal request failed in a way worth reporting to the user."""


@dataclass(slots=True)
class PortalPosting:
    """One job as a portal reports it — the adapter's whole output surface."""

    external_id: str
    title: str
    company: str
    url: str | None = None
    location: str | None = None
    workplace_type: str | None = None
    description: str | None = None
    posted_at: datetime | None = None
    extra: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class PortalAdapter(Protocol):
    """Search a portal without a browser or credentials."""

    #: Registry key and the `Job.source` value for postings found here.
    name: str

    async def search(
        self,
        keywords: str,
        *,
        location: str | None = None,
        limit: int = 25,
    ) -> list[PortalPosting]:
        """Return up to `limit` postings for the query."""
        ...
