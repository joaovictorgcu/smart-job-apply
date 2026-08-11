"""Scoring: the AI contract the app consumes, and the min-score gate.

The gate is the rule that turns a `JobScore` into a decision — apply, or skip with
a reason. Expected surface, resolved leniently:

    app/services/scoring.py:
        def should_apply(score: JobScore, min_score: int) -> bool
        def skip_reason(score: JobScore, min_score: int) -> str | None
"""

from __future__ import annotations

from typing import Any

import pytest

from app.ai.schemas import JobScore
from app.models.enums import AnswerConfidence
from tests import call_maybe_async, find_attr, missing
from tests.fixtures.factories import make_form_question
from tests.fixtures.fake_ai import FakeAIClient, FakeAIError

SCORING_MODULES = (
    "app.services.scoring",
    "app.ai.scoring",
    "app.services.jobs",
    "app.automation.scoring",
)

should_apply = find_attr(
    ("should_apply", "passes_threshold", "is_above_threshold", "meets_min_score"),
    *SCORING_MODULES,
)
skip_reason_for = find_attr(("skip_reason", "build_skip_reason"), *SCORING_MODULES)


class TestAIClientContract:
    """The fake stands in for Claude everywhere, so its contract is load-bearing."""

    async def test_scoring_returns_a_valid_job_score(self) -> None:
        result = await FakeAIClient(score=91).score_job()
        assert isinstance(result, JobScore)
        assert result.score == 91
        assert result.recommend_apply is True
        assert result.reasons

    async def test_scoring_is_deterministic(self) -> None:
        client = FakeAIClient(score=77)
        first = await client.score_job()
        second = await client.score_job()
        assert first.model_dump() == second.model_dump()
        assert client.call_count("score_job") == 2

    async def test_a_low_score_does_not_recommend_applying(self) -> None:
        result = await FakeAIClient(score=31).score_job()
        assert result.score == 31
        assert result.recommend_apply is False

    async def test_usage_is_recorded_for_every_call(self) -> None:
        client = FakeAIClient()
        await client.score_job()
        usage = client.usage()
        assert usage.model == client.model
        assert usage.input_tokens and usage.output_tokens
        assert usage.refused is False

    async def test_a_refusal_produces_no_content(self) -> None:
        analysis = await FakeAIClient(refused=True).analyze_job()
        assert analysis.refused is True
        assert analysis.refusal_reason
        assert analysis.cover_letter is None
        assert analysis.screening_answers == []

    async def test_a_refusal_is_recorded_in_usage(self) -> None:
        client = FakeAIClient(refused=True)
        await client.analyze_job()
        assert client.usage().refused is True

    async def test_low_confidence_answers_are_flagged_for_review(self) -> None:
        client = FakeAIClient(low_confidence=True)
        answers = await client.answer_screening_questions([make_form_question()])
        assert len(answers.answers) == 1
        answer = answers.answers[0]
        assert answer.confidence == AnswerConfidence.LOW
        assert answer.needs_review is True

    async def test_confident_answers_are_not_flagged(self) -> None:
        client = FakeAIClient()
        answers = await client.answer_screening_questions([make_form_question()])
        assert answers.answers[0].needs_review is False

    async def test_answers_carry_the_field_id_back_to_the_form(self) -> None:
        question = make_form_question(field_id="q-salary", label="Salary?", kind="text")
        answers = await FakeAIClient().answer_screening_questions([question])
        assert answers.answers[0].field_id == "q-salary"
        assert answers.answers[0].question == "Salary?"
        assert answers.answers[0].question_type == "text"

    async def test_a_transport_failure_raises(self) -> None:
        with pytest.raises(FakeAIError):
            await FakeAIClient(api_error=True).score_job()

    async def test_the_cover_letter_carries_its_language(self) -> None:
        letter = await FakeAIClient(language="pt-BR").generate_cover_letter()
        assert letter.language == "pt-BR"
        assert letter.content


@pytest.mark.xfail(should_apply is None, reason=missing("should_apply", *SCORING_MODULES))
class TestScoreGate:
    @pytest.mark.parametrize(
        ("score", "min_score", "expected"),
        [(70, 70, True), (71, 70, True), (100, 70, True), (69, 70, False), (0, 70, False)],
    )
    async def test_the_threshold_is_inclusive(
        self, score: int, min_score: int, expected: bool
    ) -> None:
        decision = await call_maybe_async(
            should_apply, JobScore(score=score, recommend_apply=True), min_score
        )
        assert bool(decision) is expected

    async def test_a_model_recommendation_does_not_override_the_threshold(self) -> None:
        """The user's minimum score wins over the model's enthusiasm."""
        decision = await call_maybe_async(
            should_apply, JobScore(score=40, recommend_apply=True), 70
        )
        assert bool(decision) is False


@pytest.mark.xfail(skip_reason_for is None, reason=missing("skip_reason", *SCORING_MODULES))
class TestSkipReason:
    async def test_a_passing_score_has_no_skip_reason(self) -> None:
        reason: Any = await call_maybe_async(
            skip_reason_for, JobScore(score=90, recommend_apply=True), 70
        )
        assert not reason

    async def test_a_failing_score_explains_itself(self) -> None:
        reason: Any = await call_maybe_async(
            skip_reason_for, JobScore(score=10, recommend_apply=False), 70
        )
        assert reason
        assert isinstance(reason, str)
