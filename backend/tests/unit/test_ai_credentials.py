"""Whose key answers, and what happens when it cannot.

The rule this module exists to enforce is a quota rule: an account that brings
its own key spends its own free tier, and an account that brings none inherits
the deployment's. Everything below is a way of getting that wrong —
silently falling back to the shared key, accepting an endpoint the user chose,
or reporting "configured" for credentials that will fail on first use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.ai import credentials as ai_credentials
from app.ai.client import AINotConfiguredError, get_ai_client
from app.ai.providers import PRESETS, describe_provider
from app.auth.crypto import encrypt_text


@dataclass
class FakeSettingsRow:
    """The two columns plus the model override that `for_settings_row` reads."""

    ai_provider: str | None = None
    ai_api_key_encrypted: str | None = None
    ai_model: str | None = None


class TestWhatAnAccountMaySelect:
    def test_every_keyed_preset_is_selectable(self) -> None:
        keyed = {name for name, preset in PRESETS.items() if preset.requires_key}

        assert keyed <= ai_credentials.USER_SELECTABLE_PROVIDERS
        assert "anthropic" in ai_credentials.USER_SELECTABLE_PROVIDERS

    @pytest.mark.parametrize("provider", ["ollama", "llamacpp", "openai_compat", "stub"])
    def test_local_and_custom_endpoint_providers_are_not_selectable(
        self, provider: str
    ) -> None:
        """On a hosted install "localhost" is the server, and a user-supplied
        base URL is a request the server makes on the user's behalf. Both stay
        deployment-level."""
        assert provider not in ai_credentials.USER_SELECTABLE_PROVIDERS

        resolved = ai_credentials.for_account(provider, "any-key")

        assert resolved.enabled is False
        assert provider in resolved.reason

    def test_an_account_provider_never_carries_a_base_url(self) -> None:
        """The preset's compiled-in URL is the only endpoint reachable this way."""
        resolved = ai_credentials.for_account("groq", "gsk-test")

        assert resolved.ai_base_url == ""
        assert describe_provider(resolved).startswith("groq/")


class TestInheritingTheDeployment:
    def test_no_provider_means_the_deployment_answers(self) -> None:
        resolved = ai_credentials.for_settings_row(FakeSettingsRow())

        assert resolved.source == ai_credentials.DEPLOYMENT
        assert resolved.ai_provider == "anthropic"  # what conftest pins
        assert resolved.ai_enabled is True

    def test_a_model_override_survives_inheriting(self) -> None:
        """`ai_model` worked before accounts could bring a provider, and an
        upgrade that quietly dropped it would be a regression nobody sees until
        the bill arrives."""
        resolved = ai_credentials.for_settings_row(FakeSettingsRow(ai_model="claude-haiku-4-5"))

        assert resolved.source == ai_credentials.DEPLOYMENT
        assert describe_provider(resolved).endswith("/claude-haiku-4-5")

    def test_a_row_that_does_not_exist_yet_inherits_too(self) -> None:
        assert ai_credentials.for_settings_row(None).source == ai_credentials.DEPLOYMENT


class TestBringingAKey:
    def test_a_stored_key_is_decrypted_and_used(self) -> None:
        row = FakeSettingsRow(ai_provider="groq", ai_api_key_encrypted=encrypt_text("gsk-secret"))

        resolved = ai_credentials.for_settings_row(row)

        assert resolved.source == ai_credentials.ACCOUNT
        assert resolved.ai_enabled is True
        assert resolved.ai_api_key == "gsk-secret"

    def test_anthropic_keys_land_in_the_anthropic_field(self) -> None:
        """`build_provider` reads a different attribute for that path; putting
        the key in the wrong one would look configured and answer nothing."""
        row = FakeSettingsRow(
            ai_provider="anthropic", ai_api_key_encrypted=encrypt_text("sk-ant-secret")
        )

        resolved = ai_credentials.for_settings_row(row)

        assert resolved.anthropic_api_key == "sk-ant-secret"
        assert resolved.ai_api_key == ""

    def test_a_provider_with_no_key_is_disabled_and_says_where_to_get_one(self) -> None:
        resolved = ai_credentials.for_settings_row(FakeSettingsRow(ai_provider="groq"))

        assert resolved.enabled is False
        assert "console.groq.com" in resolved.reason


class TestFailingLoudly:
    def test_an_undecryptable_key_never_falls_back_to_the_shared_one(self) -> None:
        """The failure mode this guards is silent and expensive: an account
        whose key stopped decrypting would otherwise start spending the
        deployment's quota without anyone being told."""
        row = FakeSettingsRow(ai_provider="groq", ai_api_key_encrypted="not-a-fernet-token")

        resolved = ai_credentials.for_settings_row(row)

        assert resolved.source == ai_credentials.ACCOUNT
        assert resolved.enabled is False
        assert resolved.ai_api_key == ""
        assert resolved.anthropic_api_key == ""
        assert "decrypt" in resolved.reason.lower()

    def test_the_reason_reaches_the_caller_on_first_use(self) -> None:
        row = FakeSettingsRow(ai_provider="gemini")
        resolved = ai_credentials.for_settings_row(row)

        client = get_ai_client(credentials=resolved)

        assert client.is_configured is False
        with pytest.raises(AINotConfiguredError, match="gemini"):
            client._require_provider()

    def test_a_key_is_never_part_of_a_reason(self) -> None:
        """Reasons are rendered in the UI and written to logs."""
        secret = "gsk-do-not-print-me"
        row = FakeSettingsRow(ai_provider="groq", ai_api_key_encrypted=encrypt_text(secret))

        resolved = ai_credentials.for_settings_row(row)

        assert secret not in resolved.reason
        assert secret not in describe_provider(resolved)


class TestTheClientHonoursCredentials:
    def test_the_client_reports_whose_key_it_would_spend(self) -> None:
        row = FakeSettingsRow(ai_provider="groq", ai_api_key_encrypted=encrypt_text("gsk-x"))

        client = get_ai_client(credentials=ai_credentials.for_settings_row(row))

        assert client.credentials_source == ai_credentials.ACCOUNT
        assert client.provider_name.startswith("groq/")

    def test_a_client_with_no_credentials_still_reads_the_deployment(self) -> None:
        """Every existing caller passes none, and must keep working."""
        client = get_ai_client()

        assert client.credentials_source == ai_credentials.DEPLOYMENT
        assert client.is_configured is True

    def test_the_provider_built_from_account_credentials_is_the_selected_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        built: dict[str, Any] = {}

        def _capture(config: Any) -> Any:
            built["provider"] = config.resolved_ai_provider
            built["key"] = config.ai_api_key
            built["base_url"] = config.ai_base_url
            raise RuntimeError("stop here: the arguments are the assertion")

        monkeypatch.setattr("app.ai.client.build_provider", _capture)
        row = FakeSettingsRow(
            ai_provider="cerebras", ai_api_key_encrypted=encrypt_text("csk-secret")
        )
        client = get_ai_client(credentials=ai_credentials.for_settings_row(row))

        with pytest.raises(RuntimeError):
            client._require_provider()

        assert built == {"provider": "cerebras", "key": "csk-secret", "base_url": ""}
