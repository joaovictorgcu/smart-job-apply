"""The fit score, recomputed from the breakdown that is supposed to explain it.

Two promises are under test. First, a model's arithmetic never costs a scoring
call: whatever the emitted weights add up to, they are rescaled instead of
rejected. Second, the recomputed score is reported and never applied — the
threshold still runs on the model's own number, and a disagreement between the
two reaches the user instead of being quietly resolved.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import JobScore, ScoreDimension, ScoreGate
from app.domain.scoring import decide, weighted_score
from app.models.enums import JobStatus
from app.schemas.job import JobRead
from tests.fixtures.factories import create_job


def dimension(name: str, score: int, weight_pct: int) -> ScoreDimension:
    return ScoreDimension(
        dimension=name,  # type: ignore[arg-type]
        score=score,
        weight_pct=weight_pct,
        evidence="e",
    )


def weights_of(score: JobScore) -> list[int]:
    return [row.weight_pct for row in score.breakdown]


def score_with(*dimensions: ScoreDimension, overall: int = 80) -> JobScore:
    return JobScore(score=overall, recommend_apply=True, breakdown=list(dimensions))


class TestWeightNormalization:
    def test_weights_that_fall_short_of_100_are_scaled_up(self) -> None:
        # 30 + 25 + 15 + 17 = 87. The model's relative importances are intact;
        # only its arithmetic was wrong, and only its arithmetic is repaired.
        score = score_with(
            dimension("skills", 90, 30),
            dimension("experience", 80, 25),
            dimension("seniority", 70, 15),
            dimension("location", 60, 17),
        )

        assert sum(weights_of(score)) == 100
        assert weights_of(score) == [34, 29, 17, 20]

    def test_weights_that_overshoot_100_are_scaled_down(self) -> None:
        # 100 + 100 + 50 = 250: the model weighted each dimension against the
        # whole instead of against the others. Ratios survive, the total is fixed.
        score = score_with(
            dimension("skills", 90, 100),
            dimension("experience", 80, 100),
            dimension("seniority", 70, 50),
        )

        assert weights_of(score) == [40, 40, 20]

    def test_all_zero_weights_are_split_evenly(self) -> None:
        # Nothing to be proportional to. The model still chose to emit these
        # three dimensions, so "all of them, equally" is the least-assuming read.
        score = score_with(
            dimension("skills", 90, 0),
            dimension("experience", 80, 0),
            dimension("seniority", 70, 0),
        )

        assert weights_of(score) == [34, 33, 33]
        assert sum(weights_of(score)) == 100

    def test_a_single_dimension_carries_the_whole_weight(self) -> None:
        assert weights_of(score_with(dimension("skills", 90, 42))) == [100]
        assert weights_of(score_with(dimension("skills", 90, 0))) == [100]

    def test_an_absurd_sum_is_still_normalized_rather_than_rejected(self) -> None:
        # A rejection would throw away every gate, reason and dimension in the
        # response over a number the model wrote last and cares about least.
        score = score_with(
            dimension("skills", 90, 100),
            dimension("experience", 80, 100),
            dimension("seniority", 70, 100),
            dimension("education", 60, 100),
        )

        assert weights_of(score) == [25, 25, 25, 25]

    def test_an_empty_breakdown_normalizes_to_nothing(self) -> None:
        assert weights_of(score_with()) == []


class TestWeightedScore:
    def test_recomputes_the_score_from_the_breakdown(self) -> None:
        # (90 * 60 + 50 * 40) / 100 = 74.
        breakdown = [dimension("skills", 90, 60), dimension("experience", 50, 40)]

        assert weighted_score(breakdown) == 74

    def test_an_empty_breakdown_is_not_derivable(self) -> None:
        assert weighted_score([]) is None

    def test_a_breakdown_without_weights_is_not_derivable(self) -> None:
        # Every breakdown stored before `weight_pct` existed looks like this.
        # Averaging it evenly would put a number on screen the model never gave.
        assert weighted_score([dimension("skills", 90, 0), dimension("experience", 50, 0)]) is None

    def test_rounds_half_up(self) -> None:
        # 82.5. Banker's rounding would answer 82, which reads as a bug to
        # anyone checking the arithmetic by hand.
        assert weighted_score([dimension("skills", 82, 50), dimension("experience", 83, 50)]) == 83

    def test_divides_by_the_actual_weight_total(self) -> None:
        # Stored rows bypass the JobScore validator, so a partial breakdown must
        # still average correctly instead of being deflated towards zero.
        assert weighted_score([dimension("skills", 80, 30), dimension("experience", 60, 10)]) == 75


class TestDivergenceIsSurfacedNotApplied:
    def test_the_threshold_still_uses_the_models_own_score(self) -> None:
        score = score_with(
            dimension("skills", 90, 60),
            dimension("experience", 50, 40),
            overall=90,
        )

        decision = decide(score, min_score=80)

        # The breakdown adds up to 74, which is below the minimum; the headline
        # 90 is not. The job survives, and the contradiction is reported.
        assert decision.skipped is False
        assert decision.weighted == 74
        assert decision.divergence == 16

    def test_a_failed_gate_still_reports_the_arithmetic(self) -> None:
        score = JobScore(
            score=95,
            recommend_apply=False,
            breakdown=[dimension("skills", 90, 100)],
            gates=[ScoreGate(gate="eligibility", status="fail", evidence="Requires citizenship.")],
        )

        decision = decide(score, min_score=0)

        assert decision.skipped is True
        assert decision.weighted == 90
        assert decision.divergence == 5

    def test_a_consistent_breakdown_diverges_by_zero(self) -> None:
        score = score_with(dimension("skills", 80, 50), dimension("experience", 80, 50), overall=80)

        decision = decide(score, min_score=0)

        assert decision.divergence == 0

    def test_no_breakdown_means_no_arithmetic_to_report(self) -> None:
        decision = decide(score_with(overall=70), min_score=0)

        assert decision.weighted is None
        assert decision.divergence is None


class TestJobReadDerivesTheFields:
    def test_a_scored_job_round_trips_verdict_and_arithmetic(self) -> None:
        payload = JobRead(
            id=1,
            external_id="x",
            title="t",
            company="c",
            status=JobStatus.ANALYZED,
            score=82,
            verdict="strong",
            weighted_score=74,
            score_divergence=8,
        )

        assert payload.model_dump()["verdict"] == "strong"
        assert JobRead.model_validate(payload.model_dump()).weighted_score == 74
        assert JobRead.model_validate(payload.model_dump()).score_divergence == 8


class TestDerivedFieldsReachTheApi:
    async def test_a_weighted_breakdown_is_derived_on_read(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        job = await create_job(
            session,
            user,
            score=82,
            score_breakdown=[
                {
                    "dimension": "skills",
                    "score": 90,
                    "weight": "hard",
                    "weight_pct": 60,
                    "evidence": "FastAPI.",
                },
                {
                    "dimension": "experience",
                    "score": 50,
                    "weight": "hard",
                    "weight_pct": 40,
                    "evidence": "3 of 6 years.",
                },
            ],
        )

        payload = (await client.get(f"/api/jobs/{job.id}", headers=auth_headers)).json()

        assert payload["verdict"] == "strong"
        assert payload["weighted_score"] == 74
        assert payload["score_divergence"] == 8

    async def test_a_job_scored_before_this_change_reports_no_arithmetic(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        # Stored breakdowns predating `weight_pct` carry no weights, so there is
        # nothing to recompute. The band still holds — it only needs the score.
        job = await create_job(
            session,
            user,
            score=64,
            score_breakdown=[
                {"dimension": "skills", "score": 70, "weight": "hard", "evidence": "Python."}
            ],
        )

        payload = (await client.get(f"/api/jobs/{job.id}", headers=auth_headers)).json()

        assert payload["weighted_score"] is None
        assert payload["score_divergence"] is None
        assert payload["verdict"] == "good"

    async def test_an_unscored_job_reports_none_for_all_three(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        job = await create_job(session, user)

        payload = (await client.get(f"/api/jobs/{job.id}", headers=auth_headers)).json()

        assert payload["score"] is None
        assert payload["verdict"] is None
        assert payload["weighted_score"] is None
        assert payload["score_divergence"] is None


@pytest.mark.parametrize(
    ("weights", "expected"),
    [
        ([1, 1, 1], [34, 33, 33]),
        ([1, 2], [33, 67]),
        ([7], [100]),
        ([0, 5], [0, 100]),
    ],
)
def test_normalization_is_deterministic(weights: list[int], expected: list[int]) -> None:
    # Same input, same output, every time: these numbers get persisted and then
    # rendered as the explanation of a score, so they cannot drift between runs.
    for _ in range(3):
        dimensions = [dimension("skills", 50, weight) for weight in weights]
        assert weights_of(score_with(*dimensions)) == expected
