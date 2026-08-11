"""At-rest encryption of the LinkedIn session state."""

from __future__ import annotations

import os

import pytest

from app.auth import crypto
from app.auth.crypto import (
    DecryptionError,
    decrypt_json,
    decrypt_text,
    encrypt_json,
    encrypt_text,
)
from app.config import get_settings

STORAGE_STATE = {
    "cookies": [
        {"name": "li_at", "value": "AQEDAT-secret-session-value", "domain": ".linkedin.com"}
    ],
    "origins": [],
}


class TestTextEncryption:
    def test_round_trips(self) -> None:
        assert decrypt_text(encrypt_text("li_at=AQEDAT")) == "li_at=AQEDAT"

    def test_ciphertext_does_not_contain_the_plaintext(self) -> None:
        token = encrypt_text("AQEDAT-secret-session-value")
        assert "AQEDAT-secret-session-value" not in token

    def test_is_nondeterministic(self) -> None:
        # Fernet uses a fresh IV per message; equal plaintexts must not be linkable.
        assert encrypt_text("same") != encrypt_text("same")

    def test_round_trips_unicode(self) -> None:
        assert decrypt_text(encrypt_text("acentuação — ok ✓")) == "acentuação — ok ✓"

    def test_round_trips_an_empty_string(self) -> None:
        assert decrypt_text(encrypt_text("")) == ""

    def test_rejects_a_corrupted_token(self) -> None:
        token = encrypt_text("li_at=AQEDAT")
        with pytest.raises(DecryptionError):
            decrypt_text(token[:-4] + "AAAA")

    def test_rejects_garbage(self) -> None:
        with pytest.raises(DecryptionError):
            decrypt_text("clearly-not-a-fernet-token")


class TestJsonEncryption:
    def test_round_trips_a_storage_state(self) -> None:
        assert decrypt_json(encrypt_json(STORAGE_STATE)) == STORAGE_STATE

    def test_cookie_values_are_not_readable_in_the_ciphertext(self) -> None:
        token = encrypt_json(STORAGE_STATE)
        assert "li_at" not in token
        assert "AQEDAT-secret-session-value" not in token

    def test_round_trips_a_list_at_the_root(self) -> None:
        assert decrypt_json(encrypt_json([1, "two", None])) == [1, "two", None]


class TestKeyRotation:
    def test_data_written_with_the_old_key_becomes_unreadable(self) -> None:
        """Rotating the key must fail loudly, not return garbage.

        The recovery path is for the user to reconnect their LinkedIn account, so
        the failure has to be an explicit `DecryptionError`.
        """
        token = encrypt_text("li_at=AQEDAT")
        previous = os.environ.get("ENCRYPTION_KEY")
        try:
            os.environ["ENCRYPTION_KEY"] = "a-completely-different-encryption-key"
            get_settings.cache_clear()
            crypto._fernet.cache_clear()
            with pytest.raises(DecryptionError):
                decrypt_text(token)
        finally:
            if previous is None:
                os.environ.pop("ENCRYPTION_KEY", None)
            else:
                os.environ["ENCRYPTION_KEY"] = previous
            get_settings.cache_clear()
            crypto._fernet.cache_clear()

        # Same key again: the original token reads back cleanly.
        assert decrypt_text(token) == "li_at=AQEDAT"

    def test_falls_back_to_the_secret_key_when_no_encryption_key_is_set(self) -> None:
        previous = os.environ.get("ENCRYPTION_KEY")
        try:
            os.environ["ENCRYPTION_KEY"] = ""
            get_settings.cache_clear()
            crypto._fernet.cache_clear()
            assert decrypt_text(encrypt_text("derived-from-secret-key")) == (
                "derived-from-secret-key"
            )
        finally:
            if previous is None:
                os.environ.pop("ENCRYPTION_KEY", None)
            else:
                os.environ["ENCRYPTION_KEY"] = previous
            get_settings.cache_clear()
            crypto._fernet.cache_clear()
