"""The invention guard — the safety net behind CV tailoring's "never invent" rule.

These tests are adversarial by design: they try to slip a fabricated technology
past the guard, because catching that is the entire reason the guard exists. They
do not trust the model to have obeyed; they check the code that assumes it did not.
"""

from __future__ import annotations

from app.ai.client import flag_unsupported_skills

SOURCE = (
    "Senior engineer. Skills: Python, FastAPI, PostgreSQL, Docker. "
    "Seven years building REST APIs."
)


class TestCatchesInvention:
    def test_a_curated_technology_absent_from_the_source_is_flagged(self) -> None:
        assert "Kubernetes" in flag_unsupported_skills(SOURCE, "Expert in Python and Kubernetes.")

    def test_a_camelcase_technology_absent_from_the_source_is_flagged(self) -> None:
        assert "GraphQL" in flag_unsupported_skills(SOURCE, "Built GraphQL gateways at scale.")

    def test_an_alphanumeric_technology_absent_from_the_source_is_flagged(self) -> None:
        assert "OAuth2" in flag_unsupported_skills(SOURCE, "Implemented OAuth2 device flows.")

    def test_several_inventions_come_back_unique_sorted_and_original_cased(self) -> None:
        flags = flag_unsupported_skills(SOURCE, "Used Rust and Kubernetes, plus more Rust.")
        assert flags == ["Kubernetes", "Rust"]


class TestLeavesTruthfulContentAlone:
    def test_technologies_present_in_the_source_are_not_flagged(self) -> None:
        assert flag_unsupported_skills(SOURCE, "Strong in Python, FastAPI and PostgreSQL.") == []

    def test_case_and_accents_do_not_cause_false_flags(self) -> None:
        assert flag_unsupported_skills("Skills: Postgrés, Python", "postgres, PYTHON") == []

    def test_ordinary_prose_is_not_treated_as_technology(self) -> None:
        text = "Experienced engineer who ships reliable software and mentors the team."
        assert flag_unsupported_skills(SOURCE, text) == []

    def test_a_skill_only_in_the_profile_skill_list_still_counts_as_supported(self) -> None:
        # `Docker` is in the source but only as a bare skill token, not in prose.
        assert flag_unsupported_skills(SOURCE, "Containerized services with Docker.") == []


class TestDocumentedLimits:
    def test_an_invented_achievement_in_plain_words_is_not_caught(self) -> None:
        # The guard targets fabricated *technologies* — the most checkable class of
        # invention. A made-up result phrased in ordinary words slips through; that
        # limitation is why a human still reviews, and the UI says so.
        assert flag_unsupported_skills(SOURCE, "Increased revenue by forty percent.") == []
