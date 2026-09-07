"""The provider seam: schema tightening, structured-output degradation, refusals.

The behaviour under test is what makes a free provider usable in place of the
paid one. Three things are load-bearing and each has a test that fails loudly if
it regresses:

* A server that rejects strict JSON schema must still produce validated output,
  by falling back to JSON mode and then to prompt-only.
* A reply that cannot be validated must come back as an unparsed response, never
  as an exception — that is what preserves "the user reviews it by hand".
* A rate limit must be retryable and a bad request must not be, so the free
  tiers' 429s do not look like misconfiguration.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.ai.providers import (
    PRESETS,
    OpenAICompatProvider,
    ProviderNotConfiguredError,
    StubProvider,
    build_provider,
    describe_provider,
    json_schema_for,
)
from app.ai.providers.base import (
    STOP_END_TURN,
    ProviderError,
    ProviderTransientError,
)
from app.ai.providers.openai_compat import SchemaMode
from app.ai.schemas import DraftReview, JobScore, ScreeningAnswerSet, TailoredResume
from app.config import Settings

pytestmark = pytest.mark.anyio


# --------------------------------------------------------------------------- #
# Schema tightening
# --------------------------------------------------------------------------- #


def test_schema_marks_every_property_required() -> None:
    """Strict mode expresses optionality as null, never as an absent key."""
    schema = json_schema_for(JobScore)

    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False


def test_schema_tightens_nested_definitions() -> None:
    """`$defs` entries are objects too, and are rejected if left loose."""
    schema = json_schema_for(JobScore)
    definitions = schema["$defs"]

    assert definitions, "JobScore has nested models, so $defs must be present"
    for name, definition in definitions.items():
        if definition.get("type") == "object" or "properties" in definition:
            assert definition["additionalProperties"] is False, name
            assert set(definition["required"]) == set(definition["properties"]), name


def test_schema_strips_keywords_strict_mode_rejects() -> None:
    """`default`/`title` carry no constraint and make strict mode 400."""
    blob = json.dumps(json_schema_for(TailoredResume))

    assert '"default"' not in blob
    assert '"title"' not in blob


# --------------------------------------------------------------------------- #
# OpenAI-compatible transport
# --------------------------------------------------------------------------- #


def _provider(handler: Any, *, name: str = "groq") -> OpenAICompatProvider:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.test/v1"
    )
    return OpenAICompatProvider(
        base_url="https://example.test/v1",
        model="test-model",
        api_key="k",
        name=name,
        client=client,
    )


def _completion(content: str, *, finish_reason: str = "stop", **message: Any) -> dict[str, Any]:
    return {
        "model": "test-model",
        "choices": [
            {"finish_reason": finish_reason, "message": {"content": content, **message}}
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }


_VALID_SCORE = {
    "score": 81,
    "gates": [],
    "reasons": ["Stack overlap"],
    "missing_requirements": [],
    "breakdown": [],
    "recommend_apply": True,
    "summary": "Good fit.",
}


async def test_strict_schema_is_requested_first_and_parsed() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=_completion(json.dumps(_VALID_SCORE)))

    provider = _provider(handler)
    response = await provider.send(
        system="s", user_prompt="u", max_tokens=256, output_format=JobScore
    )
    await provider.aclose()

    assert seen[0]["response_format"]["type"] == "json_schema"
    assert seen[0]["response_format"]["json_schema"]["strict"] is True
    assert isinstance(response.parsed_output, JobScore)
    assert response.parsed_output.score == 81
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7
    assert response.stop_reason == STOP_END_TURN


async def test_falls_back_to_json_mode_when_strict_is_rejected() -> None:
    """A 400 on `json_schema` must not lose the call — Ollama does exactly this."""
    modes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        mode = (payload.get("response_format") or {}).get("type", "none")
        modes.append(mode)
        if mode == "json_schema":
            return httpx.Response(400, json={"error": {"message": "unsupported"}})
        return httpx.Response(200, json=_completion(json.dumps(_VALID_SCORE)))

    provider = _provider(handler)
    response = await provider.send(
        system="s", user_prompt="u", max_tokens=256, output_format=JobScore
    )

    assert modes == ["json_schema", "json_object"]
    assert isinstance(response.parsed_output, JobScore)

    # The downgrade is remembered, so the dead mode is not probed again.
    await provider.send(system="s", user_prompt="u", max_tokens=256, output_format=JobScore)
    await provider.aclose()
    assert modes == ["json_schema", "json_object", "json_object"]


async def test_falls_back_to_prompt_only_and_puts_the_schema_in_the_system_prompt() -> None:
    systems: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        systems.append(payload["messages"][0]["content"])
        if payload.get("response_format") is not None:
            return httpx.Response(400, json={"error": {"message": "no response_format"}})
        return httpx.Response(200, json=_completion(json.dumps(_VALID_SCORE)))

    provider = _provider(handler)
    response = await provider.send(
        system="BASE", user_prompt="u", max_tokens=256, output_format=JobScore
    )
    await provider.aclose()

    assert isinstance(response.parsed_output, JobScore)
    # Strict mode leaves the prompt alone; the fallbacks have to carry the schema.
    assert systems[0] == "BASE"
    assert "JSON Schema" in systems[-1]
    assert "recommend_apply" in systems[-1]


async def test_json_inside_a_markdown_fence_is_recovered() -> None:
    """Local models fence their JSON however firmly they are told not to."""
    fenced = f"Here you go:\n```json\n{json.dumps(_VALID_SCORE)}\n```\nHope that helps."

    provider = _provider(lambda _r: httpx.Response(200, json=_completion(fenced)))
    response = await provider.send(
        system="s", user_prompt="u", max_tokens=256, output_format=JobScore
    )
    await provider.aclose()

    assert isinstance(response.parsed_output, JobScore)
    assert response.parsed_output.score == 81


async def test_unvalidatable_output_is_reported_not_raised() -> None:
    """The caller's manual fallback depends on this being a normal return."""
    provider = _provider(lambda _r: httpx.Response(200, json=_completion("not json at all")))
    response = await provider.send(
        system="s", user_prompt="u", max_tokens=256, output_format=JobScore
    )
    await provider.aclose()

    assert response.parsed_output is None
    assert response.text == "not json at all"


