"""The audit trail of guardrail changes.

Turning off dry-run or manual approval, raising the daily cap, lowering the
minimum score: every one of these weakens the promise that nothing is submitted
without a human, so every one of them has to leave a row behind. A change that was
*rejected*, or that changed nothing, must leave none.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_access_token
from tests.fixtures.factories import create_user

AUDIT_URL = "/api/users/me/audit"


async def read_trail(client: AsyncClient, headers: dict[str, str], **params: Any) -> list[dict]:
    response = await client.get(AUDIT_URL, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
async def live_headers(session: AsyncSession) -> dict[str, str]:
    """A user whose dry-run is already off, so a change can *tighten* a guardrail."""
    caller = await create_user(session, email="live@example.com", settings={"dry_run": False})
    return {"Authorization": f"Bearer {create_access_token(caller.id)}"}


class TestRelaxingAGuardrail:
    async def test_turning_dry_run_off_is_recorded_once(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.put(
            "/api/settings", headers=auth_headers, json={"dry_run": False}
        )
        assert response.status_code == 200, response.text

        trail = await read_trail(client, auth_headers)

        assert len(trail) == 1
        entry = trail[0]
        assert entry["action"] == "settings_updated"
        assert entry["subject_type"] == "user_settings"
        assert entry["before"] == {"dry_run": True}
        assert entry["after"] == {"dry_run": False}
        assert entry["relaxed"] == ["dry_run"]

    async def test_a_raised_cap_and_a_lowered_score_both_count_as_relaxations(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.put(
            "/api/settings", headers=auth_headers, json={"daily_cap": 40, "min_score": 30}
        )
        assert response.status_code == 200, response.text

        trail = await read_trail(client, auth_headers)

        assert len(trail) == 1
        assert sorted(trail[0]["relaxed"]) == ["daily_cap", "min_score"]
        assert trail[0]["before"] == {"daily_cap": 15, "min_score": 70}
        assert trail[0]["after"] == {"daily_cap": 40, "min_score": 30}

    async def test_a_wider_working_window_is_a_relaxation_at_both_ends(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        caller = await create_user(
            session,
            email="hours@example.com",
            settings={"working_hour_start": 9, "working_hour_end": 18},
        )
        headers = {"Authorization": f"Bearer {create_access_token(caller.id)}"}

        response = await client.put(
            "/api/settings",
            headers=headers,
            json={"working_hour_start": 6, "working_hour_end": 23},
        )
        assert response.status_code == 200, response.text

        trail = await read_trail(client, headers)

        assert sorted(trail[0]["relaxed"]) == ["working_hour_end", "working_hour_start"]


class TestChangesThatAreNotRelaxations:
    async def test_tightening_a_guardrail_is_recorded_with_an_empty_relaxed_list(
        self, client: AsyncClient, live_headers: dict[str, str]
    ) -> None:
        response = await client.put("/api/settings", headers=live_headers, json={"dry_run": True})
        assert response.status_code == 200, response.text

        trail = await read_trail(client, live_headers)

        assert len(trail) == 1
        assert trail[0]["before"] == {"dry_run": False}
        assert trail[0]["after"] == {"dry_run": True}
        assert trail[0]["relaxed"] == []

    async def test_a_no_op_update_records_nothing(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.put(
            "/api/settings", headers=auth_headers, json={"daily_cap": 15, "dry_run": True}
        )
        assert response.status_code == 200, response.text

        assert await read_trail(client, auth_headers) == []

    async def test_only_the_fields_that_moved_are_recorded(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """A partial update repeats unchanged fields; the trail must not repeat them."""
        response = await client.put(
            "/api/settings", headers=auth_headers, json={"daily_cap": 15, "min_score": 90}
        )
        assert response.status_code == 200, response.text

        trail = await read_trail(client, auth_headers)

        assert trail[0]["after"] == {"min_score": 90}
        assert trail[0]["relaxed"] == []


class TestRejectedChanges:
    async def test_disabling_manual_approval_is_refused_and_never_audited(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Assisted mode refuses the change; auditing it would claim it happened."""
        response = await client.put(
            "/api/settings", headers=auth_headers, json={"require_manual_approval": False}
        )
        assert response.status_code == 422, response.text

        assert await read_trail(client, auth_headers) == []
        settings = (await client.get("/api/settings", headers=auth_headers)).json()
        assert settings["require_manual_approval"] is True

    async def test_an_invalid_range_is_refused_and_never_audited(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """The merged result is what fails here, and the trail must not show it."""
        caller = await create_user(
            session,
            email="narrow@example.com",
            settings={"working_hour_start": 9, "working_hour_end": 18},
        )
        headers = {"Authorization": f"Bearer {create_access_token(caller.id)}"}

        response = await client.put(
            "/api/settings", headers=headers, json={"working_hour_start": 19}
        )
        assert response.status_code == 422, response.text

        assert await read_trail(client, headers) == []


class TestProfileChanges:
    async def test_the_trail_holds_field_names_and_never_the_resume_text(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        secret = "Classified: worked at Acme on project Nightingale."

        response = await client.put(
            "/api/profile", headers=auth_headers, json={"resume_text": secret, "phone": "+55 11"}
        )
        assert response.status_code == 200, response.text

        raw = await client.get(AUDIT_URL, headers=auth_headers)
        trail = raw.json()

        assert len(trail) == 1
        assert trail[0]["action"] == "profile_updated"
        assert trail[0]["after"] == {"fields": ["phone", "resume_text"]}
        assert trail[0]["before"] == {}
        assert secret not in raw.text
        assert "+55 11" not in raw.text

    async def test_a_resume_upload_records_the_stored_name_and_size(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        content = b"%PDF-1.4 not a real document"

        response = await client.post(
            "/api/profile/resume",
            headers=auth_headers,
            files={"file": ("cv.pdf", content, "application/pdf")},
        )
        assert response.status_code == 200, response.text

        trail = await read_trail(client, auth_headers)

        assert trail[0]["action"] == "resume_uploaded"
        assert trail[0]["after"]["bytes"] == len(content)
        assert trail[0]["after"]["filename"].endswith(".pdf")


class TestReadingTheTrail:
    async def test_it_is_newest_first_and_honours_the_limit(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await client.put("/api/settings", headers=auth_headers, json={"daily_cap": 20})
        await client.put("/api/settings", headers=auth_headers, json={"min_score": 50})

        trail = await read_trail(client, auth_headers)
        newest_only = await read_trail(client, auth_headers, limit=1)

        assert [entry["after"] for entry in trail] == [{"min_score": 50}, {"daily_cap": 20}]
        assert newest_only == trail[:1]

    async def test_an_out_of_range_limit_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(AUDIT_URL, headers=auth_headers, params={"limit": 500})

        assert response.status_code == 422, response.text

    async def test_the_trail_needs_authentication(self, client: AsyncClient) -> None:
        response = await client.get(AUDIT_URL)

        assert response.status_code == 401, response.text


class TestIsolation:
    async def test_another_users_trail_is_never_returned(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        other_auth_headers: dict[str, str],
    ) -> None:
        await client.put("/api/settings", headers=auth_headers, json={"dry_run": False})

        theirs = await read_trail(client, other_auth_headers)

        assert theirs == []
        assert len(await read_trail(client, auth_headers)) == 1
