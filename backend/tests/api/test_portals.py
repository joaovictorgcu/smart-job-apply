"""External portal discovery — the Gupy adapter and its persistence."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, User
from app.portals import GupyAdapter, PortalAdapter
from app.portals.base import PortalError
from app.services import portal_service

GUPY_PAYLOAD = {
    "data": [
        {
            "id": 9001,
            "name": "Pessoa Engenheira Backend Python",
            "careerPageName": "Nubank",
            "jobUrl": "https://nubank.gupy.io/jobs/9001",
            "city": "São Paulo",
            "state": "SP",
            "isRemoteWork": True,
            "publishedDate": "2026-08-10T12:00:00.000Z",
            "description": "<p>FastAPI e <b>PostgreSQL</b> em produção.</p>",
        },
        {
            "id": 9002,
            "name": "Dev Python Júnior",
            "careerPageName": "Stone",
            "jobUrl": "https://stone.gupy.io/jobs/9002",
            "city": "Recife",
            "state": "PE",
            "isRemoteWork": False,
            "publishedDate": None,
            "description": None,
        },
    ]
}


def _adapter(payload: Any = None, status_code: int = 200) -> GupyAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code, content=json.dumps(payload if payload is not None else GUPY_PAYLOAD)
        )

    return GupyAdapter(transport=httpx.MockTransport(handler))


class TestGupyAdapter:
    def test_satisfies_the_portal_protocol(self) -> None:
        assert isinstance(GupyAdapter(), PortalAdapter)

    async def test_parses_the_public_payload(self) -> None:
        postings = await _adapter().search("python")

        assert [posting.external_id for posting in postings] == ["gupy-9001", "gupy-9002"]
        first = postings[0]
        assert first.company == "Nubank"
        assert first.location == "São Paulo, SP"
        assert first.workplace_type == "remote"
        # HTML stripped, never fed raw into prompts or the UI.
        assert first.description == "FastAPI e PostgreSQL em produção."
        assert first.posted_at is not None and first.posted_at.tzinfo is not None

    async def test_filters_by_location_client_side(self) -> None:
        postings = await _adapter().search("python", location="Recife")
        assert [posting.company for posting in postings] == ["Stone"]

    async def test_an_http_failure_is_a_portal_error(self) -> None:
        with pytest.raises(PortalError):
            await _adapter(status_code=503).search("python")

    async def test_an_unexpected_shape_is_a_portal_error(self) -> None:
        with pytest.raises(PortalError):
            await _adapter(payload={"jobs": []}).search("python")


class TestPortalService:
    async def test_persists_new_jobs_with_their_source(
        self, session: AsyncSession, user: User
    ) -> None:
        result = await portal_service.run_portal_search(
            session, user, portal="gupy", keywords="python", adapter=_adapter()
        )

        assert result.jobs_found == 2 and result.jobs_new == 2
        rows = (await session.execute(select(Job).where(Job.user_id == user.id))).scalars().all()
        assert {job.source for job in rows} == {"gupy"}
        assert all(job.easy_apply is False for job in rows)

    async def test_rerunning_never_duplicates(self, session: AsyncSession, user: User) -> None:
        await portal_service.run_portal_search(
            session, user, portal="gupy", keywords="python", adapter=_adapter()
        )
        result = await portal_service.run_portal_search(
            session, user, portal="gupy", keywords="python", adapter=_adapter()
        )

        assert result.jobs_found == 2 and result.jobs_new == 0

    async def test_an_unknown_portal_is_a_validation_error(
        self, session: AsyncSession, user: User
    ) -> None:
        from app.api.errors import ValidationError

        with pytest.raises(ValidationError):
            await portal_service.run_portal_search(
                session, user, portal="monster", keywords="python"
            )


class TestPortalRoutes:
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get("/api/portals")).status_code == 401
        assert (
            await client.post(
                "/api/portals/search", json={"portal": "gupy", "keywords": "python"}
            )
        ).status_code == 401

    async def test_lists_the_available_portals(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/portals", headers=auth_headers)
        assert response.status_code == 200
        assert "gupy" in response.json()
