"""Gupy — the ATS behind a large share of Brazilian tech hiring.

Gupy exposes a public, unauthenticated JSON search endpoint for its job portal,
so discovery here is plain HTTP: no browser, no login, no scraping fragility,
and no terms-of-service tension of driving a UI. The tradeoff is honesty about
scope — this finds and enriches postings; applying remains a human act on the
company's career page.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx

from app.observability import get_logger
from app.portals.base import PortalError, PortalPosting

logger = get_logger(__name__)

SEARCH_URL = "https://portal.api.gupy.io/api/job"
_TIMEOUT_SECONDS = 15.0
# The portal rejects anonymous default user agents; identify as a browser-like
# client the same way the portal's own frontend does.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; smart-job-apply/0.1)"}

_TAG = re.compile(r"<[^>]+>")


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = _TAG.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _parse_date(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _workplace(row: dict[str, Any]) -> str | None:
    if row.get("isRemoteWork") or row.get("remoteWork"):
        return "remote"
    workplace = row.get("workplaceType")
    if isinstance(workplace, str) and workplace.strip():
        return workplace.strip().lower()
    return None


class GupyAdapter:
    """Search Gupy's public portal API."""

    name = "gupy"

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # An injectable transport keeps the offline test suite honest: tests
        # serve canned JSON through httpx.MockTransport, never the network.
        self._transport = transport

    async def search(
        self,
        keywords: str,
        *,
        location: str | None = None,
        limit: int = 25,
    ) -> list[PortalPosting]:
        params: dict[str, Any] = {"name": keywords, "limit": max(1, min(limit, 50)), "offset": 0}
        async with httpx.AsyncClient(
            transport=self._transport, timeout=_TIMEOUT_SECONDS, headers=_HEADERS
        ) as client:
            try:
                response = await client.get(SEARCH_URL, params=params)
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPError as exc:
                raise PortalError(f"Gupy search failed: {exc}") from exc

        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise PortalError("Gupy returned an unexpected payload shape.")

        postings: list[PortalPosting] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("id") is None:
                continue
            company = str(row.get("careerPageName") or "").strip()
            city = row.get("city") or ""
            state = row.get("state") or ""
            posting_location = ", ".join(part for part in (city, state) if part) or None
            if location and posting_location and location.lower() not in posting_location.lower():
                # The endpoint has no reliable location filter; applied client-side.
                continue
            postings.append(
                PortalPosting(
                    external_id=f"gupy-{row['id']}",
                    title=str(row.get("name") or "").strip() or "(sem título)",
                    company=company or "(empresa não informada)",
                    url=row.get("jobUrl") or row.get("careerPageUrl"),
                    location=posting_location,
                    workplace_type=_workplace(row),
                    description=_strip_html(row.get("description")),
                    posted_at=_parse_date(row.get("publishedDate")),
                )
            )
        logger.info(
            "Gupy search finished.",
            extra={
                "action": "portal.gupy.search",
                "status": "ok",
                "keywords": keywords,
                "found": len(postings),
            },
        )
        return postings
