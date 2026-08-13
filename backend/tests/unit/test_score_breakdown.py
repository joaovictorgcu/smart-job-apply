"""The per-dimension score breakdown and screening-answer provenance."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import scoring
from app.ai.schemas import JobScore, ScoreDimension, ScreeningAnswer
from app.automation.contracts import FormQuestion
from tests.fixtures.factories import create_job


class TestScoreDimension:
    def test_rejects_an_out_of_range_dimension_score(self) -> None:
        # Same contract as JobScore.score: out of range is a validation error the
        # client retries on, not a number to silently clamp.
        with pytest.raises(ValidationError):
            ScoreDimension(dimension="skills", score=140, evidence="x")
        with pytest.raises(ValidationError):
            ScoreDimension(dimension="skills", score=-5, evidence="x")

    def test_rejects_a_dimension_outside_the_closed_set(self) -> None:
        # Free-form names would be untranslatable in the dashboard.
        with pytest.raises(ValidationError):
            ScoreDimension(dimension="vibes", score=50, evidence="x")  # type: ignore[arg-type]

    def test_defaults_to_a_hard_requirement(self) -> None:
        assert ScoreDimension(dimension="location", score=10, evidence="x").weight == "hard"

    def test_a_score_without_a_breakdown_is_still_valid(self) -> None:
        # Every job scored before this feature has none, and the model may omit it.
        assert JobScore(score=70, recommend_apply=True).breakdown == []


class TestBreakdownIsPersisted:
    async def test_analyze_stores_the_breakdown_on_the_job(
        self, session: AsyncSession, user: Any, fake_ai: Any
    ) -> None:
        job = await create_job(session, user)
        profile_ctx = scoring.ProfileContext(headline="Backend engineer")

        await scoring.analyze_job(
            session,
            user=user,
            job=job,
            profile_ctx=profile_ctx,
            settings_row=None,
            client=fake_ai,
        )

        assert [row["dimension"] for row in job.score_breakdown] == ["skills", "experience"]
        assert job.score_breakdown[0]["score"] == 90
        assert job.score_breakdown[0]["weight"] == "hard"
        assert "FastAPI" in job.score_breakdown[0]["evidence"]

    async def test_the_breakdown_reaches_the_api(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        job = await create_job(
            session,
            user,
            score=88,
            score_breakdown=[
                {"dimension": "seniority", "score": 75, "weight": "hard", "evidence": "Senior."}
            ],
        )

        payload = (await client.get(f"/api/jobs/{job.id}", headers=auth_headers)).json()

        assert payload["score_breakdown"] == [
            {"dimension": "seniority", "score": 75, "weight": "hard", "evidence": "Senior."}
        ]

    async def test_a_job_scored_before_the_feature_reads_back_empty(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        job = await create_job(session, user, score=60)

        payload = (await client.get(f"/api/jobs/{job.id}", headers=auth_headers)).json()

        assert payload["score_breakdown"] == []


class TestAnswerProvenance:
    def test_an_answer_from_the_bank_is_marked_as_such(self) -> None:
        question = FormQuestion(field_id="q1", label="Notice period", kind="text")

        answer = scoring._answer_from_bank(question, {"notice period": "30 days"})

        assert answer is not None
        assert answer.source == "answer_bank"

    def test_a_model_answer_defaults_to_ai(self) -> None:
        assert ScreeningAnswer(question="Q", answer="A").source == "ai"

    async def test_editing_an_answer_marks_it_as_the_users_own(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        from tests.fixtures.factories import create_application

        job = await create_job(session, user)
        application = await create_application(
            session,
            user,
            job,
            screening_answers=[
                {
                    "question": "Years of Python experience?",
                    "answer": "7",
                    "question_type": "number",
                    "confidence": "high",
                    "needs_review": False,
                    "source": "ai",
                    "field_id": "q-years",
                }
            ],
        )

        response = await client.patch(
            f"/api/applications/{application.id}",
            headers=auth_headers,
            json={
                "screening_answers": [
                    {
                        "question": "Years of Python experience?",
                        # The user corrects the model's guess.
                        "answer": "4",
                        "question_type": "number",
                        "confidence": "high",
                        "needs_review": False,
                        "source": "ai",
                        "field_id": "q-years",
                    }
                ]
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["screening_answers"][0]["source"] == "user"

    async def test_an_untouched_answer_keeps_its_source(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        from tests.fixtures.factories import create_application

        job = await create_job(session, user)
        stored = {
            "question": "Notice period?",
            "answer": "30 days",
            "question_type": "text",
            "confidence": "high",
            "needs_review": False,
            "source": "answer_bank",
            "field_id": "q-notice",
        }
        application = await create_application(session, user, job, screening_answers=[stored])

        response = await client.patch(
            f"/api/applications/{application.id}",
            headers=auth_headers,
            json={"screening_answers": [stored]},
        )

        assert response.json()["screening_answers"][0]["source"] == "answer_bank"
