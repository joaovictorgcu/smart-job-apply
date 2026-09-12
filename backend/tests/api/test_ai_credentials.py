"""Bringing your own AI key, over HTTP.

The free tiers this app runs on are rate-limited per key, so one shared
`AI_API_KEY` is one shared 429. An account may therefore store its own — which
makes the key a secret the API accepts, never returns, and never writes into the
audit trail it also exposes.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.crypto import decrypt_text
from app.models import UserSettings

SETTINGS_URL = "/api/settings"
TEST_URL = "/api/settings/ai/test"
PROVIDERS_URL = "/api/settings/ai/providers"
STATUS_URL = "/api/ai/status"
AUDIT_URL = "/api/users/me/audit"

SECRET = "gsk-a-real-looking-secret-key"


async def stored_settings(session: AsyncSession, user_id: int) -> UserSettings:
    """Re-read the row from the database, not from this session's identity map.

    `expunge_all` rather than `expire_all`: the request wrote through a session
    of its own, and an expired instance would try to refresh itself lazily on
    first attribute access — outside the greenlet that makes async IO legal.
    """
    session.expunge_all()
    result = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    return result.scalar_one()


async def put(client: AsyncClient, headers: dict[str, str], **body: Any) -> Any:
    return await client.put(SETTINGS_URL, headers=headers, json=body)


class TestStoringAKey:
    async def test_a_key_is_stored_encrypted_and_never_returned(
        self, client: AsyncClient, auth_headers: dict[str, str], session: AsyncSession, user: Any
    ) -> None:
        response = await put(client, auth_headers, ai_provider="groq", ai_api_key=SECRET)
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["ai_provider"] == "groq"
        assert body["ai_key_set"] is True
        assert SECRET not in response.text
        assert "ai_api_key" not in body

        row = await stored_settings(session, user.id)
        assert row.ai_api_key_encrypted is not None
        assert SECRET not in row.ai_api_key_encrypted
        assert decrypt_text(row.ai_api_key_encrypted) == SECRET

    async def test_reading_settings_back_never_exposes_the_key(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await put(client, auth_headers, ai_provider="gemini", ai_api_key=SECRET)

        response = await client.get(SETTINGS_URL, headers=auth_headers)

        assert response.status_code == 200
        assert SECRET not in response.text
        assert response.json()["ai_key_set"] is True

    async def test_a_provider_the_account_may_not_select_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """`ollama` is localhost, and on a hosted install that is the server."""
        response = await put(client, auth_headers, ai_provider="ollama", ai_api_key=SECRET)

        assert response.status_code == 422
        assert "ollama" in response.json()["detail"]

    async def test_a_base_url_cannot_be_smuggled_in(
        self, client: AsyncClient, auth_headers: dict[str, str], session: AsyncSession, user: Any
    ) -> None:
        """The SSRF this design exists to prevent: a user-chosen endpoint the
        server would then fetch. The preset's URL is compiled in, and the field
        simply is not part of the contract."""
        response = await put(
            client,
            auth_headers,
            ai_provider="groq",
            ai_api_key=SECRET,
            ai_base_url="http://169.254.169.254/latest/meta-data/",
        )

        assert response.status_code == 200
        assert not hasattr(await stored_settings(session, user.id), "ai_base_url")

        from app.ai.credentials import for_settings_row

        assert for_settings_row(await stored_settings(session, user.id)).ai_base_url == ""


class TestRefusingWhatCannotWork:
    async def test_a_provider_without_a_key_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await put(client, auth_headers, ai_provider="groq")

        assert response.status_code == 422
        assert "console.groq.com" in response.json()["detail"]

    async def test_switching_provider_without_a_new_key_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], session: AsyncSession, user: Any
    ) -> None:
        """The stored key belongs to the provider being left. Sending it to the
        new one is a 401 an hour later, in a run nobody is watching."""
        await put(client, auth_headers, ai_provider="groq", ai_api_key=SECRET)

        response = await put(client, auth_headers, ai_provider="cerebras")

        assert response.status_code == 422
        assert "cerebras" in response.json()["detail"]
        row = await stored_settings(session, user.id)
        assert row.ai_provider == "groq"
        assert decrypt_text(row.ai_api_key_encrypted or "") == SECRET

    async def test_switching_provider_with_a_new_key_is_accepted(
        self, client: AsyncClient, auth_headers: dict[str, str], session: AsyncSession, user: Any
    ) -> None:
        await put(client, auth_headers, ai_provider="groq", ai_api_key=SECRET)

        response = await put(
            client, auth_headers, ai_provider="cerebras", ai_api_key="csk-second-key"
        )

        assert response.status_code == 200
        row = await stored_settings(session, user.id)
        assert row.ai_provider == "cerebras"
        assert decrypt_text(row.ai_api_key_encrypted or "") == "csk-second-key"

    async def test_a_rejected_change_leaves_no_audit_row(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await put(client, auth_headers, ai_provider="groq")

        trail = await client.get(AUDIT_URL, headers=auth_headers)

        assert trail.json() == []


class TestClearing:
    async def test_clearing_the_provider_drops_the_key_with_it(
        self, client: AsyncClient, auth_headers: dict[str, str], session: AsyncSession, user: Any
    ) -> None:
        """A secret at rest that nothing can read again is pure liability."""
        await put(client, auth_headers, ai_provider="groq", ai_api_key=SECRET)

        response = await put(client, auth_headers, ai_provider="")

        assert response.status_code == 200
        assert response.json()["ai_key_set"] is False
        row = await stored_settings(session, user.id)
        assert row.ai_provider is None
        assert row.ai_api_key_encrypted is None

    async def test_an_empty_key_clears_it_but_an_absent_one_does_not(
        self, client: AsyncClient, auth_headers: dict[str, str], session: AsyncSession, user: Any
    ) -> None:
        await put(client, auth_headers, ai_provider="groq", ai_api_key=SECRET)

        # Absent: an unrelated settings change must not disturb the key.
        await put(client, auth_headers, daily_cap=20)
        row = await stored_settings(session, user.id)
        assert row.ai_api_key_encrypted is not None

        # Present and empty, with the provider cleared in the same request —
        # a key alone cannot be removed while a provider still needs it.
        response = await put(client, auth_headers, ai_provider="", ai_api_key="")

        assert response.status_code == 200
        assert (await stored_settings(session, user.id)).ai_api_key_encrypted is None


class TestTheAuditTrail:
    async def test_the_trail_records_that_a_key_moved_never_the_key(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """The audit table is append-only and readable over the API: it is the
        worst possible place to copy a credential into."""
        await put(client, auth_headers, ai_provider="groq", ai_api_key=SECRET)

        response = await client.get(AUDIT_URL, headers=auth_headers)

        assert SECRET not in response.text
        entry = response.json()[0]
        assert entry["after"]["ai_api_key"] == "set"
        assert entry["after"]["ai_provider"] == "groq"
        assert entry["before"]["ai_api_key"] == "***"


class TestStatus:
    async def test_status_answers_for_the_account_not_the_deployment(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await put(client, auth_headers, ai_provider="groq", ai_api_key=SECRET)

        body = (await client.get(STATUS_URL, headers=auth_headers)).json()

        assert body["configured"] is True
        assert body["provider"] == "groq"
        assert body["source"] == "account"
        assert body["detail"] == ""

    async def test_an_account_with_no_key_of_its_own_reports_the_deployment(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        body = (await client.get(STATUS_URL, headers=auth_headers)).json()

        assert body["source"] == "deployment"
        assert body["provider"] == "anthropic"  # what conftest pins

    async def test_the_selectable_providers_exclude_local_ones(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        body = (await client.get(PROVIDERS_URL, headers=auth_headers)).json()

        names = {option["name"] for option in body}
        assert "groq" in names
        assert names.isdisjoint({"ollama", "llamacpp", "openai_compat", "stub"})
        assert all(option["key_url"] for option in body)


class FakeProbeClient:
    """Stands in for a built provider: the endpoint's job is what is tested."""

    def __init__(self, *, model: str = "llama-3.3-70b-versatile", error: Exception | None = None):
        self.model = model
        self._error = error
        self.closed = False
        self.probes = 0

    async def probe(self) -> str:
        self.probes += 1
        if self._error is not None:
            raise self._error
        return "OK"

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def probe_client(monkeypatch: pytest.MonkeyPatch) -> FakeProbeClient:
    fake = FakeProbeClient()
    monkeypatch.setattr(
        "app.api.routes.settings.get_ai_client", lambda *a, **k: fake, raising=True
    )
    return fake


