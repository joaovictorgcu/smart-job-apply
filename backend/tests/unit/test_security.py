"""Password hashing and JWT issuing/validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.auth.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.config import get_settings


class TestPasswordHashing:
    def test_verifies_the_original_password(self) -> None:
        hashed = hash_password("correct-horse-battery")
        assert verify_password("correct-horse-battery", hashed) is True

    def test_rejects_a_wrong_password(self) -> None:
        hashed = hash_password("correct-horse-battery")
        assert verify_password("correct-horse-batteru", hashed) is False

    def test_never_stores_the_plaintext(self) -> None:
        hashed = hash_password("correct-horse-battery")
        assert "correct-horse-battery" not in hashed
        assert hashed.startswith("$2")

    def test_is_salted_so_equal_passwords_hash_differently(self) -> None:
        first = hash_password("correct-horse-battery")
        second = hash_password("correct-horse-battery")
        assert first != second
        assert verify_password("correct-horse-battery", first)
        assert verify_password("correct-horse-battery", second)

    def test_rejects_a_password_past_the_bcrypt_limit(self) -> None:
        # Silently truncating at 72 bytes would make distinct passwords equivalent.
        with pytest.raises(ValueError, match="72 bytes"):
            hash_password("a" * 73)

    def test_verification_of_an_over_long_password_is_false_not_an_error(self) -> None:
        hashed = hash_password("a" * 72)
        assert verify_password("a" * 73, hashed) is False

    def test_multibyte_password_is_measured_in_bytes(self) -> None:
        # "é" is two bytes, so 40 of them exceed the limit only when counted right.
        assert verify_password("é" * 40, hash_password("é" * 36)) is False
        with pytest.raises(ValueError):
            hash_password("é" * 40)

    def test_verification_against_a_garbage_hash_is_false(self) -> None:
        assert verify_password("correct-horse-battery", "not-a-bcrypt-hash") is False
        assert verify_password("correct-horse-battery", "") is False


class TestAccessTokens:
    def test_round_trips_the_subject_as_a_string(self) -> None:
        payload = decode_access_token(create_access_token(42))
        assert payload["sub"] == "42"
        assert payload["type"] == "access"

    def test_carries_extra_claims(self) -> None:
        payload = decode_access_token(create_access_token(7, {"scope": "admin"}))
        assert payload["scope"] == "admin"

    def test_sets_an_expiry_from_the_configured_ttl(self) -> None:
        settings = get_settings()
        payload = decode_access_token(create_access_token(1))
        expires = datetime.fromtimestamp(payload["exp"], tz=UTC)
        expected = datetime.now(UTC) + timedelta(minutes=settings.access_token_ttl_minutes)
        assert abs((expires - expected).total_seconds()) < 60

    def test_rejects_garbage(self) -> None:
        with pytest.raises(TokenError):
            decode_access_token("not.a.token")

    def test_rejects_an_empty_token(self) -> None:
        with pytest.raises(TokenError):
            decode_access_token("")

    def test_rejects_an_expired_token(self) -> None:
        settings = get_settings()
        past = datetime.now(UTC) - timedelta(minutes=5)
        expired = jwt.encode(
            {"sub": "1", "type": "access", "exp": int(past.timestamp())},
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(TokenError):
            decode_access_token(expired)

    def test_rejects_a_token_signed_with_another_key(self) -> None:
        settings = get_settings()
        forged = jwt.encode(
            {
                "sub": "1",
                "type": "access",
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            "a-different-secret-entirely",
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(TokenError):
            decode_access_token(forged)

    def test_rejects_a_token_of_the_wrong_type(self) -> None:
        settings = get_settings()
        refresh = jwt.encode(
            {
                "sub": "1",
                "type": "refresh",
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(TokenError, match="token type"):
            decode_access_token(refresh)

    def test_rejects_a_token_without_a_subject(self) -> None:
        settings = get_settings()
        anonymous = jwt.encode(
            {
                "type": "access",
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(TokenError, match="subject"):
            decode_access_token(anonymous)