async def test_explicit_refusal_field_becomes_a_refusal_response() -> None:
    provider = _provider(
        lambda _r: httpx.Response(
            200, json=_completion("", refusal="I can't help with that.")
        )
    )
    response = await provider.send(system="s", user_prompt="u", max_tokens=64)
    await provider.aclose()

    assert response.stop_reason == "refusal"
    assert response.stop_details is not None
    assert "can't help" in (response.stop_details.category or "")


async def test_content_filter_finish_reason_becomes_a_refusal() -> None:
    provider = _provider(
        lambda _r: httpx.Response(200, json=_completion("", finish_reason="content_filter"))
    )
    response = await provider.send(system="s", user_prompt="u", max_tokens=64)
    await provider.aclose()

    assert response.stop_reason == "refusal"
    assert response.stop_details is not None
    assert response.stop_details.category == "content_filter"


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_rate_limits_and_server_errors_are_retryable(status: int) -> None:
    """Free tiers 429 constantly; that has to read as transient, not as broken."""
    provider = _provider(lambda _r: httpx.Response(status, json={"error": "slow down"}))

    with pytest.raises(ProviderTransientError):
        await provider.send(system="s", user_prompt="u", max_tokens=64)
    await provider.aclose()


async def test_auth_failure_is_not_retryable() -> None:
    provider = _provider(lambda _r: httpx.Response(401, json={"error": {"message": "bad key"}}))

    with pytest.raises(ProviderError) as caught:
        await provider.send(system="s", user_prompt="u", max_tokens=64)
    await provider.aclose()

    assert not isinstance(caught.value, ProviderTransientError)
    assert "bad key" in str(caught.value)


async def test_transport_failure_is_transient() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = _provider(handler, name="ollama")

    with pytest.raises(ProviderTransientError) as caught:
        await provider.send(system="s", user_prompt="u", max_tokens=64)
    await provider.aclose()

    assert "unreachable" in str(caught.value)


async def test_every_structured_mode_rejected_is_an_error() -> None:
    """Exhausting all three modes is a real failure, not a silent empty answer."""
    provider = _provider(lambda _r: httpx.Response(400, json={"error": {"message": "nope"}}))

    with pytest.raises(ProviderError, match="structured-output mode"):
        await provider.send(
            system="s", user_prompt="u", max_tokens=64, output_format=ScreeningAnswerSet
        )
    await provider.aclose()


async def test_higher_effort_lowers_temperature() -> None:
    seen: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["temperature"])
        return httpx.Response(200, json=_completion("ok"))

    provider = _provider(handler)
    await provider.send(system="s", user_prompt="u", max_tokens=64, effort="low")
    await provider.send(system="s", user_prompt="u", max_tokens=64, effort="max")
    await provider.aclose()

    assert seen[0] > seen[1]


