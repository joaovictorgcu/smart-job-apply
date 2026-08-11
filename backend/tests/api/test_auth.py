"""Registration, login and identity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from jose import jwt

from app.config import get_settings
from tests.fixtures.factories import DEFAULT_PASSWORD

VALID = {
    "email": "newcomer@example.com",
    "password": "a-long-enough-password",
    "full_name": "New Comer",
}


class TestRegister:
    async def test_returns_a_token_and_the_new_user(self, client: AsyncClient) -> None:
        response = await client.post("/api/auth/register", json=VALID)

        assert response.status_code in (200, 201), response.text
        body = response.json()
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0
        assert body["user"]["email"] == VALID["email"]
        assert body["user"]["full_name"] == VALID["full_name"]

    async def test_never_echoes_the_password(self, client: AsyncClient) -> None:
        response = await client.post("/api/auth/register", json=VALID)

        assert VALID["password"] not in response.text
        assert "hashed_password" not in response.text

    async def test_the_returned_token_works_immediately(self, client: AsyncClient) -> None:
        token = (await client.post("/api/auth/register", json=VALID)).json()["access_token"]

        me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert me.status_code == 200
        assert me.json()["email"] == VALID["email"]

    async def test_a_duplicate_email_conflicts(
        self, client: AsyncClient, user: Any
    ) -> None:
        response = await client.post(
            "/api/auth/register",
            json={"email": user.email, "password": "another-long-password"},
        )

        assert response.status_code == 409, response.text

    async def test_the_duplicate_check_ignores_case(
        self, client: AsyncClient, user: Any
    ) -> None:
        response = await client.post(
            "/api/auth/register",
            json={"email": user.email.upper(), "password": "another-long-password"},
        )

        assert response.status_code == 409, response.text

    @pytest.mark.parametrize("password", ["short", "123456789", ""])
    async def test_rejects_a_password_below_the_minimum_length(
        self, client: AsyncClient, password: str
    ) -> None:
        response = await client.post(
            "/api/auth/register", json={"email": "shorty@example.com", "password": password}
        )

        assert response.status_code == 422, response.text

    async def test_rejects_a_password_past_the_bcrypt_limit(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/auth/register", json={"email": "toolong@example.com", "password": "a" * 100}
        )

        assert response.status_code == 422, response.text

    @pytest.mark.parametrize("email", ["not-an-email", "@example.com", ""])
    async def test_rejects_a_malformed_email(self, client: AsyncClient, email: str) -> None:
        response = await client.post(
            "/api/auth/register", json={"email": email, "password": "a-long-enough-password"}
        )

        assert response.status_code == 422, response.text


class TestLogin:
    async def test_returns_a_token_for_the_right_password(
        self, client: AsyncClient, user: Any
    ) -> None:
        response = await client.post(
            "/api/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
        )

        assert response.status_code == 200, response.text
        assert response.json()["access_token"]
        assert response.json()["user"]["id"] == user.id

    async def test_rejects_a_wrong_password(self, client: AsyncClient, user: Any) -> None:
        response = await client.post(
            "/api/auth/login", json={"email": user.email, "password": "not-the-password"}
        )

        assert response.status_code == 401, response.text

    async def test_an_unknown_email_looks_exactly_like_a_wrong_password(
        self, client: AsyncClient
    ) -> None:
        """Same status either way: the response must not confirm who has an account."""
        response = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "not-the-password"},
        )

        assert response.status_code == 401, response.text

    async def test_an_inactive_account_cannot_log_in(
        self, client: AsyncClient, session: Any
    ) -> None:
        from tests.fixtures.factories import create_user

        disabled = await create_user(session, email="disabled@example.com", is_active=False)

        response = await client.post(
            "/api/auth/login", json={"email": disabled.email, "password": DEFAULT_PASSWORD}
        )

        assert response.status_code in (401, 403), response.text


class TestMe:
    async def test_returns_the_authenticated_user(
        self, client: AsyncClient, user: Any, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/auth/me", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == user.id
        assert body["email"] == user.email
        assert "hashed_password" not in body

    async def test_requires_a_token(self, client: AsyncClient) -> None:
        assert (await client.get("/api/auth/me")).status_code == 401

    async def test_rejects_a_garbage_token(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/auth/me", headers={"Authorization": "Bearer not.a.real.token"}
        )

        assert response.status_code == 401

    async def test_rejects_a_missing_bearer_prefix(
        self, client: AsyncClient, user: Any
    ) -> None:
        from app.auth.security import create_access_token

        response = await client.get(
            "/api/auth/me", headers={"Authorization": create_access_token(user.id)}
        )

        assert response.status_code == 401

    async def test_rejects_an_expired_token(self, client: AsyncClient, user: Any) -> None:
        settings = get_settings()
        expired = jwt.encode(
            {
                "sub": str(user.id),
                "type": "access",
                "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
            },
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )

        response = await client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {expired}"}
        )

        assert response.status_code == 401

    async def test_rejects_a_token_signed_with_another_key(
        self, client: AsyncClient, user: Any
    ) -> None:
        forged = jwt.encode(
            {
                "sub": str(user.id),
                "type": "access",
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            "a-different-secret-entirely",
            algorithm=get_settings().jwt_algorithm,
        )

        response = await client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {forged}"}
        )

        assert response.status_code == 401

    async def test_rejects_a_token_for_a_deleted_user(self, client: AsyncClient) -> None:
        from app.auth.security import create_access_token

        response = await client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {create_access_token(999999)}"}
        )

        assert response.status_code == 401


class TestHealth:
    async def test_is_public(self, client: AsyncClient) -> None:
        response = await client.get("/api/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["version"]