class TestTestingAKey:
    async def test_a_working_key_reports_the_model_it_reached(
        self, client: AsyncClient, auth_headers: dict[str, str], probe_client: FakeProbeClient
    ) -> None:
        response = await client.post(
            TEST_URL, headers=auth_headers, json={"provider": "groq", "api_key": SECRET}
        )

        assert response.status_code == 200
        assert response.json() == {
            "ok": True,
            "provider": "groq",
            "model": probe_client.model,
            "detail": "",
        }
        assert probe_client.probes == 1
        assert probe_client.closed is True

    async def test_testing_a_key_does_not_store_it(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        session: AsyncSession,
        user: Any,
        probe_client: FakeProbeClient,
    ) -> None:
        """Testing and saving are separate acts; a key that fails should not end
        up on the account because someone clicked the wrong button."""
        await client.post(
            TEST_URL, headers=auth_headers, json={"provider": "groq", "api_key": SECRET}
        )

        row = await stored_settings(session, user.id)
        assert row.ai_provider is None
        assert row.ai_api_key_encrypted is None

    async def test_a_rejected_key_is_a_200_carrying_the_provider_s_words(
        self, client: AsyncClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.ai.providers import ProviderError

        fake = FakeProbeClient(error=ProviderError("groq: invalid api key"))
        monkeypatch.setattr(
            "app.api.routes.settings.get_ai_client", lambda *a, **k: fake, raising=True
        )

        response = await client.post(
            TEST_URL, headers=auth_headers, json={"provider": "groq", "api_key": "wrong"}
        )

        assert response.status_code == 200
        assert response.json()["ok"] is False
        assert "invalid api key" in response.json()["detail"]
        assert fake.closed is True

    async def test_a_provider_that_cannot_be_selected_never_reaches_the_network(
        self, client: AsyncClient, auth_headers: dict[str, str], probe_client: FakeProbeClient
    ) -> None:
        response = await client.post(
            TEST_URL, headers=auth_headers, json={"provider": "ollama", "api_key": ""}
        )

        assert response.status_code == 200
        assert response.json()["ok"] is False
        assert probe_client.probes == 0

    async def test_the_stored_key_can_be_retested_without_retyping_it(
        self, client: AsyncClient, auth_headers: dict[str, str], probe_client: FakeProbeClient
    ) -> None:
        """The UI cannot show the key back, so it cannot ask for it again."""
        await put(client, auth_headers, ai_provider="groq", ai_api_key=SECRET)

        response = await client.post(TEST_URL, headers=auth_headers, json={})

        assert response.json()["ok"] is True
        assert response.json()["provider"] == "groq"
        assert probe_client.probes == 1
