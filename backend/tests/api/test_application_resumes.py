"""One candidate, N applications, N resumes — through the API, end to end.

The scenario this file exists to prove: a person keeps one master resume, applies
to five different vacancies, and each application carries its own version of that
resume with its own emphasis. Editing one version touches nothing else, and
editing the master leaves every version already derived exactly as it was
reviewed.

Isolation is asserted rather than assumed, in both directions, because the whole
value of the feature is that a resume sent to one company cannot be rewritten by
something the user did afterwards for another.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApplicationStatus, TailoredResume
from tests.fixtures.factories import (
    create_application,
    create_demo_jobs,
    create_demo_user,
    create_job,
)

RESUME = "/api/applications/{application_id}/resume"


async def headers_for(user: Any) -> dict[str, str]:
    from app.auth.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def apply_to_all(
    session: AsyncSession, user: Any, client: AsyncClient, headers: dict[str, str], count: int = 5
) -> list[dict[str, Any]]:
    """Create `count` applications and derive each one's own resume version."""
    jobs = await create_demo_jobs(session, user, count)
    bodies: list[dict[str, Any]] = []
    for job in jobs:
        application = await create_application(session, user, job)
        response = await client.post(RESUME.format(application_id=application.id), headers=headers)
        assert response.status_code == 200, response.text
        bodies.append(response.json())
    return bodies


def lead_experience(body: dict[str, Any]) -> dict[str, Any]:
    return body["sections"]["experiences"][0]


def find_experience(body: dict[str, Any], company: str) -> dict[str, Any]:
    return next(
        entry for entry in body["sections"]["experiences"] if entry["company"] == company
    )


