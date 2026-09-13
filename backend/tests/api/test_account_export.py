"""Leaving with what you put in.

The export is derived from the mappers rather than from a hand-written field
list, so the interesting tests are not "does it contain the resume" — it does,
by construction. They are the two edges of that decision: that a credential
cannot ride along on the automatic path, and that another account's rows cannot
either.

`TestNothingSecretCanRideAlong` is the one that matters most. It fails on the
day someone adds a column called `*_token` or `*_encrypted` without classifying
it, which is precisely the day the leak would otherwise ship.
"""

from __future__ import annotations

import json
from typing import Any

from httpx import AsyncClient
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.crypto import encrypt_json, encrypt_text
from app.models import Application, LinkedInAccount, User, UserSettings
from app.services import export_service, user_service
from tests.fixtures.factories import create_application, create_job

URL = "/api/users/me/export"

SECRET_KEY_VALUE = "gsk-this-must-never-be-exported"
SECRET_COOKIE_VALUE = "li_at-this-must-never-be-exported"


async def fetch(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.get(URL, headers=headers)
    assert response.status_code == 200, response.text
    return json.loads(response.text)


async def seed(session: AsyncSession, user: Any) -> None:
    """An account with something in most of the tables the export walks."""
    job = await create_job(session, user, score=88)
    await create_application(session, user, job)
    profile = await user_service.get_or_create_profile(session, user)
    profile.summary = "Sete anos entre backend e dados."
    profile.resume_text = "Python, FastAPI, PostgreSQL."
    settings_row = await user_service.get_or_create_settings(session, user)
    settings_row.ai_provider = "groq"
    settings_row.ai_api_key_encrypted = encrypt_text(SECRET_KEY_VALUE)
    # The factory already gives every account one; there is a UNIQUE on user_id.
    account = await user_service.get_linkedin_account(session, user)
    assert account is not None
    account.display_name = "João"
    account.encrypted_storage_state = encrypt_json({"cookies": [SECRET_COOKIE_VALUE]})
    await session.commit()


class TestTheFile:
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get(URL)).status_code == 401

    async def test_comes_back_as_a_named_download(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await seed(session, user)

        response = await client.get(URL, headers=auth_headers)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        disposition = response.headers["content-disposition"]
        assert disposition.startswith("attachment;")
        assert f"smart-job-apply-{user.id}-" in disposition

    async def test_carries_the_account_and_its_work(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await seed(session, user)

        payload = await fetch(client, auth_headers)

        assert payload["format_version"] == export_service.FORMAT_VERSION
        assert payload["account"]["email"] == user.email
        assert payload["data"]["profile"][0]["resume_text"] == "Python, FastAPI, PostgreSQL."
        assert payload["counts"]["jobs"] == 1
        assert payload["counts"]["applications"] == 1
        # Every table the exporter knows about is a key, even when empty: a
        # missing key reads as "we lost it", an empty list reads as "you had none".
        for section in export_service.SECTIONS:
            assert section.key in payload["data"], section.key

    async def test_says_what_it_does_not_contain(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        """An export that omits the PDFs without saying so reads as complete."""
        await seed(session, user)

        payload = await fetch(client, auth_headers)

        text = " ".join(payload["not_included"])
        assert "resume file" in text
        assert "credentials" in text

    async def test_enums_and_timestamps_are_readable(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        """The same spellings the API documentation uses, not `ApplicationStatus.X`."""
        await seed(session, user)

        payload = await fetch(client, auth_headers)

        application = payload["data"]["applications"][0]
        assert application["status"] == "awaiting_review"
        assert application["created_at"].startswith("20")
        assert "+00:00" in application["created_at"] or application["created_at"].endswith("Z")


class TestNothingSecretCanRideAlong:
    """The export is automatic; the withholding is not. This is what keeps it so."""

    def test_every_credential_shaped_column_is_classified(self) -> None:
        """Fails the day a `*_token` or `*_encrypted` column is added without a
        decision. The alternative is a leak that ships quietly, because the
        exporter reads the mapper and asks nobody."""
        unclassified: list[str] = []
        for section in (*export_service.SECTIONS, export_service._Section("account", User)):
            table = str(section.model.__tablename__)
            withheld = export_service.NEVER_EXPORT.get(table, frozenset())
            for column in inspect(section.model).columns:
                if not export_service.SECRET_COLUMN_PATTERN.search(column.key):
                    continue
                qualified = f"{table}.{column.key}"
                if column.key in withheld:
                    continue
                if qualified in export_service.REVIEWED_NOT_SECRET:
                    continue
                unclassified.append(qualified)

        assert unclassified == [], (
            "These columns look like credentials and nobody has classified them. "
            "Put them in NEVER_EXPORT, or in REVIEWED_NOT_SECRET if you have "
            f"looked and they are not secrets: {unclassified}"
        )

    def test_the_escape_hatch_only_covers_columns_that_exist(self) -> None:
        """A stale entry in `REVIEWED_NOT_SECRET` is a decision about a column
        that is gone, and it would silently clear a future column of the same
        name — which nobody would have reviewed."""
        real: set[str] = set()
        for section in (*export_service.SECTIONS, export_service._Section("account", User)):
            table = str(section.model.__tablename__)
            real.update(f"{table}.{column.key}" for column in inspect(section.model).columns)

        stale = export_service.REVIEWED_NOT_SECRET - real

        assert stale == set(), f"REVIEWED_NOT_SECRET names columns that no longer exist: {stale}"

    def test_the_three_known_secrets_are_withheld(self) -> None:
        assert "hashed_password" not in export_service.exportable_columns(User)
        assert "ai_api_key_encrypted" not in export_service.exportable_columns(UserSettings)
        assert "encrypted_storage_state" not in export_service.exportable_columns(LinkedInAccount)

    async def test_no_secret_value_appears_anywhere_in_the_file(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        """Asserted against the raw text, not the parsed tree: a secret nested
        somewhere nobody thought to look is still a secret in the file."""
        await seed(session, user)
        session.expunge_all()
        stored = await session.get(User, user.id)
        assert stored is not None

        raw = (await client.get(URL, headers=auth_headers)).text

        assert SECRET_KEY_VALUE not in raw
        assert SECRET_COOKIE_VALUE not in raw
        assert stored.hashed_password not in raw
        # Not even the ciphertext: it is still the session, and a key rotation
        # is not something the holder of the file has to wait for.
        assert "gAAAAA" not in raw

    async def test_the_linkedin_row_still_says_a_session_exists(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        """Withholding the cookies is not the same as pretending there was no
        connection: the metadata is the user's own history."""
        await seed(session, user)

        payload = await fetch(client, auth_headers)

        account = payload["data"]["linkedin_account"][0]
        assert account["display_name"] == "João"
        assert "encrypted_storage_state" not in account

    async def test_the_stored_ai_provider_is_exported_without_the_key(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await seed(session, user)

        payload = await fetch(client, auth_headers)

        assert payload["data"]["settings"][0]["ai_provider"] == "groq"
        assert "ai_api_key_encrypted" not in payload["data"]["settings"][0]


class TestScoping:
    async def test_another_account_is_not_in_the_file(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        other_user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        await seed(session, user)
        intruder_job = await create_job(session, other_user, title="Not Yours Ltd")
        await create_application(session, other_user, intruder_job)
        await session.commit()

        raw = (await client.get(URL, headers=auth_headers)).text
        payload = json.loads(raw)

        assert "Not Yours Ltd" not in raw
        assert payload["counts"]["jobs"] == 1
        assert payload["counts"]["applications"] == 1

    async def test_application_events_are_scoped_through_their_application(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        other_user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        """`application_events` is the one table with no `user_id` of its own,
        so it is the one place a scoping mistake would not be obvious."""
        await seed(session, user)
        intruder_job = await create_job(session, other_user)
        intruder_application = await create_application(session, other_user, intruder_job)
        await session.commit()

        payload = await fetch(client, auth_headers)

        exported_ids = {row["application_id"] for row in payload["data"]["application_events"]}
        assert intruder_application.id not in exported_ids
        mine = await session.execute(
            Application.__table__.select().where(Application.user_id == user.id)
        )
        assert exported_ids <= {row.id for row in mine}


class TestAnEmptyAccount:
    async def test_a_fresh_account_exports_an_empty_but_complete_file(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Nothing to export is a normal state, not an error."""
        payload = await fetch(client, auth_headers)

        assert payload["account"]["email"]
        assert all(isinstance(rows, list) for rows in payload["data"].values())
        assert payload["counts"]["jobs"] == 0
