"""A key the provider rejects has to reach the user, not the log.

`scoring.py` degrades almost every AI failure into a refusal, and that is right:
a model that declines to answer should leave the user writing the letter by
hand rather than staring at an error page. A **rejected credential** is the one
failure where that kindness backfires — the call can never succeed, so the app
reports a cheerful 200 with whatever score the job already carried, and an
expired key looks exactly like a working one.

These tests pin the seam that tells the two apart.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.ai.client import AIClient
from app.ai.providers.base import (
    ProviderError,
    ProviderNotConfiguredError,
    ProviderTransientError,
)


class _Rejecting:
    """A provider whose credentials the upstream API refuses."""

    name = "anthropic"
    model = "claude-opus-5"

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    async def send(self, **_kwargs: Any) -> Any:
        self.calls += 1
        raise self._error

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        return None


def _client(provider: Any) -> AIClient:
    client = AIClient()
    # The provider seam, not the settings: what is under test is how a failure
    # from `send` is classified, whatever produced it.
    client._provider = provider
    return client


class TestTranslation:
    async def test_a_rejected_key_becomes_a_configuration_error(self) -> None:
        from app.ai import AINotConfiguredError

        provider = _Rejecting(ProviderNotConfiguredError("The API rejected this key."))
        client = _client(provider)

        with pytest.raises(AINotConfiguredError) as raised:
            await client._send(system="s", user_prompt="u", max_tokens=16, effort=None)

        # The message has to name the problem: this is what the user reads.
        assert "rejected this key" in str(raised.value)

    async def test_it_is_not_retried(self) -> None:
        """No amount of waiting makes a refused credential work."""
        from app.ai import AINotConfiguredError

        provider = _Rejecting(ProviderNotConfiguredError("nope"))
        client = _client(provider)

        with pytest.raises(AINotConfiguredError):
            await client._send(system="s", user_prompt="u", max_tokens=16, effort=None)

        assert provider.calls == 1

    async def test_a_transient_failure_is_still_retried(self) -> None:
        """The rate limits of the free tiers must keep their second chance."""
        provider = _Rejecting(ProviderTransientError("429"))
        client = _client(provider)

        with pytest.raises(ProviderError):
            await client._send(system="s", user_prompt="u", max_tokens=16, effort=None)

        assert provider.calls > 1


class TestAnthropicTranslation:
    def test_an_authentication_error_is_classified_as_configuration(self) -> None:
        anthropic = pytest.importorskip("anthropic")
        import httpx

        from app.ai.providers.anthropic_provider import _as_configuration_error

        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(401, request=request, json={"error": {"message": "bad key"}})
        error = anthropic.AuthenticationError(
            "API key is invalid.", response=response, body=None
        )

        translated = _as_configuration_error(error)

        assert isinstance(translated, ProviderNotConfiguredError)
        assert "ANTHROPIC_API_KEY" in str(translated)

    def test_anything_else_is_left_alone(self) -> None:
        """A translation that swallowed other failures would be worse than none."""
        from app.ai.providers.anthropic_provider import _as_configuration_error

        error = ValueError("something else entirely")
        assert _as_configuration_error(error) is error


class TestOpenAICompatTranslation:
    """The same rule on the path the free tiers actually use.

    Groq, Gemini, OpenRouter and Cerebras all answer through this provider, so a
    mistyped key there has to fail as loudly as a bad Anthropic one — otherwise
    the bug simply moves to whichever provider the deployment picked.
    """

    @pytest.mark.parametrize("status", [401, 403])
    async def test_a_refused_key_is_a_configuration_error(self, status: int) -> None:
        import httpx

        from app.ai.providers.openai_compat import OpenAICompatProvider

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"error": {"message": "Invalid API Key"}})

        provider = OpenAICompatProvider(
            name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key="wrong",
            model="llama-3.3-70b-versatile",
        )
        provider._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://api.groq.com/openai/v1",
        )

        with pytest.raises(ProviderNotConfiguredError) as raised:
            await provider.send(system="s", user_prompt="u", max_tokens=8)

        assert "AI_API_KEY" in str(raised.value)

    async def test_a_rate_limit_stays_retryable(self) -> None:
        """429 is an expected outcome on a free tier, not a broken key."""
        import httpx

        from app.ai.providers.openai_compat import OpenAICompatProvider

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "slow down"}})

        provider = OpenAICompatProvider(
            name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key="fine",
            model="llama-3.3-70b-versatile",
        )
        provider._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://api.groq.com/openai/v1",
        )

        with pytest.raises(ProviderTransientError):
            await provider.send(system="s", user_prompt="u", max_tokens=8)
