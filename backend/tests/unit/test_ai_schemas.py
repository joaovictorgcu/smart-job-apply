"""The AI output contract.

These are the structures every provider has to produce, and the place where a
low-confidence answer is turned into a review request.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.schemas import (
    AIUsage,
    CoverLetter,
    JobAnalysis,
    JobScore,
    ScreeningAnswer,
    ScreeningAnswerSet,
)
from app.models.enums import AnswerConfidence


class TestJobScore:
    def test_accepts_the_full_range(self) -> None:
        assert JobScore(score=0, recommend_apply=False).score == 0
        assert JobScore(score=100, recommend_apply=True).score == 100

    @pytest.mark.parametrize("score", [-1, 101, 1000])
    def test_rejects_a_score_outside_the_range(self, score: int) -> None:
        with pytest.raises(ValidationError):
            JobScore(score=score, recommend_apply=True)

    def test_lists_default_to_empty(self) -> None:
        result = JobScore(score=50, recommend_apply=False)
        assert result.reasons == []
        assert result.missing_requirements == []
        assert result.summary is None

    def test_ignores_unknown_keys_from_the_model(self) -> None:
        result = JobScore.model_validate(
            {"score": 80, "recommend_apply": True, "hallucinated_field": "ignored"}
        )
        assert not hasattr(result, "hallucinated_field")

    def test_requires_an_explicit_recommendation(self) -> None:
        with pytest.raises(ValidationError):
            JobScore.model_validate({"score": 80})


class TestScreeningAnswer:
    def test_low_confidence_forces_review(self) -> None:
        """The safety property: nothing low-confidence is submitted silently."""
        answer = ScreeningAnswer(question="Salary?", answer="120000", confidence="low")
        assert answer.confidence is AnswerConfidence.LOW
        assert answer.needs_review is True

    def test_low_confidence_forces_review_when_the_model_says_otherwise(self) -> None:
        answer = ScreeningAnswer(
            question="Salary?", answer="120000", confidence="low", needs_review=False
        )
        assert answer.needs_review is True

    @pytest.mark.parametrize("confidence", ["high", "medium"])
    def test_confident_answers_are_not_flagged_by_default(self, confidence: str) -> None:
        answer = ScreeningAnswer(question="Salary?", answer="120000", confidence=confidence)
        assert answer.needs_review is False

    def test_an_explicit_review_flag_survives_high_confidence(self) -> None:
        answer = ScreeningAnswer(
            question="Salary?", answer="120000", confidence="high", needs_review=True
        )
        assert answer.needs_review is True

    def test_defaults_to_medium_confidence_and_unknown_type(self) -> None:
        answer = ScreeningAnswer(question="Salary?", answer="120000")
        assert answer.confidence is AnswerConfidence.MEDIUM
        assert answer.question_type == "unknown"
        assert answer.field_id is None

    def test_rejects_an_unknown_question_type(self) -> None:
        with pytest.raises(ValidationError):
            ScreeningAnswer(question="Salary?", answer="1", question_type="slider")


class TestScreeningAnswerSet:
    def test_defaults_to_no_answers(self) -> None:
        assert ScreeningAnswerSet().answers == []

    def test_validates_nested_answers_including_the_review_rule(self) -> None:
        answers = ScreeningAnswerSet.model_validate(
            {"answers": [{"question": "Visa?", "answer": "Yes", "confidence": "low"}]}
        )
        assert answers.answers[0].needs_review is True


class TestCoverLetter:
    def test_keeps_the_language_it_is_given(self) -> None:
        assert CoverLetter(content="Hello", language="en").language == "en"

    def test_content_is_required(self) -> None:
        with pytest.raises(ValidationError):
            CoverLetter.model_validate({"language": "en"})


class TestJobAnalysis:
    def test_defaults_are_safe(self) -> None:
        analysis = JobAnalysis()
        assert analysis.score == 0
        assert analysis.recommend_apply is False
        assert analysis.refused is False
        assert analysis.cover_letter is None
        assert analysis.screening_answers == []

    def test_carries_a_refusal(self) -> None:
        analysis = JobAnalysis(refused=True, refusal_reason="Declined.")
        assert analysis.refused is True
        assert analysis.refusal_reason == "Declined."

    def test_nested_answers_keep_the_review_rule(self) -> None:
        analysis = JobAnalysis.model_validate(
            {
                "score": 90,
                "screening_answers": [
                    {"question": "Relocate?", "answer": "Maybe", "confidence": "low"}
                ],
            }
        )
        assert analysis.screening_answers[0].needs_review is True


class TestAIUsage:
    def test_only_the_model_is_required(self) -> None:
        usage = AIUsage(model="claude-opus-5")
        assert usage.input_tokens is None
        assert usage.refused is False

    def test_records_a_refusal_category(self) -> None:
        usage = AIUsage(model="claude-opus-5", refused=True, refusal_category="policy")
        assert usage.refused is True
        assert usage.refusal_category == "policy"