async def test_missing_base_url_or_model_is_a_configuration_error() -> None:
    with pytest.raises(ProviderNotConfiguredError, match="AI_BASE_URL"):
        OpenAICompatProvider(base_url="", model="m")
    with pytest.raises(ProviderNotConfiguredError, match="AI_MODEL"):
        OpenAICompatProvider(base_url="http://x/v1", model="")


# --------------------------------------------------------------------------- #
# Offline provider
# --------------------------------------------------------------------------- #


async def _score(stub: StubProvider, prompt: str) -> Any:
    return await stub.send(
        system="s", user_prompt=prompt, output_format=JobScore, max_tokens=64
    )


async def test_stub_scores_deterministically() -> None:
    stub = StubProvider()
    first = await _score(stub, "Backend Engineer")
    again = await _score(stub, "Backend Engineer")
    other = await _score(stub, "Data Analyst")

    assert isinstance(first.parsed_output, JobScore)
    assert isinstance(other.parsed_output, JobScore)
    assert first.parsed_output.score == again.parsed_output.score  # type: ignore[union-attr]
    # Not a constant: a suite needs a spread of scores to exercise thresholds.
    assert first.parsed_output.score != other.parsed_output.score


async def test_stub_breakdown_weights_sum_to_100() -> None:
    """The UI renders these as shares, so anything else is a broken chart."""
    stub = StubProvider()
    response = await stub.send(
        system="s", user_prompt="job", output_format=JobScore, max_tokens=64
    )

    score = response.parsed_output
    assert isinstance(score, JobScore)
    assert sum(dimension.weight_pct for dimension in score.breakdown) == 100


async def test_stub_score_can_be_pinned() -> None:
    stub = StubProvider(forced_score=91)
    response = await stub.send(
        system="s", user_prompt="anything", output_format=JobScore, max_tokens=64
    )

    assert isinstance(response.parsed_output, JobScore)
    assert response.parsed_output.score == 91
    assert response.parsed_output.recommend_apply is True


async def _screening(prompt: str) -> dict[str, Any]:
    response = await StubProvider().send(
        system="s", user_prompt=prompt, output_format=ScreeningAnswerSet, max_tokens=64
    )
    answers = response.parsed_output
    assert isinstance(answers, ScreeningAnswerSet)
    return {answer.question: answer for answer in answers.answers}


def _prompt_for(*questions: dict[str, Any]) -> str:
    """The shape `build_screening_prompt` emits: one JSON object per line."""
    lines = "\n".join(json.dumps(question, ensure_ascii=False) for question in questions)
    return f"=== QUESTIONS (one JSON object per line) ===\n{lines}\n"


async def test_stub_reads_the_prompts_real_question_format() -> None:
    """Parsing has to match `build_screening_prompt`, not a guess at it.

    A mismatch here does not fail loudly — it produces a run that drafted zero
    answers, which reads as "the AI had nothing to say".
    """
    by_question = await _screening(
        _prompt_for(
            {"index": 1, "question": "Years of Python experience?", "type": "number",
             "required": True},
            {"index": 2, "question": "Are you authorized to work in this country?",
             "type": "radio", "required": True, "options": ["Yes", "No"]},
        )
    )

    assert by_question["Years of Python experience?"].answer == "5"
    assert by_question["Are you authorized to work in this country?"].answer == "Yes"


async def test_stub_flags_questions_it_has_no_rule_for() -> None:
    """A stub that invented answers would make the review gate untestable."""
    by_question = await _screening(
        _prompt_for(
            {"index": 1, "question": "Years of Python experience?", "type": "number"},
            {"index": 2, "question": "What is your favourite colour?", "type": "text"},
        )
    )

    years = by_question["Years of Python experience?"]
    assert years.answer == "5"
    assert years.needs_review is False

    colour = by_question["What is your favourite colour?"]
    assert colour.answer == ""
    assert colour.needs_review is True


async def test_stub_refuses_an_answer_the_form_does_not_offer() -> None:
    """Choosing an option outside the list is the silent guess to avoid."""
    by_question = await _screening(
        _prompt_for(
            {
                "index": 1,
                "question": "Level of English",
                "type": "select",
                "options": ["Basic", "Intermediate"],
            }
        )
    )

    english = by_question["Level of English"]
    # The rule says "Advanced", which this form does not offer.
    assert english.answer == ""
    assert english.needs_review is True


