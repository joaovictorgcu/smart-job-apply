"""What the user is looking for, and what that rules out.

The rule under test is narrow on purpose: a posting may only be rejected for a
term the user actually wrote, and only on the fields that say what the job *is*
— its title, its location, its workplace type. Everything else is noise a
skip list would fire on, and a skip list nobody trusts is worse than none.
"""

from __future__ import annotations

from app.domain.preferences import (
    JobPreferenceRules,
    normalize_workplace,
    screen,
    search_keywords,
    search_location,
    search_remote_filter,
)


def rules(**overrides: object) -> JobPreferenceRules:
    return JobPreferenceRules(**overrides)  # type: ignore[arg-type]


class TestStatingNothingRulesOutNothing:
    def test_empty_preferences_pass_every_posting(self) -> None:
        verdict = screen(rules(), title="Atendente de call center presencial")

        assert verdict.excluded is False
        assert bool(verdict) is True

    def test_a_posting_that_does_not_say_its_workplace_is_never_a_mismatch(self) -> None:
        verdict = screen(rules(work_models=("remote",)), title="Backend Developer")

        assert verdict.excluded is False


class TestExcludedTerms:
    def test_a_term_in_the_title_stops_the_posting(self) -> None:
        verdict = screen(
            rules(excluded_terms=("call center", "sales")),
            title="Atendente de Call Center",
        )

        assert verdict.excluded is True
        assert verdict.matched_term == "call center"
        assert "call center" in (verdict.reason or "")

    def test_the_reason_quotes_the_user_s_own_word(self) -> None:
        verdict = screen(rules(excluded_terms=("sênior",)), title="Desenvolvedor Sênior .NET")

        # Accent-insensitive matching, but the reason repeats what they typed.
        assert verdict.excluded is True
        assert 'skip postings mentioning "sênior"' in (verdict.reason or "")

    def test_a_term_inside_a_longer_word_does_not_match(self) -> None:
        verdict = screen(rules(excluded_terms=("net",)), title="Kubernetes Engineer")

        assert verdict.excluded is False

    def test_the_location_and_the_workplace_type_are_screened_too(self) -> None:
        assert screen(
            rules(excluded_terms=("presencial",)),
            title="Backend Developer",
            workplace_type="Presencial",
        ).excluded is True
        assert screen(
            rules(excluded_terms=("são paulo",)),
            title="Backend Developer",
            location="São Paulo, SP",
        ).excluded is True

    def test_blank_terms_are_ignored_rather_than_matching_everything(self) -> None:
        verdict = screen(rules(excluded_terms=("", "   ")), title="Backend Developer")

        assert verdict.excluded is False


class TestWorkModel:
    def test_a_posting_in_a_model_the_user_did_not_ask_for_is_skipped(self) -> None:
        verdict = screen(
            rules(work_models=("remote", "hybrid")),
            title="Backend Developer",
            workplace_type="Presencial",
        )

        assert verdict.excluded is True
        assert verdict.matched_term == "on-site"
        assert "on-site" in (verdict.reason or "")

    def test_a_matching_model_passes_however_the_posting_spells_it(self) -> None:
        for spelling in ("Remoto", "remote", "TELETRABALHO"):
            verdict = screen(
                rules(work_models=("remote",)), title="Backend Developer", workplace_type=spelling
            )
            assert verdict.excluded is False, spelling

    def test_a_wording_we_do_not_recognise_is_not_treated_as_a_mismatch(self) -> None:
        verdict = screen(
            rules(work_models=("remote",)),
            title="Backend Developer",
            workplace_type="Flexível",
        )

        assert verdict.excluded is False

    def test_normalize_workplace_maps_both_languages(self) -> None:
        assert normalize_workplace("Híbrido") == "hybrid"
        assert normalize_workplace("On Site") == "on-site"
        assert normalize_workplace(None) is None
        assert normalize_workplace("nonsense") is None


class TestTheQueryTheseProduce:
    def test_the_main_role_leads_and_the_alternatives_follow(self) -> None:
        query = search_keywords(
            rules(
                target_role="Full Stack Developer",
                alternative_roles=("Backend Developer", "Software Developer"),
            )
        )

        assert query.startswith('"Full Stack Developer"')
        assert '"Backend Developer"' in query
        assert " OR " in query

    def test_a_repeated_role_appears_once(self) -> None:
        query = search_keywords(
            rules(target_role="Backend Developer", alternative_roles=("backend developer",))
        )

        assert query.count("OR") == 0

    def test_no_role_produces_no_query_rather_than_an_empty_sweep(self) -> None:
        assert search_keywords(rules(priority_technologies=("C#",))) == ""

    def test_technologies_stay_out_of_the_query(self) -> None:
        query = search_keywords(
            rules(target_role="Backend Developer", priority_technologies=("C#",))
        )

        assert "C#" not in query

    def test_one_work_model_becomes_a_filter_and_several_do_not(self) -> None:
        assert search_remote_filter(rules(work_models=("remote",))) == "remote"
        # Asking the portal for one of two would hide the other outright; the
        # screen above still rejects what does not match.
        assert search_remote_filter(rules(work_models=("remote", "hybrid"))) is None
        assert search_remote_filter(rules()) is None

    def test_the_first_stated_location_is_the_one_the_filter_takes(self) -> None:
        assert search_location(rules(locations=("Recife, PE", "Lisboa"))) == "Recife, PE"
        assert search_location(rules()) is None
