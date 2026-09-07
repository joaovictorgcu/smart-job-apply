"""One user, four applications, four resumes — and none of them leaking.

These are the scenarios the feature exists for, driven through the API the way
the app drives it:

* four postings open at once, each application presenting a differently
  emphasized resume built from the same history;
* editing the master resume changes what the *next* application derives, and
  nothing that already exists;
* editing one application's resume changes that one only;
* the version survives a fresh read from the database.

The automation engine's own path is covered too, because it is the other door
that creates applications and therefore the other place that has to hand one
its resume.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_access_token
from app.models import AutomationRunKind, AutomationRunStatus, TailoredResume
from tests.automation import application_for_job
from tests.fixtures.factories import create_application, create_job, create_run, create_user
from tests.fixtures.fake_linkedin import FakeLinkedInService
from tests.fixtures.resumes import MASTER_PROFILE, POSTINGS

URL = "/api/applications/{application_id}/resume"


async def candidate(session: AsyncSession, email: str = "candidate@example.com") -> Any:
    return await create_user(session, email=email, profile=dict(MASTER_PROFILE))


async def application_for(session: AsyncSession, user: Any, posting: str) -> Any:
    job = await create_job(
        session,
        user,
        title=POSTINGS[posting]["title"],
        description=POSTINGS[posting]["description"],
    )
    return await create_application(session, user, job)


class TestManyApplicationsManyResumes:
    async def test_four_open_applications_carry_four_different_resumes(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await candidate(session)
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

        versions: dict[str, dict[str, Any]] = {}
        for posting in POSTINGS:
            application = await application_for(session, user, posting)
            versions[posting] = (
                await client.post(URL.format(application_id=application.id), headers=headers)
            ).json()

        leading = {
            posting: body["document"]["experiences"][0]["company"]
            for posting, body in versions.items()
        }
        assert leading["dotnet"] == "Globalthings"
        assert leading["fullstack"] == "Nexo Digital"
        assert leading["python"] == "DataLab"

        # Every version is a distinct document, and each one says what it is for.
        documents = [body["document"] for body in versions.values()]
        assert len({str(document) for document in documents}) == len(POSTINGS)
        for posting, body in versions.items():
            assert body["focus"], f"the {posting} posting produced no focus"

        # The same position, described differently in each application.
        summaries = {
            posting: next(
                experience["summary"]
                for experience in body["document"]["experiences"]
                if experience["key"] == "globalthings-tech-lead"
            )
            for posting, body in versions.items()
        }
        assert len(set(summaries.values())) == len(POSTINGS)

    async def test_editing_one_application_leaves_the_others_alone(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await candidate(session, "isolated@example.com")
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        first = await application_for(session, user, "dotnet")
        second = await application_for(session, user, "python")
        third = await application_for(session, user, "fullstack")
        for application in (first, second, third):
            await client.post(URL.format(application_id=application.id), headers=headers)
        before = {
            application.id: (
                await client.get(URL.format(application_id=application.id), headers=headers)
            ).json()["document"]
            for application in (second, third)
        }

        edited = deepcopy(before[second.id])
        document = (await client.get(URL.format(application_id=first.id), headers=headers)).json()[
            "document"
        ]
        document["summary"] = "Só a candidatura .NET tem esta frase."
        await client.patch(
            URL.format(application_id=first.id), headers=headers, json={"document": document}
        )

        for application in (second, third):
            after = (
                await client.get(URL.format(application_id=application.id), headers=headers)
            ).json()
            assert after["document"] == before[application.id]
            assert after["source"] == "rules"
            assert after["document"]["summary"] != "Só a candidatura .NET tem esta frase."
        assert edited == before[second.id]

    async def test_a_version_survives_a_fresh_read_from_the_database(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """What the API returns is what is stored, not something held in memory."""
        user = await candidate(session, "persisted@example.com")
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user, "apis")
        body = (
            await client.post(URL.format(application_id=application.id), headers=headers)
        ).json()

        row = (
            await session.execute(
                select(TailoredResume)
                .where(TailoredResume.job_id == application.job_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()

        assert (
            row.document["experiences"][0]["company"]
            == (body["document"]["experiences"][0]["company"])
        )
        assert row.base_document["experiences"], "the master snapshot is stored too"
        assert row.focus == body["focus"]
        assert row.document_source == "rules"


class TestTheMasterIsABaseNotALiveDependency:
    async def test_editing_the_master_does_not_change_an_existing_version(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await candidate(session, "base@example.com")
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        application = await application_for(session, user, "dotnet")
        before = (
            await client.post(URL.format(application_id=application.id), headers=headers)
        ).json()

        # A real profile edit: a new job replaces the whole history.
        await client.put(
            "/api/profile",
            headers=headers,
            json={
                "experiences": [
                    {
                        "company": "Empresa Nova",
                        "role": "Staff Engineer",
                        "start": "2026-01",
                        "summary": "Chegou depois de a candidatura existir.",
                        "technologies": [".NET 8"],
                        "highlights": [{"text": "Nada a ver com o passado.", "technologies": []}],
                    }
                ]
            },
        )

        after = (
            await client.get(URL.format(application_id=application.id), headers=headers)
        ).json()
        assert after["document"] == before["document"]
        assert [item["company"] for item in after["document"]["experiences"]] == [
            item["company"] for item in before["document"]["experiences"]
        ]
        assert "Empresa Nova" not in str(after["document"])
        # The snapshot is what makes that provable, and it is still the old one.
        assert "Empresa Nova" not in str(after["base_document"])
        assert after["is_stale"] is True

    async def test_a_new_application_starts_from_the_current_master(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await candidate(session, "fresh@example.com")
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        old = await application_for(session, user, "dotnet")
        await client.post(URL.format(application_id=old.id), headers=headers)

        await client.put(
            "/api/profile",
            headers=headers,
            json={
                "experiences": [
                    *MASTER_PROFILE["experiences"],
                    {
                        "company": "Consultoria Recente",
                        "role": "Arquiteto .NET",
                        "start": "2026-02",
                        "summary": "Trabalho novo, ainda não visto por candidatura nenhuma.",
                        "technologies": [".NET 8", "APIs REST"],
                        "highlights": [
                            {
                                "text": "Desenhou a malha de APIs REST em .NET 8.",
                                "technologies": [".NET 8", "APIs REST"],
                                "impact": "12 serviços sob um contrato só",
                            }
                        ],
                    },
                ]
            },
        )

        new_application = await application_for(session, user, "dotnet")
        fresh = (
            await client.post(URL.format(application_id=new_application.id), headers=headers)
        ).json()

        assert "Consultoria Recente" in str(fresh["document"])
        assert fresh["is_stale"] is False
        # And the older application still knows nothing about it.
        untouched = (await client.get(URL.format(application_id=old.id), headers=headers)).json()
        assert "Consultoria Recente" not in str(untouched["document"])


class TestTheEngineAlsoGivesAnApplicationItsResume:
    async def test_preparing_an_application_derives_its_version(
        self,
        session: AsyncSession,
        automation_engine: Any,
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        user = await candidate(session, "engine@example.com")
        job = await create_job(
            session,
            user,
            title=POSTINGS["fullstack"]["title"],
            description=POSTINGS["fullstack"]["description"],
        )
        run = await create_run(
            session, user, kind=AutomationRunKind.PREPARE, status=AutomationRunStatus.PENDING
        )

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        row = (
            await session.execute(
                select(TailoredResume)
                .where(TailoredResume.job_id == job.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert row.document["experiences"][0]["company"] == "Nexo Digital"
        assert "React" in row.focus

    async def test_re_preparing_keeps_the_version_the_user_edited(
        self,
        client: AsyncClient,
        session: AsyncSession,
        automation_engine: Any,
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        """Re-reading the form is no reason to throw away the user's wording."""
        user = await candidate(session, "reprepare@example.com")
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        job = await create_job(
            session,
            user,
            title=POSTINGS["python"]["title"],
            description=POSTINGS["python"]["description"],
        )
        run = await create_run(
            session, user, kind=AutomationRunKind.PREPARE, status=AutomationRunStatus.PENDING
        )
        await automation_engine.prepare_applications(user.id, run.id, [job.id])
        application = await application_for_job(session, job.id)
        assert application is not None

        version = (
            await client.get(URL.format(application_id=application.id), headers=headers)
        ).json()
        document = deepcopy(version["document"])
        document["summary"] = "Minha versão, escrita à mão."
        await client.patch(
            URL.format(application_id=application.id),
            headers=headers,
            json={"document": document},
        )

        second_run = await create_run(
            session, user, kind=AutomationRunKind.PREPARE, status=AutomationRunStatus.PENDING
        )
        await automation_engine.prepare_applications(user.id, second_run.id, [job.id])

        after = (
            await client.get(URL.format(application_id=application.id), headers=headers)
        ).json()
        assert after["document"]["summary"] == "Minha versão, escrita à mão."
        assert after["source"] == "user"