async def test_stub_still_reads_bullet_questions() -> None:
    """Kept as a fallback so a prompt revision degrades loudly, not silently."""
    by_question = await _screening(
        "Questions:\n- [q-years] Years of Python experience? (number, required)\n"
    )

    assert by_question["Years of Python experience?"].answer == "5"


async def test_stub_answers_every_structured_capability() -> None:
    stub = StubProvider()
    for schema in (JobScore, ScreeningAnswerSet, TailoredResume, DraftReview):
        response = await stub.send(
            system="s", user_prompt="p", output_format=schema, max_tokens=64
        )
        assert isinstance(response.parsed_output, schema)


async def test_stub_writes_free_text_and_labels_itself() -> None:
    stub = StubProvider()
    letter = await stub.send(system="Write a cover letter", user_prompt="p", max_tokens=64)
    prep = await stub.send(system="Interview prep pack", user_prompt="p", max_tokens=64)

    assert "offline provider" in letter.text.lower()
    assert "Likely questions" in prep.text


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "ai_provider": "",
        "ai_api_key": "",
        "ai_base_url": "",
        "ai_model": "",
        "anthropic_api_key": "",
        "secret_key": "x",
        "encryption_key": "y",
    }
    return Settings(**{**base, **overrides})


def test_no_key_and_no_provider_resolves_to_the_offline_provider() -> None:
    """A fresh clone must run end to end without anyone signing up anywhere."""
    settings = _settings()

    assert settings.resolved_ai_provider == "stub"
    assert settings.ai_enabled is True
    assert isinstance(build_provider(settings), StubProvider)


def test_an_anthropic_key_alone_keeps_the_original_behaviour() -> None:
    settings = _settings(anthropic_api_key="sk-test")

    assert settings.resolved_ai_provider == "anthropic"
    assert describe_provider(settings) == "anthropic/claude-opus-5"


def test_explicit_provider_wins_over_a_present_anthropic_key() -> None:
    settings = _settings(ai_provider="ollama", anthropic_api_key="sk-test")

    assert settings.resolved_ai_provider == "ollama"
    provider = build_provider(settings)
    assert isinstance(provider, OpenAICompatProvider)
    assert provider.model == PRESETS["ollama"].model


def test_local_providers_need_no_key() -> None:
    for name in ("ollama", "llamacpp"):
        settings = _settings(ai_provider=name)
        assert settings.ai_enabled is True
        assert isinstance(build_provider(settings), OpenAICompatProvider)


@pytest.mark.parametrize("name", ["groq", "gemini", "openrouter", "cerebras"])
def test_hosted_providers_report_the_missing_key_and_where_to_get_one(name: str) -> None:
    settings = _settings(ai_provider=name)

    assert settings.ai_enabled is False
    with pytest.raises(ProviderNotConfiguredError) as caught:
        build_provider(settings)
    message = str(caught.value)
    assert "AI_API_KEY" in message
    assert "http" in message, "the error should say where to get a free key"


@pytest.mark.parametrize("name", ["groq", "gemini", "openrouter", "cerebras"])
def test_hosted_providers_are_usable_with_a_key(name: str) -> None:
    settings = _settings(ai_provider=name, ai_api_key="free-tier-key")

    assert settings.ai_enabled is True
    provider = build_provider(settings)
    assert isinstance(provider, OpenAICompatProvider)
    assert provider.name == name
    assert provider.model == PRESETS[name].model


def test_model_and_base_url_override_the_preset() -> None:
    settings = _settings(
        ai_provider="groq", ai_api_key="k", ai_model="custom-model", ai_base_url="http://x/v1"
    )
    provider = build_provider(settings)

    assert provider.model == "custom-model"
    assert describe_provider(settings) == "groq/custom-model"


def test_unknown_provider_names_itself_and_the_alternatives() -> None:
    settings = _settings(ai_provider="gpt5-please")

    with pytest.raises(ProviderNotConfiguredError) as caught:
        build_provider(settings)
    assert "gpt5-please" in str(caught.value)
    assert "ollama" in str(caught.value)


def test_stub_schema_mode_constants_are_ordered_most_to_least_capable() -> None:
    """`_modes_from` slices this order; reordering it would skip a fallback."""
    assert (SchemaMode.STRICT, SchemaMode.JSON_OBJECT, SchemaMode.PROMPT_ONLY) == (
        "json_schema",
        "json_object",
        "prompt_only",
    )
