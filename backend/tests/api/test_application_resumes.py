"""One user, four vacancies, four independent resumes.

The tests are arranged around the promise the feature makes, in the order a
reviewer would want to see it proven:

* every application gets its own copy of the resume, derived from the master;
* the copies differ from each other because the postings differ;
* editing the master leaves existing copies alone;
* editing one copy leaves the master and every sibling alone.

Assertions go through the API rather than the ORM wherever possible: the isolation
that matters is the one a browser can observe, and a request is the only thing
that proves the whole stack agrees.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_access_token
from app.models import ApplicationResume, ApplicationStatus
from tests.fixtures.factories import (
    JOB_POSTINGS,
    create_application,
    create_posting_job,
    create_resume_history,
    create_user,
)

MASTER = "/api/resumes/master"
VERSIONS = "/api/resumes/versions"
APPLICATION = "/api/resumes/applications/{application_id}"
EXPERIENCES = "/api/profile/experiences"


async def seeded_user(session: AsyncSession, email: str) -> Any:
    """A user whose master resume has the full four-position history."""
    user = await create_user(session, email=email)
    await create_resume_history(session, user)
    return user


async def application_for(session: AsyncSession, user: Any, kind: str) -> Any:
    """An application awaiting review for one of the four example vacancies."""
    job = await create_posting_job(session, user, kind)
    return await create_application(session, user, job)


async def adapt(
    client: AsyncClient, headers: dict[str, str], application_id: int
) -> dict[str, Any]:
    response = await client.post(APPLICATION.format(application_id=application_id), headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def leading_company(body: dict[str, Any]) -> str:
    return body["experiences"][0]["company"]


class TestDerivingACopy:
    async def test_adapting_produces_a_document_and_a_report(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")

        body = await adapt(client, auth_headers, application.id)

        assert body["application_id"] == application.id
        assert body["job_title"] == JOB_POSTINGS["dotnet"]["title"]
        assert body["version"] == 1
        assert len(body["experiences"]) == 4
        assert body["changes"]
        assert body["fit_score"] > 0
        assert body["was_edited"] is False
        assert body["is_stale"] is False

    async def test_the_copy_survives_a_reload(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        """A snapshot nobody can read back is not a snapshot."""
        await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")
        created = await adapt(client, auth_headers, application.id)

        reread = await client.get(
            APPLICATION.format(application_id=application.id), headers=auth_headers
        )

        assert reread.status_code == 200, reread.text
        assert reread.json()["experiences"] == created["experiences"]
        assert reread.json()["fit_score"] == created["fit_score"]

    async def test_reading_before_adapting_is_404(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        """A normal state for an application created before this existed."""
        application = await application_for(session, user, "dotnet")

        response = await client.get(
            APPLICATION.format(application_id=application.id), headers=auth_headers
        )

        assert response.status_code == 404

    async def test_an_empty_master_resume_is_a_precondition_error(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        thin = await create_user(
            session, email="thin-resume@example.com", profile={"resume_text": "", "skills": []}
        )
        headers = {"Authorization": f"Bearer {create_access_token(thin.id)}"}
        application = await application_for(session, thin, "dotnet")

        response = await client.post(
            APPLICATION.format(application_id=application.id), headers=headers
        )

        assert response.status_code == 412
        count = await session.scalar(
            select(func.count())
            .select_from(ApplicationResume)
            .where(ApplicationResume.application_id == application.id)
        )
        assert count == 0

    async def test_adapting_is_recorded_in_the_application_trail(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        """ "Which resume is this application using, and since when" is answerable."""
        await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")
        await adapt(client, auth_headers, application.id)

        events = await client.get(
            f"/api/applications/{application.id}/events", headers=auth_headers
        )

        assert events.status_code == 200
        assert any(event["event_type"] == "resume_adapted" for event in events.json())


class TestSeveralApplicationsOneUser:
    async def test_four_vacancies_produce_four_different_leading_experiences(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        """The demonstration the whole feature exists for."""
        await create_resume_history(session, user)
        bodies = {}
        for kind in ("dotnet", "fullstack", "python", "engineering"):
            application = await application_for(session, user, kind)
            bodies[kind] = await adapt(client, auth_headers, application.id)

        assert leading_company(bodies["dotnet"]) == "Globalthings"
        assert leading_company(bodies["fullstack"]) == "Nuvem Retail"
        assert leading_company(bodies["python"]) == "Instituto Dados Abertos"
        assert leading_company(bodies["engineering"]) == "Auditar Sistemas"

    async def test_the_emphasised_technologies_change_with_the_vacancy(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        backend = await adapt(
            client, auth_headers, (await application_for(session, user, "dotnet")).id
        )
        data = await adapt(
            client, auth_headers, (await application_for(session, user, "python")).id
        )

        assert "C#" in backend["emphasized_technologies"]
        assert "C#" not in data["emphasized_technologies"]
        assert "Python" in data["emphasized_technologies"]

    async def test_the_same_experience_is_described_differently_per_vacancy(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        backend = await adapt(
            client, auth_headers, (await application_for(session, user, "dotnet")).id
        )
        fullstack = await adapt(
            client, auth_headers, (await application_for(session, user, "fullstack")).id
        )

        def globalthings(body: dict[str, Any]) -> dict[str, Any]:
            return next(item for item in body["experiences"] if item["company"] == "Globalthings")

        assert (
            globalthings(backend)["responsibilities"] != globalthings(fullstack)["responsibilities"]
        )
        assert "C#" in globalthings(backend)["responsibilities"][0]
        assert "React" in globalthings(fullstack)["responsibilities"][0]

    async def test_every_version_is_listed_with_its_posting(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        for kind in ("dotnet", "fullstack", "python"):
            await adapt(client, auth_headers, (await application_for(session, user, kind)).id)

        response = await client.get(VERSIONS, headers=auth_headers)

        assert response.status_code == 200, response.text
        rows = response.json()
        assert len(rows) == 3
        assert {row["job_title"] for row in rows} == {
            JOB_POSTINGS[kind]["title"] for kind in ("dotnet", "fullstack", "python")
        }
        assert all(row["version"] == 1 for row in rows)

    async def test_the_structure_holds_for_more_than_a_handful(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        """Nothing here is limited to two or three applications."""
        await create_resume_history(session, user)
        kinds = ["dotnet", "fullstack", "python", "engineering"] * 3
        for index, kind in enumerate(kinds):
            application = await application_for(session, user, kind)
            body = await adapt(client, auth_headers, application.id)
            assert body["application_id"] == application.id, f"application {index}"

        rows = (await client.get(VERSIONS, headers=auth_headers)).json()
        assert len(rows) == len(kinds)
        assert len({row["application_id"] for row in rows}) == len(kinds)


class TestIsolation:
    async def test_editing_the_master_leaves_an_existing_copy_untouched(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        """The rule a snapshot exists to enforce."""
        await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")
        before = await adapt(client, auth_headers, application.id)

        added = await client.post(
            EXPERIENCES,
            headers=auth_headers,
            json={
                "company": "Nova Empresa",
                "role": "Arquiteto de Solucoes",
                "started_on": "2015-01-01",
                "ended_on": "2016-01-01",
                "technologies": ["Kubernetes", "Terraform"],
                "responsibilities": ["Operei clusters Kubernetes em producao."],
            },
        )
        assert added.status_code == 201, added.text

        url = APPLICATION.format(application_id=application.id)
        after = (await client.get(url, headers=auth_headers)).json()

        assert after["experiences"] == before["experiences"]
        assert after["version"] == before["version"]
        # It does report itself as derived from an older master, which is the
        # honest answer: stale is not the same as wrong.
        assert after["is_stale"] is True

    async def test_deleting_a_master_experience_leaves_an_existing_copy_untouched(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        rows = await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")
        before = await adapt(client, auth_headers, application.id)

        removed = await client.delete(f"{EXPERIENCES}/{rows[0].id}", headers=auth_headers)
        assert removed.status_code == 204

        url = APPLICATION.format(application_id=application.id)
        after = (await client.get(url, headers=auth_headers)).json()
        assert [item["company"] for item in after["experiences"]] == [
            item["company"] for item in before["experiences"]
        ]

    async def test_editing_one_application_does_not_touch_another(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        first = await application_for(session, user, "dotnet")
        second = await application_for(session, user, "python")
        await adapt(client, auth_headers, first.id)
        untouched = await adapt(client, auth_headers, second.id)

        edited = await client.patch(
            APPLICATION.format(application_id=first.id),
            headers=auth_headers,
            json={"headline": "Especialista backend .NET", "skills": ["C#", ".NET"]},
        )
        assert edited.status_code == 200, edited.text

        after = (
            await client.get(APPLICATION.format(application_id=second.id), headers=auth_headers)
        ).json()
        assert after["headline"] == untouched["headline"]
        assert after["skills"] == untouched["skills"]
        assert after["was_edited"] is False

    async def test_editing_an_application_does_not_touch_the_master(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")
        adapted = await adapt(client, auth_headers, application.id)
        master_before = (await client.get(MASTER, headers=auth_headers)).json()

        await client.patch(
            APPLICATION.format(application_id=application.id),
            headers=auth_headers,
            json={
                "headline": "Reescrito para esta vaga",
                "experiences": [
                    {
                        "summary": "Reescrito.",
                        "responsibilities": ["Somente uma linha."],
                        "technologies": ["C#"],
                        "results": [],
                    }
                    for _ in adapted["experiences"]
                ],
            },
        )

        master_after = (await client.get(MASTER, headers=auth_headers)).json()
        assert master_after == master_before

    async def test_a_user_cannot_read_or_adapt_another_users_application(
        self,
        client: AsyncClient,
        session: AsyncSession,
        auth_headers: dict[str, str],
        other_auth_headers: dict[str, str],
        user: Any,
    ) -> None:
        await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")
        await adapt(client, auth_headers, application.id)

        url = APPLICATION.format(application_id=application.id)
        assert (await client.get(url, headers=other_auth_headers)).status_code == 404
        assert (await client.post(url, headers=other_auth_headers)).status_code == 404
        assert (
            await client.patch(url, headers=other_auth_headers, json={"headline": "nao"})
        ).status_code == 404

    async def test_the_version_list_only_shows_your_own(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        await adapt(client, auth_headers, (await application_for(session, user, "dotnet")).id)

        stranger = await create_user(session, email="stranger@example.com")
        stranger_headers = {"Authorization": f"Bearer {create_access_token(stranger.id)}"}

        assert (await client.get(VERSIONS, headers=stranger_headers)).json() == []

    async def test_the_endpoints_require_authentication(
        self, client: AsyncClient, session: AsyncSession, user: Any
    ) -> None:
        application = await application_for(session, user, "dotnet")
        url = APPLICATION.format(application_id=application.id)

        assert (await client.get(MASTER)).status_code == 401
        assert (await client.get(VERSIONS)).status_code == 401
        assert (await client.get(url)).status_code == 401
        assert (await client.post(url)).status_code == 401


class TestEditingACopy:
    async def test_edits_are_saved_and_flagged(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")
        await adapt(client, auth_headers, application.id)

        response = await client.patch(
            APPLICATION.format(application_id=application.id),
            headers=auth_headers,
            json={"summary": "Resumo escrito para esta vaga.", "skills": ["C#", ".NET", "SQL"]},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["summary"] == "Resumo escrito para esta vaga."
        assert body["skills"] == ["C#", ".NET", "SQL"]
        assert body["was_edited"] is True

    async def test_an_experience_edit_keeps_the_identity_and_the_report(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        """The reviewer rewrites text; they do not get to invent an employer."""
        await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")
        adapted = await adapt(client, auth_headers, application.id)

        response = await client.patch(
            APPLICATION.format(application_id=application.id),
            headers=auth_headers,
            json={
                "experiences": [
                    {
                        "summary": f"Reescrito {index}.",
                        "responsibilities": ["Uma linha só."],
                        "technologies": item["technologies"],
                        "results": item["results"],
                    }
                    for index, item in enumerate(adapted["experiences"])
                ]
            },
        )

        assert response.status_code == 200, response.text
        edited = response.json()["experiences"]
        assert [item["company"] for item in edited] == [
            item["company"] for item in adapted["experiences"]
        ]
        assert [item["relevance"] for item in edited] == [
            item["relevance"] for item in adapted["experiences"]
        ]
        assert edited[0]["summary"] == "Reescrito 0."
        assert edited[0]["responsibilities"] == ["Uma linha só."]

    async def test_a_stale_editor_is_rejected_rather_than_misapplied(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        """Positional merge with the wrong length would reassign one job's bullets."""
        await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")
        await adapt(client, auth_headers, application.id)

        response = await client.patch(
            APPLICATION.format(application_id=application.id),
            headers=auth_headers,
            json={
                "experiences": [
                    {"summary": "só uma", "responsibilities": [], "technologies": [], "results": []}
                ]
            },
        )

        assert response.status_code == 422

    async def test_patching_before_adapting_is_404(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        application = await application_for(session, user, "dotnet")

        response = await client.patch(
            APPLICATION.format(application_id=application.id),
            headers=auth_headers,
            json={"headline": "qualquer"},
        )

        assert response.status_code == 404


class TestAdaptingAgain:
    async def test_it_bumps_the_version_without_creating_a_second_row(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")
        await adapt(client, auth_headers, application.id)

        again = await adapt(client, auth_headers, application.id)

        assert again["version"] == 2
        count = await session.scalar(
            select(func.count())
            .select_from(ApplicationResume)
            .where(ApplicationResume.application_id == application.id)
        )
        assert count == 1

    async def test_it_replaces_the_edits_and_clears_the_stale_flag(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        """Asking for a fresh derivation is asking to discard the hand edits."""
        await create_resume_history(session, user)
        application = await application_for(session, user, "dotnet")
        await adapt(client, auth_headers, application.id)
        await client.patch(
            APPLICATION.format(application_id=application.id),
            headers=auth_headers,
            json={"headline": "editado a mao"},
        )
        await client.post(
            EXPERIENCES,
            headers=auth_headers,
            json={"company": "Outra", "role": "Dev", "technologies": ["Rust"]},
        )

        again = await adapt(client, auth_headers, application.id)

        assert again["headline"] != "editado a mao"
        assert again["was_edited"] is False
        assert again["is_stale"] is False
        assert len(again["experiences"]) == 5

    async def test_it_leaves_every_sibling_alone(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        first = await application_for(session, user, "dotnet")
        second = await application_for(session, user, "fullstack")
        await adapt(client, auth_headers, first.id)
        before = await adapt(client, auth_headers, second.id)

        await adapt(client, auth_headers, first.id)

        after = (
            await client.get(APPLICATION.format(application_id=second.id), headers=auth_headers)
        ).json()
        assert after["version"] == before["version"] == 1
        assert after["experiences"] == before["experiences"]


class TestTheMasterResume:
    async def test_it_returns_the_profile_and_the_positions(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)

        response = await client.get(MASTER, headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["experiences"]) == 4
        assert body["experiences"][0]["company"] == "Globalthings"
        assert body["experiences"][0]["is_current"] is True
        assert body["fingerprint"]

    async def test_its_fingerprint_moves_when_a_position_changes(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        rows = await create_resume_history(session, user)
        before = (await client.get(MASTER, headers=auth_headers)).json()["fingerprint"]

        await client.patch(
            f"{EXPERIENCES}/{rows[0].id}",
            headers=auth_headers,
            json={"summary": "Reescrevi o resumo desta experiencia."},
        )

        after = (await client.get(MASTER, headers=auth_headers)).json()["fingerprint"]
        assert after != before


class TestExperienceCrud:
    async def test_a_position_can_be_added_read_edited_and_removed(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        created = await client.post(
            EXPERIENCES,
            headers=auth_headers,
            json={
                "company": "Globalthings",
                "role": "Engenheiro de Software",
                "started_on": "2022-03-01",
                "is_current": True,
                "responsibilities": ["Mantive APIs em C#.", "  "],
                "technologies": ["C#", ".NET", ""],
                "results": ["Reduzi a latencia em 70%."],
                "projects": [
                    {
                        "name": "Gerenciador de Acessos",
                        "description": "Portal interno.",
                        "technologies": ["C#", "React"],
                    }
                ],
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        # Blank lines the editor leaves behind are dropped, not persisted.
        assert body["responsibilities"] == ["Mantive APIs em C#."]
        assert body["technologies"] == ["C#", ".NET"]
        assert body["projects"][0]["name"] == "Gerenciador de Acessos"

        listed = await client.get(EXPERIENCES, headers=auth_headers)
        assert [item["id"] for item in listed.json()] == [body["id"]]

        patched = await client.patch(
            f"{EXPERIENCES}/{body['id']}", headers=auth_headers, json={"role": "Tech Lead"}
        )
        assert patched.status_code == 200
        assert patched.json()["role"] == "Tech Lead"
        assert patched.json()["company"] == "Globalthings"

        assert (
            await client.delete(f"{EXPERIENCES}/{body['id']}", headers=auth_headers)
        ).status_code == 204
        assert (await client.get(EXPERIENCES, headers=auth_headers)).json() == []

    async def test_a_backwards_period_is_rejected(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        response = await client.post(
            EXPERIENCES,
            headers=auth_headers,
            json={
                "company": "Globalthings",
                "role": "Dev",
                "started_on": "2022-01-01",
                "ended_on": "2021-01-01",
            },
        )

        assert response.status_code == 422

    async def test_a_current_position_cannot_have_an_end_date(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        response = await client.post(
            EXPERIENCES,
            headers=auth_headers,
            json={
                "company": "Globalthings",
                "role": "Dev",
                "started_on": "2022-01-01",
                "ended_on": "2023-01-01",
                "is_current": True,
            },
        )

        assert response.status_code == 422

    async def test_a_partial_edit_that_would_break_the_period_is_rejected(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        """The merged row is re-checked, not only the incoming fields."""
        rows = await create_resume_history(session, user)
        finished = next(row for row in rows if row.company == "Nuvem Retail")

        response = await client.patch(
            f"{EXPERIENCES}/{finished.id}", headers=auth_headers, json={"is_current": True}
        )

        assert response.status_code == 422

    async def test_a_user_cannot_touch_another_users_position(
        self,
        client: AsyncClient,
        session: AsyncSession,
        other_auth_headers: dict[str, str],
        user: Any,
    ) -> None:
        rows = await create_resume_history(session, user)
        url = f"{EXPERIENCES}/{rows[0].id}"

        assert (
            await client.patch(url, headers=other_auth_headers, json={"role": "Invasor"})
        ).status_code == 404
        assert (await client.delete(url, headers=other_auth_headers)).status_code == 404


class TestAutomaticDerivationOnCreation:
    async def test_a_prepared_application_already_carries_its_resume(
        self, session: AsyncSession, automation_engine: Any, client: AsyncClient
    ) -> None:
        """A new application uses the master resume as it stands *now*.

        Deriving at creation rather than on first read is what pins the copy to
        that day's master: an edit tomorrow finds a document already written.
        """
        user = await create_user(
            session, email="autoderive@example.com", settings={"dry_run": True}
        )
        await create_resume_history(session, user)
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        job = await create_posting_job(session, user, "dotnet", status="analyzed", score=88)
        from tests.fixtures.factories import create_run

        run = await create_run(session, user, kind="prepare")

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        applications = (await client.get("/api/applications", headers=headers)).json()["items"]
        assert len(applications) == 1
        body = (
            await client.get(
                APPLICATION.format(application_id=applications[0]["id"]), headers=headers
            )
        ).json()
        assert body["experiences"][0]["company"] == "Globalthings"
        assert body["version"] == 1

    async def test_an_account_with_no_experience_still_gets_its_application(
        self, session: AsyncSession, automation_engine: Any
    ) -> None:
        """The derivation is a side effect and must never fail the main act."""
        user = await create_user(
            session,
            email="noexperience@example.com",
            profile={"resume_text": "", "skills": []},
            settings={"dry_run": True},
        )
        job = await create_posting_job(session, user, "dotnet", status="analyzed", score=88)
        from tests.fixtures.factories import create_run

        run = await create_run(session, user, kind="prepare")

        prepared = await automation_engine.prepare_applications(user.id, run.id, [job.id])

        assert len(prepared) == 1
        result = await session.execute(select(func.count()).select_from(ApplicationResume))
        assert result.scalar_one() == 0

    async def test_re_preparing_keeps_the_copy_the_user_edited(
        self, session: AsyncSession, automation_engine: Any, client: AsyncClient
    ) -> None:
        user = await create_user(session, email="reprepare@example.com", settings={"dry_run": True})
        await create_resume_history(session, user)
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        job = await create_posting_job(session, user, "dotnet", status="analyzed", score=88)
        from tests.fixtures.factories import create_run

        run = await create_run(session, user, kind="prepare")
        await automation_engine.prepare_applications(user.id, run.id, [job.id])
        applications = (await client.get("/api/applications", headers=headers)).json()["items"]
        application_id = applications[0]["id"]
        await client.patch(
            APPLICATION.format(application_id=application_id),
            headers=headers,
            json={"headline": "escrito a mao"},
        )

        second_run = await create_run(session, user, kind="prepare")
        await automation_engine.prepare_applications(user.id, second_run.id, [job.id])

        body = (
            await client.get(APPLICATION.format(application_id=application_id), headers=headers)
        ).json()
        assert body["headline"] == "escrito a mao"
        assert body["was_edited"] is True


class TestVersionList:
    async def test_it_reports_edited_and_stale_versions(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        edited = await application_for(session, user, "dotnet")
        untouched = await application_for(session, user, "python")
        await adapt(client, auth_headers, edited.id)
        await adapt(client, auth_headers, untouched.id)
        await client.patch(
            APPLICATION.format(application_id=edited.id),
            headers=auth_headers,
            json={"headline": "editado"},
        )

        rows = (await client.get(VERSIONS, headers=auth_headers)).json()
        by_application = {row["application_id"]: row for row in rows}

        assert by_application[edited.id]["was_edited"] is True
        assert by_application[untouched.id]["was_edited"] is False
        assert all(row["is_stale"] is False for row in rows)

    async def test_it_carries_the_application_status_so_versions_can_be_told_apart(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str], user: Any
    ) -> None:
        await create_resume_history(session, user)
        job = await create_posting_job(session, user, "dotnet")
        application = await create_application(
            session, user, job, status=ApplicationStatus.SUBMITTED
        )
        await adapt(client, auth_headers, application.id)

        rows = (await client.get(VERSIONS, headers=auth_headers)).json()

        assert rows[0]["application_status"] == "submitted"


class TestTheComparisonAgainstTheMaster:
    """Original versus this vacancy, and how few edits separate them.

    The feature's claim is that an adapted resume still reads as the same
    document. The change budget is what lets a reviewer check that in a glance
    instead of taking it on trust.
    """

    async def test_the_copy_reports_its_own_change_budget(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await seeded_user(session, "budget@example.com")
        job = await create_posting_job(session, user, "dotnet")
        application = await create_application(session, user, job)
        await session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

        await client.post(APPLICATION.format(application_id=application.id), headers=headers)
        body = (
            await client.get(APPLICATION.format(application_id=application.id), headers=headers)
        ).json()

        comparison = body["comparison"]
        assert comparison is not None
        assert comparison["is_comparable"] is True
        assert comparison["changes_total"] == (
            comparison["experiences_reordered"]
            + len(comparison["highlighted_technologies"])
            + comparison["sections_adjusted"]
        )

    async def test_a_moved_experience_says_where_it_came_from(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await seeded_user(session, "moved@example.com")
        job = await create_posting_job(session, user, "dotnet")
        application = await create_application(session, user, job)
        await session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

        await client.post(APPLICATION.format(application_id=application.id), headers=headers)
        body = (
            await client.get(APPLICATION.format(application_id=application.id), headers=headers)
        ).json()

        moves = body["comparison"]["moves"]
        assert moves, "the seeded history has several positions to order"
        for move in moves:
            assert move["from_position"] >= 1 and move["to_position"] >= 1
            assert move["company"]

    async def test_nothing_is_invented_and_it_is_measured(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await seeded_user(session, "clean@example.com")
        job = await create_posting_job(session, user, "fullstack")
        application = await create_application(session, user, job)
        await session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

        await client.post(APPLICATION.format(application_id=application.id), headers=headers)
        body = (
            await client.get(APPLICATION.format(application_id=application.id), headers=headers)
        ).json()

        assert body["comparison"]["invented"] == []
        assert body["comparison"]["is_clean"] is True

    async def test_a_stale_copy_declines_to_compare_rather_than_blaming_the_adaptation(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await seeded_user(session, "stale@example.com")
        job = await create_posting_job(session, user, "dotnet")
        application = await create_application(session, user, job)
        await session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

        await client.post(APPLICATION.format(application_id=application.id), headers=headers)
        # Editing the master is what makes the copy stale.
        await client.post(
            EXPERIENCES,
            headers=headers,
            json={"company": "Nova Empresa", "role": "Staff Engineer"},
        )

        body = (
            await client.get(APPLICATION.format(application_id=application.id), headers=headers)
        ).json()

        assert body["is_stale"] is True
        assert body["comparison"]["is_comparable"] is False
        assert body["comparison"]["moves"] == []
