"""The per-application resume endpoints: derive, read, edit — and their guards.

The contract these tests hold to the wall: an application's resume is its own,
it can be edited without touching the master or any other application, and it
cannot be edited into a resume that disagrees with the master about where the
candidate worked.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_access_token
from tests.fixtures.factories import create_application, create_job, create_user
from tests.fixtures.resumes import MASTER_PROFILE, POSTINGS

URL = "/api/applications/{application_id}/resume"


async def job_for(session: AsyncSession, user: Any, posting: str = "dotnet") -> Any:
    return await create_job(
        session,
        user,
        title=POSTINGS[posting]["title"],
        description=POSTINGS[posting]["description"],
    )


async def application_for(session: AsyncSession, user: Any, posting: str = "dotnet") -> Any:
    """An application with no resume version yet — the pre-feature shape."""
    return await create_application(session, user, await job_for(session, user, posting))


class TestDerive:
    async def test_deriving_returns_the_version_and_its_base(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
    ) -> None:
        user = await create_user(session, email="master@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)

        response = await client.post(URL.format(application_id=application.id), headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["application_id"] == application.id
        assert body["job_title"] == POSTINGS["dotnet"]["title"]
        assert body["focus"], "the posting and the resume overlap, so there is a focus"
        assert body["document"]["experiences"][0]["company"] == "Globalthings"
        # The base travels with it: the UI diffs against it without a second call.
        assert body["base_document"]["experiences"][0]["company"] == "Globalthings"
        assert body["changes"]
        assert body["source"] == "rules"
        assert body["is_stale"] is False
        assert body["markdown"].strip()

    async def test_reading_before_deriving_is_404(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """An application prepared before this feature existed, exactly."""
        user = await create_user(session, email="old@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)

        response = await client.get(URL.format(application_id=application.id), headers=headers)

        assert response.status_code == 404

    async def test_reading_after_deriving_returns_the_same_document(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="read@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)

        derived = (
            await client.post(URL.format(application_id=application.id), headers=headers)
        ).json()
        read = (await client.get(URL.format(application_id=application.id), headers=headers)).json()

        assert read["document"] == derived["document"]
        assert read["focus"] == derived["focus"]

    async def test_an_empty_master_resume_is_a_precondition_error(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        thin = await create_user(
            session,
            email="thin@example.com",
            profile={"skills": [], "technologies": [], "experiences": [], "projects": []},
        )
        headers = {"Authorization": f"Bearer {create_access_token(thin.id)}"}
        application = await application_for(session, thin)

        response = await client.post(URL.format(application_id=application.id), headers=headers)

        assert response.status_code == 412
        assert "Perfil" in response.json()["detail"]

    async def test_the_derivation_reports_no_invention(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """Everything emphasized came from the master, so the guard finds nothing."""
        user = await create_user(session, email="clean@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)

        body = (
            await client.post(URL.format(application_id=application.id), headers=headers)
        ).json()

        assert body["invention_flags"] == []


class TestEdit:
    async def test_editing_saves_the_users_wording(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="edit@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)
        version = (
            await client.post(URL.format(application_id=application.id), headers=headers)
        ).json()

        document = version["document"]
        document["experiences"][0]["summary"] = "Minha própria descrição para esta vaga."

        response = await client.patch(
            URL.format(application_id=application.id),
            headers=headers,
            json={"document": document},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["source"] == "user"
        assert body["document"]["experiences"][0]["summary"] == (
            "Minha própria descrição para esta vaga."
        )
        # Re-read: the edit is persisted, not just echoed.
        reread = (
            await client.get(URL.format(application_id=application.id), headers=headers)
        ).json()
        assert reread["document"]["experiences"][0]["summary"] == (
            "Minha própria descrição para esta vaga."
        )

    async def test_editing_does_not_touch_the_master_resume(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="keep@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)
        version = (
            await client.post(URL.format(application_id=application.id), headers=headers)
        ).json()
        before = (await client.get("/api/profile", headers=headers)).json()

        document = version["document"]
        document["summary"] = "Resumo só desta candidatura."
        document["experiences"][0]["highlights"] = []
        await client.patch(
            URL.format(application_id=application.id),
            headers=headers,
            json={"document": document},
        )

        after = (await client.get("/api/profile", headers=headers)).json()
        assert after["experiences"] == before["experiences"]
        assert after["summary"] == before["summary"]

    async def test_rewriting_an_employer_is_refused(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """A version re-emphasizes the past; it does not rewrite it."""
        user = await create_user(session, email="rewrite@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)
        version = (
            await client.post(URL.format(application_id=application.id), headers=headers)
        ).json()

        document = version["document"]
        document["experiences"][0]["company"] = "Empresa Que Nunca Existiu"

        response = await client.patch(
            URL.format(application_id=application.id),
            headers=headers,
            json={"document": document},
        )

        assert response.status_code == 422
        assert "master" in response.json()["detail"].lower()

    async def test_an_invented_technology_is_flagged_on_save(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="flag@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)
        version = (
            await client.post(URL.format(application_id=application.id), headers=headers)
        ).json()

        document = version["document"]
        document["experiences"][0]["technologies"].append("Kubernetes")

        body = (
            await client.patch(
                URL.format(application_id=application.id),
                headers=headers,
                json={"document": document},
            )
        ).json()

        assert "Kubernetes" in body["invention_flags"]
        # Flagged, never deleted: the user decides.
        assert "Kubernetes" in body["document"]["experiences"][0]["technologies"]

    async def test_editing_before_deriving_is_404(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="nodraft@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)

        response = await client.patch(
            URL.format(application_id=application.id),
            headers=headers,
            json={"document": {"experiences": []}},
        )

        assert response.status_code == 404

    async def test_re_deriving_is_the_way_back_to_the_master(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="reset@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)
        version = (
            await client.post(URL.format(application_id=application.id), headers=headers)
        ).json()
        # Copied, not aliased: the assertion below compares against the version
        # as it was derived, so the test must not edit that copy too.
        document = deepcopy(version["document"])
        document["summary"] = "Rascunho que eu quero descartar."
        await client.patch(
            URL.format(application_id=application.id),
            headers=headers,
            json={"document": document},
        )

        again = (
            await client.post(URL.format(application_id=application.id), headers=headers)
        ).json()

        assert again["source"] == "rules"
        assert again["document"]["summary"] != "Rascunho que eu quero descartar."
        assert again["document"] == version["document"]


class TestStaleness:
    async def test_editing_the_master_marks_an_existing_version_stale(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """Stale is an offer to re-derive, not a change to what is stored."""
        user = await create_user(session, email="stale@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)
        version = (
            await client.post(URL.format(application_id=application.id), headers=headers)
        ).json()

        await client.put(
            "/api/profile",
            headers=headers,
            json={"summary": "Dez anos construindo produtos web."},
        )

        after = (
            await client.get(URL.format(application_id=application.id), headers=headers)
        ).json()
        assert after["is_stale"] is True
        # The version itself did not move.
        assert after["document"] == version["document"]


class TestApplicationPayload:
    async def test_the_application_reports_which_resume_it_uses(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="payload@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)
        await client.post(URL.format(application_id=application.id), headers=headers)

        detail = (await client.get(f"/api/applications/{application.id}", headers=headers)).json()
        listing = (await client.get("/api/applications", headers=headers)).json()

        assert detail["resume_focus"]
        assert listing["items"][0]["resume_focus"] == detail["resume_focus"]

    async def test_an_application_without_a_version_reports_no_focus(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="nofocus@example.com", profile=dict(MASTER_PROFILE))
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user)

        detail = (await client.get(f"/api/applications/{application.id}", headers=headers)).json()

        assert detail["resume_focus"] == []


class TestAuthAndIsolation:
    async def test_requires_authentication(
        self, client: AsyncClient, session: AsyncSession, user: Any
    ) -> None:
        application = await application_for(session, user)

        assert (await client.get(URL.format(application_id=application.id))).status_code == 401
        assert (await client.post(URL.format(application_id=application.id))).status_code == 401
        assert (
            await client.patch(URL.format(application_id=application.id), json={"document": {}})
        ).status_code == 401

    async def test_another_user_cannot_reach_the_version(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        other_auth_headers: dict[str, str],
    ) -> None:
        application = await application_for(session, user)
        await client.post(URL.format(application_id=application.id), headers=auth_headers)

        assert (
            await client.get(URL.format(application_id=application.id), headers=other_auth_headers)
        ).status_code == 404
        assert (
            await client.post(URL.format(application_id=application.id), headers=other_auth_headers)
        ).status_code == 404
