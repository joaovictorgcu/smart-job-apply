"""Resuming interrupted automation runs from their checkpoint."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AutomationRunKind, AutomationRunStatus
from app.services import automation_service
from tests.fixtures.factories import create_run


class TestResumableFlag:
    async def test_an_interrupted_run_with_inputs_is_resumable(
        self, session: AsyncSession, user: Any
    ) -> None:
        run = await create_run(
            session,
            user,
            kind=AutomationRunKind.PREPARE,
            status=AutomationRunStatus.STOPPED,
            checkpoint={"job_ids": [1, 2, 3], "processed_ids": [1]},
        )
        assert automation_service.to_run_read(run).resumable is True

    async def test_a_completed_run_is_not(self, session: AsyncSession, user: Any) -> None:
        run = await create_run(
            session,
            user,
            kind=AutomationRunKind.SEARCH,
            status=AutomationRunStatus.COMPLETED,
            checkpoint={"filters": {"keywords": "python"}},
        )
        assert automation_service.to_run_read(run).resumable is False

    async def test_a_legacy_run_without_inputs_is_not(
        self, session: AsyncSession, user: Any
    ) -> None:
        # Runs created before inputs were persisted have only progress keys.
        run = await create_run(
            session,
            user,
            kind=AutomationRunKind.SEARCH,
            status=AutomationRunStatus.FAILED,
            checkpoint={"processed_ids": ["a"]},
        )
        assert automation_service.to_run_read(run).resumable is False


class TestResumeRoute:
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.post("/api/automation/runs/1/resume")).status_code == 401

    async def test_resumes_a_stopped_prepare_run(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        run = await create_run(
            session,
            user,
            kind=AutomationRunKind.PREPARE,
            status=AutomationRunStatus.STOPPED,
            stop_requested=True,
            error_message="boom",
            checkpoint={"job_ids": [1, 2], "processed_ids": [1]},
        )
        await session.commit()

        response = await client.post(
            f"/api/automation/runs/{run.id}/resume", headers=auth_headers
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        # Relaunched cleanly: pending again with the interruption state cleared.
        assert payload["status"] in ("pending", "running", "completed")
        assert payload["stop_requested"] is False
        assert payload["error_message"] is None

    async def test_refuses_a_run_that_never_stopped(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        run = await create_run(
            session,
            user,
            kind=AutomationRunKind.PREPARE,
            status=AutomationRunStatus.COMPLETED,
            checkpoint={"job_ids": [1]},
        )
        await session.commit()

        response = await client.post(
            f"/api/automation/runs/{run.id}/resume", headers=auth_headers
        )

        assert response.status_code == 412

    async def test_is_scoped_to_the_user(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        other_auth_headers: dict[str, str],
    ) -> None:
        run = await create_run(
            session,
            user,
            kind=AutomationRunKind.PREPARE,
            status=AutomationRunStatus.STOPPED,
            checkpoint={"job_ids": [1]},
        )
        await session.commit()

        response = await client.post(
            f"/api/automation/runs/{run.id}/resume", headers=other_auth_headers
        )

        assert response.status_code == 404


class TestCheckpointCarriesInputs:
    async def test_a_new_search_run_records_its_filters(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/api/automation/search",
            headers=auth_headers,
            json={"keywords": "python backend", "max_results": 10, "analyze": False},
        )
        assert response.status_code == 200, response.text

        run = await automation_service.get_run(session, user, response.json()["id"])
        await session.refresh(run)
        assert run.checkpoint["filters"]["keywords"] == "python backend"
        assert run.checkpoint["analyze"] is False
