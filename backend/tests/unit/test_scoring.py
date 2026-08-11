"""Scoring: the AI contract, the min-score gate, and graceful degradation.

`app.ai.scoring` is where a model answer becomes a decision recorded in the
database. Three properties matter: the user's `min_score` is the gate, every call
lands in `AIAnalysis` for audit, and a refusal or an API failure never propagates
far enough to abort a run.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import JobScore
from app.ai.scoring import analyze_job, answer_screening, generate_cover_letter
from app.models import AIAnalysis, AnalysisKind, JobStatus
from app.models.enums import AnswerConfidence
from tests.fixtures.factories import (
    create_job,
    create_user,
    make_form_question,
    make_profile_context,
)
from tests.fixtures.fake_ai import FakeAIClient


def settings_row(**overrides: Any) -> Any:
    """A plain object: `app.ai.scoring` only reads attributes off the settings."""
    values: dict[str, Any] = {
        "min_score": 70,
        "generate_cover_letter": True,
        "cover_letter_tone": "professional",
        "content_language": "job",
        "ai_model": None,
    }
    values.update(overrides)
    return type("Settings", (), values)()


async def analyses(session: AsyncSession, job_id: int) -> list[AIAnalysis]:
    result = await session.execute(select(AIAnalysis).where(AIAnalysis.job_id == job_id))
    return list(result.scalars().all())


class TestAIClientContract:
    """The fake stands in for Claude everywhere, so its contract is load-bearing."""

    async def test_scoring_returns_a_job_score_and_its_usage(self) -> None:
        score, usage = await FakeAIClient(score=91).score_job()
        assert isinstance(score, JobScore)
        assert score.score == 91
        assert score.recommend_apply is True
        assert usage.input_tokens and usage.output_tokens

    async def test_scoring_is_deterministic(self) -> None:
        client = FakeAIClient(score=77)
        first, _ = await client.score_job()
        second, _ = await client.score_job()
        assert first.model_dump() == second.model_dump()
        assert client.call_count("score_job") == 2

    async def test_a_refusal_is_reported_in_usage_not_raised(self) -> None:
        score, usage = await FakeAIClient(refused=True).score_job()
        assert usage.refused is True
        assert score.score == 0

    async def test_a_refused_cover_letter_comes_back_empty(self) -> None:
        letter, usage = await FakeAIClient(refused=True).write_cover_letter()
        assert usage.refused is True
        assert letter.content == ""

    async def test_low_confidence_answers_are_flagged_for_review(self) -> None:
        answers, _ = await FakeAIClient(low_confidence=True).answer_questions(
            questions=[make_form_question()]
        )
        assert answers[0].confidence == AnswerConfidence.LOW
        assert answers[0].needs_review is True

    async def test_answers_carry_the_field_id_back_to_the_form(self) -> None:
        question = make_form_question(field_id="q-salary", label="Salary?", kind="text")
        answers, _ = await FakeAIClient().answer_questions(questions=[question])
        assert answers[0].field_id == "q-salary"
        assert answers[0].question == "Salary?"

    async def test_a_transport_failure_raises_an_api_error(self) -> None:
        import anthropic

        with pytest.raises(anthropic.APIError):
            await FakeAIClient(api_error=True).score_job()


class TestScoreGate:
    async def test_a_score_at_the_threshold_is_analyzed_not_skipped(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="gate1@example.com")
        job = await create_job(session, user)

        result = await analyze_job(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            settings_row=settings_row(min_score=85),
            client=FakeAIClient(score=85),
        )

        assert result.score == 85
        assert job.status == JobStatus.ANALYZED
        assert job.skip_reason is None

    async def test_a_score_below_the_threshold_is_skipped_with_a_reason(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="gate2@example.com")
        job = await create_job(session, user)

        await analyze_job(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            settings_row=settings_row(min_score=90),
            client=FakeAIClient(score=40),
        )

        assert job.status == JobStatus.SKIPPED
        assert job.skip_reason

    async def test_the_users_threshold_wins_over_the_models_recommendation(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="gate3@example.com")
        job = await create_job(session, user)

        await analyze_job(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            settings_row=settings_row(min_score=80),
            client=FakeAIClient(score=40, recommend_apply=True),
        )

        assert job.status == JobStatus.SKIPPED

    async def test_the_score_and_its_justification_are_persisted(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="gate4@example.com")
        job = await create_job(session, user)

        await analyze_job(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            settings_row=settings_row(),
            client=FakeAIClient(
                score=88, reasons=["Strong Python match"], missing_requirements=["Kafka"]
            ),
        )

        assert job.score == 88
        assert job.score_reasons == ["Strong Python match"]
        assert job.missing_requirements == ["Kafka"]


class TestAuditTrail:
    async def test_every_scoring_call_is_recorded(self, session: AsyncSession) -> None:
        user = await create_user(session, email="audit-score@example.com")
        job = await create_job(session, user)

        await analyze_job(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            settings_row=settings_row(),
            client=FakeAIClient(),
        )

        rows = await analyses(session, job.id)
        assert len(rows) == 1
        assert rows[0].kind == AnalysisKind.SCORING
        assert rows[0].input_tokens == 1200
        assert rows[0].was_refusal is False

    async def test_a_refusal_is_recorded_as_a_refusal(self, session: AsyncSession) -> None:
        user = await create_user(session, email="audit-refusal@example.com")
        job = await create_job(session, user)

        await analyze_job(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            settings_row=settings_row(),
            client=FakeAIClient(refused=True),
        )

        rows = await analyses(session, job.id)
        assert rows
        assert any(row.was_refusal for row in rows)

    async def test_an_api_failure_is_recorded_and_the_job_keeps_its_status(
        self, session: AsyncSession
    ) -> None:
        """A failed call must leave the job triageable, not half-updated."""
        user = await create_user(session, email="audit-error@example.com")
        job = await create_job(session, user, status=JobStatus.DISCOVERED)

        await analyze_job(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            settings_row=settings_row(),
            client=FakeAIClient(api_error=True),
        )

        rows = await analyses(session, job.id)
        assert rows
        assert rows[0].error_message
        assert job.status == JobStatus.DISCOVERED


class TestCoverLetter:
    async def test_writes_a_letter_when_the_setting_is_on(self, session: AsyncSession) -> None:
        user = await create_user(session, email="letter1@example.com")
        job = await create_job(session, user)

        letter = await generate_cover_letter(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            settings_row=settings_row(generate_cover_letter=True),
            client=FakeAIClient(cover_letter_text="Dear team,"),
        )

        assert letter is not None
        assert letter.content == "Dear team,"

    async def test_writes_nothing_when_the_setting_is_off(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="letter2@example.com")
        job = await create_job(session, user)
        client = FakeAIClient()

        letter = await generate_cover_letter(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            settings_row=settings_row(generate_cover_letter=False),
            client=client,
        )

        assert letter is None
        assert client.calls == []

    async def test_a_refusal_yields_no_letter_instead_of_an_error(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="letter3@example.com")
        job = await create_job(session, user)

        letter = await generate_cover_letter(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            settings_row=settings_row(),
            client=FakeAIClient(refused=True),
        )

        assert letter is None

    async def test_an_api_failure_yields_no_letter_instead_of_an_error(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="letter4@example.com")
        job = await create_job(session, user)

        letter = await generate_cover_letter(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            settings_row=settings_row(),
            client=FakeAIClient(api_error=True),
        )

        assert letter is None


class TestScreeningAnswers:
    async def test_no_questions_means_no_ai_call(self, session: AsyncSession) -> None:
        user = await create_user(session, email="screen1@example.com")
        job = await create_job(session, user)
        client = FakeAIClient()

        answers = await answer_screening(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(),
            questions=[],
            client=client,
        )

        assert answers == []
        assert client.calls == []

    async def test_a_stored_answer_is_used_without_calling_the_model(
        self, session: AsyncSession
    ) -> None:
        """The answer bank is free, and cannot invent anything."""
        user = await create_user(session, email="screen2@example.com")
        job = await create_job(session, user)
        client = FakeAIClient()

        answers = await answer_screening(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(answer_bank={"notice period": "30 days"}),
            questions=[make_form_question("q-notice", "Notice period?", "text")],
            client=client,
        )

        assert answers
        assert answers[0].answer == "30 days"
        assert client.calls == []

    async def test_an_unknown_question_reaches_the_model(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="screen3@example.com")
        job = await create_job(session, user)
        client = FakeAIClient(answer_value="9")

        answers = await answer_screening(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(answer_bank={}),
            questions=[make_form_question("q-odd", "How many llamas do you own?", "number")],
            client=client,
        )

        assert client.call_count("answer_questions") == 1
        assert answers
        assert answers[0].answer == "9"

    async def test_a_low_confidence_answer_comes_back_flagged(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="screen4@example.com")
        job = await create_job(session, user)

        answers = await answer_screening(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(answer_bank={}),
            questions=[make_form_question("q-odd", "How many llamas do you own?", "number")],
            client=FakeAIClient(low_confidence=True),
        )

        assert answers
        assert answers[0].needs_review is True

    async def test_a_failed_call_leaves_the_question_unanswered_instead_of_guessing(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="screen5@example.com")
        job = await create_job(session, user)

        answers = await answer_screening(
            session,
            user=user,
            job=job,
            profile_ctx=make_profile_context(answer_bank={}),
            questions=[make_form_question("q-odd", "How many llamas do you own?", "number")],
            client=FakeAIClient(api_error=True),
        )

        assert answers == []
        rows = await analyses(session, job.id)
        assert rows
        assert rows[0].error_message
