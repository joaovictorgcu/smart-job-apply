"""Loginless job-portal adapters.

The reference architecture from the LinkedIn layer, applied to portals with a
public surface: each adapter satisfies `PortalAdapter` and returns plain
`PortalPosting` dataclasses, so the scoring/review pipeline downstream never
knows which portal a job came from. No browser, no credentials — these fetch
public endpoints over plain HTTP.
"""

from app.portals.base import PortalAdapter, PortalError, PortalPosting
from app.portals.gupy import GupyAdapter

# Registry of available portals; adding one is one class plus one entry here.
ADAPTERS: dict[str, type[PortalAdapter]] = {
    "gupy": GupyAdapter,
}

__all__ = ["ADAPTERS", "GupyAdapter", "PortalAdapter", "PortalError", "PortalPosting"]