class TestTheMasterResume:
    """(1) The user has one master resume, and it is the source of every version."""

    async def test_the_profile_carries_the_structured_master_resume(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_demo_user(session)

        body = (await client.get("/api/profile", headers=await headers_for(user))).json()

        assert len(body["experiences"]) == 5
        assert len(body["projects"]) == 5
        assert body["education"] and body["certifications"]
        assert ".NET" in body["skills"] and "Python" in body["skills"]
        # Every experience carries the tagged highlights the derivation selects from.
        assert all(entry["highlights"] for entry in body["experiences"])


class TestOneVersionPerApplication:
    """(2)-(7) Each application gets its own version, and N of them coexist."""

    async def test_an_application_starts_with_no_version_and_then_has_one(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_demo_user(session)
        headers = await headers_for(user)
        job = (await create_demo_jobs(session, user, 1))[0]
        application = await create_application(session, user, job)

        # (2) The application exists before any resume is derived for it, and
        # asking for one is a plain 404 rather than an error state.
        assert (
            await client.get(RESUME.format(application_id=application.id), headers=headers)
        ).status_code == 404

        # (3) Deriving creates this application's own version.
        created = await client.post(
            RESUME.format(application_id=application.id), headers=headers
        )
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["application_id"] == application.id
        assert body["job_title"] == job.title
        assert body["content"].strip()
        assert body["sections"]["experiences"]
        assert body["focus"]["keywords"]

    async def test_a_second_application_gets_a_different_version(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """(4)-(5) Two applications, two versions, visibly not the same document."""
        user = await create_demo_user(session)
        headers = await headers_for(user)

        first, second = await apply_to_all(session, user, client, headers, count=2)

        assert first["application_id"] != second["application_id"]
        assert first["content"] != second["content"]
        assert first["focus"]["keywords"] != second["focus"]["keywords"]

    async def test_ten_applications_each_keep_their_own_version(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """(6)-(7) Nothing about this is limited to two — N applications, N rows."""
        user = await create_demo_user(session)
        headers = await headers_for(user)

        bodies = await apply_to_all(session, user, client, headers, count=10)

        assert len({body["application_id"] for body in bodies}) == 10
        stored = await session.scalar(
            select(func.count())
            .select_from(TailoredResume)
            .where(TailoredResume.user_id == user.id)
        )
        assert stored == 10
        # Every version still reads back as its own document.
        for body in bodies:
            fetched = await client.get(
                RESUME.format(application_id=body["application_id"]), headers=headers
            )
            assert fetched.status_code == 200
            assert fetched.json()["content"] == body["content"]


class TestDifferentJobsDifferentPersonalisation:
    """(8)-(10) The versions differ because the vacancies differ."""

    async def test_five_vacancies_produce_five_distinct_documents(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_demo_user(session)

        bodies = await apply_to_all(session, user, client, await headers_for(user))

        assert len({body["content"] for body in bodies}) == 5
        assert len({tuple(body["focus"]["keywords"]) for body in bodies}) == 5

    async def test_each_vacancy_leads_with_the_experience_that_fits_it(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_demo_user(session)

        dotnet, react, python, _engineer, apis = await apply_to_all(
            session, user, client, await headers_for(user)
        )

        assert lead_experience(dotnet)["company"] == "Globalthings"
        assert lead_experience(react)["company"] == "Cofre Digital"
        assert lead_experience(python)["company"] == "Nexdata"
        assert lead_experience(apis)["company"] == "Pagamentos Vertex"

    async def test_the_same_experience_is_described_differently_per_vacancy(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """(9) The requirement from the brief, asserted through the API."""
        user = await create_demo_user(session)

        dotnet, react, python, *_ = await apply_to_all(
            session, user, client, await headers_for(user)
        )

        for_dotnet = find_experience(dotnet, "Globalthings")
        for_react = find_experience(react, "Globalthings")
        for_python = find_experience(python, "Globalthings")

        assert for_dotnet["description"] != for_react["description"]
        assert for_react["description"] != for_python["description"]
        assert "ASP.NET Core" in for_dotnet["description"]
        assert "React" in for_react["description"]
        # And the identity of the entry never moves with the description.
        assert for_dotnet["company"] == for_react["company"] == "Globalthings"
        assert for_dotnet["period"] == for_react["period"]

    async def test_skills_are_prioritised_per_vacancy(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """(10) Reordered, never truncated: what is not promoted is still listed."""
        user = await create_demo_user(session)

        dotnet, react, python, engineer, _apis = await apply_to_all(
            session, user, client, await headers_for(user)
        )

        assert dotnet["sections"]["prioritized_skills"][0] == ".NET"
        assert react["sections"]["prioritized_skills"][0] == "React"
        assert python["sections"]["prioritized_skills"][0] == "Python"
        assert "Arquitetura de software" in engineer["sections"]["prioritized_skills"]
        # Nothing the user listed is lost, only moved.
        for body in (dotnet, react, python):
            sections = body["sections"]
            assert len(sections["prioritized_skills"]) + len(sections["other_skills"]) == 28

    async def test_relevant_projects_come_first_per_vacancy(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_demo_user(session)

        _dotnet, react, python, *_ = await apply_to_all(
            session, user, client, await headers_for(user)
        )

        assert react["sections"]["projects"][0]["name"] == "Design system interno"
        assert python["sections"]["projects"][0]["name"] == "Motor de conciliação financeira"


class TestIsolation:
    """(11)-(15) The guarantees that make N simultaneous applications safe."""

    async def test_deriving_versions_never_touches_the_master_resume(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """(11) Five derivations later, the profile is byte-for-byte what it was."""
        user = await create_demo_user(session)
        headers = await headers_for(user)
        before = (await client.get("/api/profile", headers=headers)).json()

        await apply_to_all(session, user, client, headers)

        after = (await client.get("/api/profile", headers=headers)).json()
        assert after == before

    async def test_editing_one_version_leaves_every_other_untouched(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """(12)-(13) Editing A does not change B; editing B does not change C."""
        user = await create_demo_user(session)
        headers = await headers_for(user)
        bodies = await apply_to_all(session, user, client, headers)
        original = {body["application_id"]: body["content"] for body in bodies}

        first, second, third = bodies[0], bodies[1], bodies[2]
        for target, text in ((first, "Versão A editada à mão."), (second, "Versão B editada.")):
            edited = await client.patch(
                RESUME.format(application_id=target["application_id"]),
                headers=headers,
                json={"content": text},
            )
            assert edited.status_code == 200, edited.text
            assert edited.json()["content"] == text
            assert edited.json()["was_edited"] is True

        # Everything not edited still reads back exactly as derived.
        for body in bodies[2:]:
            current = await client.get(
                RESUME.format(application_id=body["application_id"]), headers=headers
            )
            assert current.json()["content"] == original[body["application_id"]]
            assert current.json()["was_edited"] is False

        # And the two edits did not bleed into each other.
        reread_first = await client.get(
            RESUME.format(application_id=first["application_id"]), headers=headers
        )
        assert reread_first.json()["content"] == "Versão A editada à mão."
        reread_third = await client.get(
            RESUME.format(application_id=third["application_id"]), headers=headers
        )
        assert reread_third.json()["content"] == original[third["application_id"]]

    async def test_editing_the_master_resume_leaves_existing_versions_alone(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """(14) The isolation that matters most: a version already reviewed is frozen."""
        user = await create_demo_user(session)
        headers = await headers_for(user)
        bodies = await apply_to_all(session, user, client, headers, count=3)

        updated = await client.put(
            "/api/profile",
            headers=headers,
            json={
                "skills": ["Rust", "Go"],
                "experiences": [
                    {
                        "role": "Consultor",
                        "company": "Outra Empresa",
                        "start": "2024",
                        "end": "atual",
                        "summary": "Currículo principal completamente reescrito.",
                        "technologies": ["Rust"],
                        "highlights": [{"text": "Serviços em Rust.", "technologies": ["Rust"]}],
                    }
                ],
            },
        )
        assert updated.status_code == 200, updated.text

        for body in bodies:
            current = await client.get(
                RESUME.format(application_id=body["application_id"]), headers=headers
            )
            fetched = current.json()
            assert fetched["content"] == body["content"]
            assert fetched["sections"] == body["sections"]
            # The version is flagged as behind the master, never rewritten to match.
            assert fetched["is_stale"] is True
            assert "Rust" not in fetched["content"]

    async def test_a_new_application_uses_the_updated_master_resume(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """(15) Old versions stay put; the next one starts from today's master."""
        user = await create_demo_user(session)
        headers = await headers_for(user)
        await apply_to_all(session, user, client, headers, count=1)

        await client.put(
            "/api/profile",
            headers=headers,
            json={
                "skills": [".NET", "C#", "Kubernetes", "Terraform"],
                "experiences": [
                    {
                        "role": "Engenheiro de plataforma",
                        "company": "Nova Casa",
                        "start": "2024",
                        "end": "atual",
                        "summary": "Plataforma interna.",
                        "technologies": ["Kubernetes", "Terraform", ".NET"],
                        "highlights": [
                            {
                                "text": "Provisionamento com Terraform e Kubernetes.",
                                "technologies": ["Terraform", "Kubernetes"],
                            }
                        ],
                    }
                ],
            },
        )

        job = await create_job(
            session,
            user,
            title="Engenheiro de Plataforma",
            description="Buscamos experiência com Kubernetes e Terraform.",
        )
        application = await create_application(session, user, job)
        body = (
            await client.post(RESUME.format(application_id=application.id), headers=headers)
        ).json()

        assert body["sections"]["experiences"][0]["company"] == "Nova Casa"
        assert "Terraform" in body["focus"]["keywords"]
        # The requirement the old master could not back is now backed, and the
        # gap list says so by no longer listing it.
        assert "terraform" not in [item.casefold() for item in body["unsupported_requirements"]]

    async def test_versions_survive_a_reload(
        self, client: AsyncClient, session: AsyncSession, sessionmaker: Any
    ) -> None:
        """(16) Every version is persisted, not held in a request's memory.

        Read back through a session that never saw them written, which is what a
        reload actually is — an identity-map hit would prove nothing.
        """
        user = await create_demo_user(session)
        headers = await headers_for(user)
        bodies = await apply_to_all(session, user, client, headers)

        async with sessionmaker() as fresh:
            rows = (
                (
                    await fresh.execute(
                        select(TailoredResume)
                        .where(TailoredResume.user_id == user.id)
                        .order_by(TailoredResume.id)
                    )
                )
                .scalars()
                .all()
            )

            assert len(rows) == 5
            assert {row.content for row in rows} == {body["content"] for body in bodies}
            for row in rows:
                assert row.sections and row.focus and row.base_snapshot
                assert row.strategy == "deterministic"
                # The snapshot really is the master, not a pointer to it.
                assert len(row.base_snapshot["experiences"]) == 5

        # And the API serves them from the same place after the fact.
        for body in bodies:
            reread = await client.get(
                RESUME.format(application_id=body["application_id"]), headers=headers
            )
            assert reread.json()["sections"] == body["sections"]


class TestBackwardCompatibility:
    """(17)-(19) Nothing that worked before is allowed to stop working."""

    async def test_an_application_with_no_version_does_not_break(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """(17) The pre-feature application: a plain 404, then a version on request."""
        user = await create_demo_user(session)
        headers = await headers_for(user)
        job = (await create_demo_jobs(session, user, 1))[0]
        application = await create_application(session, user, job)

        missing = await client.get(RESUME.format(application_id=application.id), headers=headers)
        assert missing.status_code == 404
        assert "resume version" in missing.json()["detail"]

        # The detail screen itself is unaffected — it never depended on this.
        detail = await client.get(f"/api/applications/{application.id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["id"] == application.id

    async def test_a_version_derived_before_the_structure_existed_still_reads(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """A legacy row: content only, no sections, no focus, no snapshot."""
        user = await create_demo_user(session)
        headers = await headers_for(user)
        job = (await create_demo_jobs(session, user, 1))[0]
        application = await create_application(session, user, job)
        session.add(
            TailoredResume(
                user_id=user.id,
                job_id=job.id,
                content="# Currículo antigo\nTexto gerado antes desta feature.",
                strategy="ai",
            )
        )
        await session.commit()

        body = (
            await client.get(RESUME.format(application_id=application.id), headers=headers)
        ).json()

        assert body["content"].startswith("# Currículo antigo")
        # Absent rather than fabricated — the screen falls back to the content.
        assert body["sections"] is None
        assert body["focus"] is None
        assert body["strategy"] == "ai"

    async def test_the_job_scoped_tailoring_endpoint_is_unchanged(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """(18) The existing CV flow on the job screen keeps its own contract."""
        user = await create_demo_user(session)
        headers = await headers_for(user)
        job = (await create_demo_jobs(session, user, 1))[0]

        created = await client.post(f"/api/ai/tailor-cv/{job.id}", headers=headers)
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["job_id"] == job.id
        assert body["content"].strip()
        # Still the AI path, and now also carrying the derivation for the UI.
        assert body["strategy"] == "ai"
        assert body["sections"]["experiences"]

        fetched = await client.get(f"/api/ai/tailor-cv/{job.id}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["content"] == body["content"]

    async def test_the_two_entry_points_address_the_same_version(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """One resume per application, whichever screen the user reached it from."""
        user = await create_demo_user(session)
        headers = await headers_for(user)
        job = (await create_demo_jobs(session, user, 1))[0]
        application = await create_application(session, user, job)

        await client.post(RESUME.format(application_id=application.id), headers=headers)
        from_job = (await client.get(f"/api/ai/tailor-cv/{job.id}", headers=headers)).json()
        from_application = (
            await client.get(RESUME.format(application_id=application.id), headers=headers)
        ).json()

        assert from_job["content"] == from_application["content"]
        count = await session.scalar(
            select(func.count()).select_from(TailoredResume).where(TailoredResume.job_id == job.id)
        )
        assert count == 1

    async def test_the_application_review_flow_still_works(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """(19) Editing, approving and reading events are untouched by all this."""
        user = await create_demo_user(session)
        headers = await headers_for(user)
        job = (await create_demo_jobs(session, user, 1))[0]
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )
        await client.post(RESUME.format(application_id=application.id), headers=headers)

        edited = await client.patch(
            f"/api/applications/{application.id}",
            headers=headers,
            json={"cover_letter": "Carta revisada."},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["cover_letter"] == "Carta revisada."

        events = await client.get(f"/api/applications/{application.id}/events", headers=headers)
        assert events.status_code == 200

        listed = await client.get("/api/applications", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["total"] == 1


class TestStrategies:
    async def test_the_default_document_is_the_derivation_itself(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """No model call by default, so the document and the breakdown agree."""
        user = await create_demo_user(session)
        headers = await headers_for(user)
        job = (await create_demo_jobs(session, user, 1))[0]
        application = await create_application(session, user, job)

        body = (
            await client.post(RESUME.format(application_id=application.id), headers=headers)
        ).json()

        assert body["strategy"] == "deterministic"
        assert body["model"] is None
        # The leading experience of the breakdown leads the document too.
        assert lead_experience(body)["role"] in body["content"]

    async def test_asking_for_the_ai_wording_keeps_the_same_derivation(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_demo_user(session)
        headers = await headers_for(user)
        job = (await create_demo_jobs(session, user, 1))[0]
        application = await create_application(session, user, job)
        derived = (
            await client.post(RESUME.format(application_id=application.id), headers=headers)
        ).json()

        rewritten = await client.post(
            RESUME.format(application_id=application.id),
            headers=headers,
            json={"strategy": "ai"},
        )

        assert rewritten.status_code == 200, rewritten.text
        body = rewritten.json()
        assert body["strategy"] == "ai"
        assert body["model"]
        assert body["content"] != derived["content"]
        # The structure the screen explains is still the derivation's.
        assert body["sections"] == derived["sections"]
        assert body["focus"] == derived["focus"]

    async def test_a_refused_rewrite_leaves_the_derived_version_in_place(
        self, client: AsyncClient, session: AsyncSession, fake_ai: Any
    ) -> None:
        """A model refusal must not cost the user the version they already had."""
        user = await create_demo_user(session)
        headers = await headers_for(user)
        job = (await create_demo_jobs(session, user, 1))[0]
        application = await create_application(session, user, job)
        derived = (
            await client.post(RESUME.format(application_id=application.id), headers=headers)
        ).json()
        fake_ai.refused = True

        refused = await client.post(
            RESUME.format(application_id=application.id),
            headers=headers,
            json={"strategy": "ai"},
        )

        assert refused.status_code == 502
        current = await client.get(RESUME.format(application_id=application.id), headers=headers)
        assert current.json()["content"] == derived["content"]
        assert current.json()["strategy"] == "deterministic"

    async def test_a_profile_with_nothing_in_it_is_a_precondition_error(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        from tests.fixtures.factories import create_user

        empty = await create_user(
            session,
            email="empty@example.com",
            profile={"resume_text": "", "skills": [], "summary": "", "headline": ""},
        )
        headers = await headers_for(empty)
        job = await create_job(session, empty)
        application = await create_application(session, empty, job)

        response = await client.post(
            RESUME.format(application_id=application.id), headers=headers
        )

        assert response.status_code == 412


class TestAuthAndOwnership:
    async def test_every_endpoint_requires_authentication(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_demo_user(session)
        job = (await create_demo_jobs(session, user, 1))[0]
        application = await create_application(session, user, job)
        url = RESUME.format(application_id=application.id)

        assert (await client.get(url)).status_code == 401
        assert (await client.post(url)).status_code == 401
        assert (await client.patch(url, json={"content": "x"})).status_code == 401

    async def test_another_user_can_neither_read_nor_derive_nor_edit(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """Two users with applications of their own must not see each other's."""
        owner = await create_demo_user(session, email="owner-demo@example.com")
        intruder = await create_demo_user(session, email="intruder-demo@example.com")
        job = (await create_demo_jobs(session, owner, 1))[0]
        application = await create_application(session, owner, job)
        await client.post(
            RESUME.format(application_id=application.id), headers=await headers_for(owner)
        )
        headers = await headers_for(intruder)
        url = RESUME.format(application_id=application.id)

        assert (await client.get(url, headers=headers)).status_code == 404
        assert (await client.post(url, headers=headers)).status_code == 404
        assert (
            await client.patch(url, headers=headers, json={"content": "x"})
        ).status_code == 404
