"""Upload a resume, check what we found, save it.

The endpoints exist to remove a thirty-field form from the first five minutes of
using the app, so the assertions are about that shape: reading proposes and
never writes, applying writes only what came back, and the destructive option is
the one the caller had to ask for.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Experience, Profile

INTAKE = "/api/profile/intake"
APPLY = "/api/profile/intake/apply"
PROFILE = "/api/profile"
EXPERIENCES = "/api/profile/experiences"

RESUME_TEXT = """\
Ana Ribeiro
Desenvolvedora Backend
Recife, PE
ana@example.com

RESUMO
Desenvolvedora backend com foco em APIs Python e PostgreSQL.

EXPERIÊNCIA PROFISSIONAL
Desenvolvedora Backend — Acme Tecnologia
Mar 2022 - Presente
- Construí APIs em FastAPI consumidas por um app React.

TECNOLOGIAS
Python, FastAPI, PostgreSQL, Docker
"""


async def seed_resume_text(session: AsyncSession, user: Any, text: str = RESUME_TEXT) -> None:
    profile = await session.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:
        profile = Profile(user_id=user.id)
        session.add(profile)
    profile.resume_text = text
    await session.commit()


class TestReadingAProposal:
    async def test_reads_the_resume_text_already_on_the_profile(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await seed_resume_text(session, user)

        response = await client.post(INTAKE, headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["full_name"] == "Ana Ribeiro"
        assert body["headline"] == "Desenvolvedora Backend"
        assert body["email"] == "ana@example.com"
        assert len(body["experiences"]) == 1
        assert body["experiences"][0]["company"] == "Acme Tecnologia"
        assert "Python" in body["skills"]

    async def test_reading_writes_nothing_to_the_profile(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await seed_resume_text(session, user)
        before = (await client.get(PROFILE, headers=auth_headers)).json()

        response = await client.post(INTAKE, headers=auth_headers)

        # The proposal names a headline and skills the profile does not hold.
        assert response.json()["headline"] == "Desenvolvedora Backend"
        after = (await client.get(PROFILE, headers=auth_headers)).json()
        assert after == before, "reading a resume must not fill the profile in"
        positions = await session.scalar(
            select(func.count()).select_from(Experience).where(Experience.user_id == user.id)
        )
        assert positions == 0

    async def test_reading_with_no_resume_at_all_explains_itself(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await seed_resume_text(session, user, text="")

        response = await client.post(INTAKE, headers=auth_headers)

        assert response.status_code == 422
        assert "resume" in response.json()["detail"].lower()

    async def test_an_upload_is_stored_and_read_in_one_request(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        # A DOCX/PDF parser is not exercised here: `extract_resume_text` returns
        # None for an unreadable file, and the endpoint has to say so rather than
        # fail. The stored filename is the part that must still be right.
        response = await client.post(
            INTAKE,
            headers=auth_headers,
            files={"file": ("cv.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["resume_filename"] == f"user_{user.id}_resume.pdf"
        assert body["warnings"], "an unreadable file has to be reported, not returned empty"

    async def test_the_endpoint_requires_a_login(self, client: AsyncClient) -> None:
        assert (await client.post(INTAKE)).status_code == 401


class TestApplyingAProposal:
    async def test_saves_the_confirmed_fields_and_positions(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            APPLY,
            headers=auth_headers,
            json={
                "headline": "Desenvolvedora Backend",
                "location": "Recife, PE",
                "summary": "APIs Python e PostgreSQL.",
                "skills": ["Python", "PostgreSQL"],
                "resume_text": RESUME_TEXT,
                "experiences": [
                    {
                        "company": "Acme Tecnologia",
                        "role": "Desenvolvedora Backend",
                        "started_on": "2022-03-01",
                        "is_current": True,
                        "responsibilities": ["Construí APIs em FastAPI."],
                        "technologies": ["Python", "FastAPI"],
                    }
                ],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["experiences_created"] == 1
        assert body["experiences_removed"] == 0
        assert body["profile"]["headline"] == "Desenvolvedora Backend"

        listed = await client.get(EXPERIENCES, headers=auth_headers)
        assert [row["company"] for row in listed.json()] == ["Acme Tecnologia"]

    async def test_leaves_out_fields_alone(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await client.put(PROFILE, headers=auth_headers, json={"phone": "+55 81 99999-0000"})

        await client.post(APPLY, headers=auth_headers, json={"headline": "Backend"})

        profile = (await client.get(PROFILE, headers=auth_headers)).json()
        assert profile["phone"] == "+55 81 99999-0000"
        assert profile["headline"] == "Backend"

    async def test_positions_are_appended_unless_replacement_is_asked_for(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        first = {"company": "Acme", "role": "Dev"}
        second = {"company": "Globex", "role": "Dev"}

        await client.post(APPLY, headers=auth_headers, json={"experiences": [first]})
        await client.post(APPLY, headers=auth_headers, json={"experiences": [second]})

        listed = (await client.get(EXPERIENCES, headers=auth_headers)).json()
        assert {row["company"] for row in listed} == {"Acme", "Globex"}

    async def test_replacement_removes_only_this_account_s_positions(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        other_user: Any,
        auth_headers: dict[str, str],
        other_auth_headers: dict[str, str],
    ) -> None:
        await client.post(
            APPLY,
            headers=other_auth_headers,
            json={"experiences": [{"company": "Other", "role": "Dev"}]},
        )
        await client.post(
            APPLY, headers=auth_headers, json={"experiences": [{"company": "Acme", "role": "Dev"}]}
        )

        response = await client.post(
            APPLY,
            headers=auth_headers,
            json={
                "replace_experiences": True,
                "experiences": [{"company": "Globex", "role": "Dev"}],
            },
        )

        assert response.json()["experiences_removed"] == 1
        mine = (await client.get(EXPERIENCES, headers=auth_headers)).json()
        assert [row["company"] for row in mine] == ["Globex"]
        theirs = (await client.get(EXPERIENCES, headers=other_auth_headers)).json()
        assert [row["company"] for row in theirs] == ["Other"], "another account was touched"

    async def test_the_account_name_is_filled_in_only_when_it_is_blank(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        # The fixture user already has a name, so the proposal must not rewrite it.
        await client.post(APPLY, headers=auth_headers, json={"full_name": "Someone Else"})

        await session.refresh(user)
        assert user.full_name == "Owner User"

    async def test_a_position_with_no_company_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            APPLY, headers=auth_headers, json={"experiences": [{"company": "", "role": "Dev"}]}
        )

        assert response.status_code == 422
