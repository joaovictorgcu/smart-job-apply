"""Erasing an account, and everything it left behind.

This app holds a person's CV, the answers they give to screening questions and
an encrypted LinkedIn session. "Delete my account" therefore has to mean the
rows *and* the files — a cascade reaches the database and nothing else, and the
browser profile directory is where the session the user wants gone actually
lives.

The tests below are mostly about what must **not** happen: another account's
data disappearing alongside, a file surviving, a deletion going through on a
stolen token, or a rejected attempt leaving the account half-erased.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_access_token
from app.config import get_settings
from app.models import (
    Application,
    AuditEvent,
    Job,
    JobPreferences,
    LinkedInAccount,
    Profile,
    User,
    UserSettings,
)
from app.schemas.user import UserSettingsUpdate
from app.services import user_service
from tests.fixtures.factories import DEFAULT_PASSWORD, create_application, create_job, create_user

URL = "/api/users/me"


async def delete(client: AsyncClient, headers: dict[str, str], password: str) -> Any:
    """httpx's `.delete()` takes no body, and this endpoint requires one."""
    return await client.request("DELETE", URL, headers=headers, json={"password": password})


async def count(session: AsyncSession, model: Any, user_id: int) -> int:
    session.expunge_all()
    result = await session.execute(
        select(func.count()).select_from(model).where(model.user_id == user_id)
    )
    return int(result.scalar_one())


def write_account_files(user_id: int) -> dict[str, Path]:
    """The three shapes of file an account owns on disk."""
    settings = get_settings()
    resume = settings.resumes_dir / f"user_{user_id}_resume.pdf"
    rendered = settings.resumes_dir / f"user_{user_id}_application_3.pdf"
    resume.write_bytes(b"%PDF-1.4 cv")
    rendered.write_bytes(b"%PDF-1.4 adapted")
    profile_dir = settings.browser_profiles_dir / f"user_{user_id}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "Cookies").write_bytes(b"session")
    return {"resume": resume, "rendered": rendered, "profile_dir": profile_dir}


@pytest.fixture
async def populated(session: AsyncSession, user: Any) -> dict[str, Path]:
    """An account with rows in every table that hangs off it, plus its files."""
    job = await create_job(session, user)
    await create_application(session, user, job)
    # An audit row too: it is the table whose whole purpose is to be
    # append-only, which makes it the one most likely to be spared by accident.
    await user_service.update_settings(session, user, UserSettingsUpdate(daily_cap=11))
    session.add(JobPreferences(user_id=user.id, target_role="Backend"))
    await session.commit()
    return write_account_files(user.id)


