"""The skip/keep decision behind every scored job.

Pure tests over `app.domain.scoring`: no database, no model, no job row. The
invariant they defend is that a gate outranks the number — a posting the
candidate is not eligible for must never reach the review queue because it
scored well on skills.
"""

from __future__ import annotations

from app.ai.schemas import JobScore, ScoreGate
from app.domain.scoring import VERDICT_BANDS, decide, verdict_for


def make_score(score: int, *gates: ScoreGate) -> JobScore:
    return JobScore(score=score, recommend_apply=True, gates=list(gates))


def gate(name: str = "eligibility", status: str = "fail", evidence: str = "Because.") -> ScoreGate:
    return ScoreGate(gate=name, status=status, evidence=evidence)


class TestGatesOutrankTheNumber:
    def test_a_failed_gate_skips_a_high_scoring_job(self) -> None:
        score = make_score(95, gate(evidence="Must hold an active security clearance."))

        decision = decide(score, min_score=50)

        assert decision.skipped is True
        assert decision.failed_gate == "eligibility"
        assert decision.skip_reason == (
            "Gate eligibility: Must hold an active security clearance."
        )

    def test_the_verdict_still_reflects_the_number_of_a_gated_job(self) -> None:
        # The user is told *why* it was dropped, not that it was a bad match.
        decision = decide(make_score(95, gate()), min_score=50)

        assert decision.verdict == "strong"

    def test_the_first_failing_gate_wins(self) -> None:
        score = make_score(
            80,
            gate("language", evidence="Native German required."),
            gate("eligibility", evidence="EU work permit required."),
        )

        decision = decide(score, min_score=50)

        assert decision.failed_gate == "language"
        assert "German" in (decision.skip_reason or "")

    def test_a_flagged_gate_does_not_skip(self) -> None:
        score = make_score(80, gate("language", status="flag", evidence="German B2 vs fluent."))

        decision = decide(score, min_score=50)

        assert decision.skipped is False
        assert decision.failed_gate is None

    def test_the_skip_reason_is_truncated_to_300_characters(self) -> None:
        decision = decide(make_score(90, gate(evidence="x" * 500)), min_score=50)

        assert decision.skip_reason is not None
        assert len(decision.skip_reason) == 300
        assert decision.skip_reason.startswith("Gate eligibility: ")


class TestTheThreshold:
    def test_a_score_equal_to_the_minimum_is_kept(self) -> None:
        decision = decide(make_score(60), min_score=60)

        assert decision.skipped is False
        assert decision.skip_reason is None

    def test_a_score_one_below_the_minimum_is_skipped(self) -> None:
        decision = decide(make_score(59), min_score=60)

        assert decision.skipped is True
        assert decision.skip_reason == "Score 59 is below the minimum of 60."
        assert decision.failed_gate is None

    def test_a_zero_minimum_keeps_everything_that_passes_its_gates(self) -> None:
        assert decide(make_score(0), min_score=0).skipped is False


class TestVerdictBands:
    def test_every_band_boundary(self) -> None:
        assert [
            verdict_for(value) for value in (100, 75, 74, 60, 59, 45, 44, 30, 29, 0)
        ] == [
            "strong", "strong", "good", "good", "moderate",
            "moderate", "weak", "weak", "poor", "poor",
        ]

    def test_the_bands_are_ordered_from_the_highest_floor_down(self) -> None:
        # `verdict_for` returns the first band whose floor is met, so an
        # out-of-order table would silently mislabel every score.
        floors = [floor for _, floor in VERDICT_BANDS]
        assert floors == sorted(floors, reverse=True)
        assert floors[-1] == 0