class TestConfirmation:
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await delete(client, {}, DEFAULT_PASSWORD)).status_code == 401

    async def test_requires_the_password(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.request("DELETE", URL, headers=auth_headers, json={})

        assert response.status_code == 422

    async def test_a_wrong_password_deletes_nothing(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        populated: dict[str, Path],
    ) -> None:
        """A valid token is not enough. It outlives a shared machine, a copied
        curl and a screenshot, and this is the request that cannot be undone."""
        response = await delete(client, auth_headers, "not-the-password")

        assert response.status_code == 401
        session.expunge_all()
        assert await session.get(User, user.id) is not None
        assert populated["resume"].exists()
        assert populated["profile_dir"].exists()


class TestErasure:
    async def test_the_account_and_everything_under_it_is_gone(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        populated: dict[str, Path],
    ) -> None:
        user_id = user.id

        response = await delete(client, auth_headers, DEFAULT_PASSWORD)

        assert response.status_code == 204, response.text
        session.expunge_all()
        assert await session.get(User, user_id) is None
        for model in (
            Profile,
            UserSettings,
            JobPreferences,
            LinkedInAccount,
            Job,
            Application,
            AuditEvent,
        ):
            assert await count(session, model, user_id) == 0, model.__name__

    async def test_the_files_go_too(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        populated: dict[str, Path],
    ) -> None:
        """No cascade reaches these, and the browser profile is where the
        LinkedIn session the user wants gone actually lives."""
        assert (await delete(client, auth_headers, DEFAULT_PASSWORD)).status_code == 204

        assert not populated["resume"].exists()
        assert not populated["rendered"].exists()
        assert not populated["profile_dir"].exists()

    async def test_the_token_stops_working(
        self, client: AsyncClient, auth_headers: dict[str, str], populated: dict[str, Path]
    ) -> None:
        """There is no token blacklist; the account row simply is not there."""
        assert (await delete(client, auth_headers, DEFAULT_PASSWORD)).status_code == 204

        assert (await client.get("/api/profile", headers=auth_headers)).status_code == 401

    async def test_another_account_is_untouched(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        other_user: Any,
        auth_headers: dict[str, str],
        populated: dict[str, Path],
    ) -> None:
        job = await create_job(session, other_user)
        await session.commit()
        neighbour_files = write_account_files(other_user.id)

        assert (await delete(client, auth_headers, DEFAULT_PASSWORD)).status_code == 204

        session.expunge_all()
        assert await session.get(User, other_user.id) is not None
        assert await session.get(Job, job.id) is not None
        assert neighbour_files["resume"].exists()
        assert neighbour_files["profile_dir"].exists()


class TestTheGlobBoundary:
    """`user_1_` must not match `user_10_resume.pdf`.

    The prefix ends in an underscore precisely so it cannot, and the cost of
    getting this wrong is deleting nine other people's CVs — which no test would
    have caught without saying so out loud.
    """

    def test_a_prefix_never_swallows_a_longer_id(self, tmp_path: Path) -> None:
        settings = get_settings()
        mine = settings.resumes_dir / "user_1_resume.pdf"
        neighbour = settings.resumes_dir / "user_10_resume.pdf"
        deeper = settings.resumes_dir / "user_123_application_4.pdf"
        for path in (mine, neighbour, deeper):
            path.write_bytes(b"x")

        try:
            collected = set(user_service.account_file_paths(1))

            assert mine in collected
            assert neighbour not in collected
            assert deeper not in collected
        finally:
            for path in (mine, neighbour, deeper):
                path.unlink(missing_ok=True)


class TestPurgeIsBestEffort:
    async def test_a_file_that_will_not_delete_is_reported_not_raised(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The response has already been sent, and the rows are already gone.
        Turning a locked browser profile into an exception helps nobody."""
        stubborn = tmp_path / "locked.pdf"
        stubborn.write_bytes(b"x")

        def _refuse(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("file is in use by another process")

        monkeypatch.setattr(Path, "unlink", _refuse)

        await user_service.purge_account_files([stubborn])  # must not raise


class TestAnAccountCanStartOver:
    async def test_the_email_is_free_again_afterwards(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        populated: dict[str, Path],
    ) -> None:
        """The deletion is real, not a disabled flag: the address it held is
        available, and the new account starts empty."""
        email = user.email

        assert (await delete(client, auth_headers, DEFAULT_PASSWORD)).status_code == 204

        response = await client.post(
            "/api/auth/register", json={"email": email, "password": "a-brand-new-password"}
        )

        assert response.status_code == 201, response.text
        fresh_id = response.json()["user"]["id"]
        session.expunge_all()
        assert await count(session, Job, fresh_id) == 0

    async def test_a_reused_id_does_not_inherit_a_dead_account(
        self, session: AsyncSession, client: AsyncClient
    ) -> None:
        """`profiles.user_id` is UNIQUE and SQLite hands out the lowest free
        rowid, so an orphaned profile is not merely a wasted row: the next
        account to be given that id collides with it and registration fails.
        This is the failure the foreign-key pragma exists to prevent, asserted
        from the outside rather than from the pragma."""
        first = await create_user(session, email="short-lived@example.com")
        await session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(first.id)}"}

        assert (await delete(client, headers, DEFAULT_PASSWORD)).status_code == 204

        response = await client.post(
            "/api/auth/register",
            json={"email": "newcomer@example.com", "password": "a-brand-new-password"},
        )

        assert response.status_code == 201, response.text
        # Exactly one, and it belongs to the account that just registered: two
        # would mean the dead account's profile was still there.
        assert await count(session, Profile, response.json()["user"]["id"]) == 1
