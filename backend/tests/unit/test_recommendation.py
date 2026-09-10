"""Why this vacancy — the two lists a reader can check against their own resume.

The number is not the product here; the split is. So the assertions are about
what may appear on each side: `covered` only holds terms the resume genuinely
names, `missing` only holds terms the posting genuinely asks for, and neither
can be widened by a preference.
"""

from __future__ import annotations

from app.domain.recommendation import MAX_TERMS, build

RESUME = (
    "Desenvolvedor Full Stack. Construí APIs REST em C# e .NET consumidas por "
    "um painel React. Migrei relatórios para PostgreSQL."
)
VOCABULARY = ("C#", ".NET", "React", "PostgreSQL", "APIs REST")

POSTING = (
    "Buscamos pessoa desenvolvedora para atuar com .NET, React, APIs REST e Azure. "
    "Conhecimento em Kubernetes é diferencial."
)


def recommend(**overrides: object):
    payload: dict[str, object] = {
        "score": 92,
        "title": "Desenvolvedor .NET",
        "description": POSTING,
        "resume_text": RESUME,
        "vocabulary": VOCABULARY,
    }
    payload.update(overrides)
    return build(**payload)  # type: ignore[arg-type]


class TestTheSplit:
    def test_what_the_resume_backs_goes_on_the_covered_side(self) -> None:
        result = recommend()

        covered = {term.lower() for term in result.covered}
        assert ".net" in covered
        assert "react" in covered
        assert "postgresql" not in covered, "the posting never asked for it"

    def test_what_the_posting_asks_and_the_resume_lacks_is_named_not_hidden(self) -> None:
        result = recommend()

        missing = {term.lower() for term in result.missing}
        assert "azure" in missing
        assert "kubernetes" in missing

    def test_a_covered_term_keeps_the_candidate_s_own_spelling(self) -> None:
        # The posting writes "postgres"; the resume writes "PostgreSQL".
        result = recommend(description="Vaga com postgres e .NET.")

        assert "PostgreSQL" in result.covered

    def test_a_missing_term_keeps_the_posting_s_spelling(self) -> None:
        result = recommend(description="Precisamos de Elixir e gRPC.")

        assert "Elixir" in result.missing
        assert "gRPC" in result.missing

    def test_the_counts_are_whole_even_when_the_chips_are_capped(self) -> None:
        many = " ".join(
            ["Python", "Go", "Rust", "Ruby", "PHP", "Kotlin", "Swift", "Scala", "Elixir", "Perl"]
        )
        result = recommend(description=f"Precisamos de {many}.")

        assert len(result.missing) == MAX_TERMS
        assert result.asked_total >= 10


class TestCoverage:
    def test_coverage_is_the_share_of_what_the_posting_named(self) -> None:
        result = recommend(description="Precisamos de .NET, React e Azure.")

        assert result.covered_total == 2
        assert result.asked_total == 3
        assert result.coverage_pct == 67

    def test_a_posting_with_nothing_comparable_says_so(self) -> None:
        # The title counts too, so it has to be free of technologies as well.
        result = recommend(
            title="Pessoa Desenvolvedora", description="Somos uma equipe colaborativa e diversa."
        )

        assert result.has_evidence is False
        assert result.coverage_pct == 0
        assert result.covered == ()

    def test_a_posting_with_no_text_at_all_does_not_crash(self) -> None:
        result = recommend(title="", description=None)

        assert result.has_evidence is False
        assert result.verdict == "strong"


class TestVerdict:
    def test_the_band_comes_from_the_stored_score(self) -> None:
        assert recommend(score=92).verdict == "strong"
        assert recommend(score=62).verdict == "good"
        assert recommend(score=20).verdict == "poor"

    def test_an_unscored_posting_still_splits_the_requirements(self) -> None:
        result = recommend(score=None)

        assert result.score is None
        assert result.covered, "the split does not need a score to be useful"


class TestPriorities:
    def test_a_priority_leads_the_covered_list(self) -> None:
        result = recommend(priority=("React",))

        assert result.covered[0] == "React"
        assert result.prioritized == ("React",)

    def test_a_priority_the_posting_never_asks_for_adds_nothing(self) -> None:
        result = recommend(priority=("Kubernetes", "Elixir"))

        covered = {term.lower() for term in result.covered}
        assert "kubernetes" not in covered
        assert "elixir" not in covered
        assert result.prioritized == ()

    def test_a_priority_the_candidate_does_not_have_stays_on_the_missing_side(self) -> None:
        result = recommend(priority=("Azure",))

        assert "Azure" in result.missing
        assert all(term.lower() != "azure" for term in result.covered)

    def test_priorities_keep_the_order_the_user_listed_them_in(self) -> None:
        result = recommend(priority=("React", ".NET"))

        assert result.covered[:2] == ("React", ".NET")


class TestSpellingIsNotAGap:
    """The worst failure this can have is telling someone they lack what they have.

    A posting writes "postgres", a resume writes "PostgreSQL". Whole-term
    matching alone calls that a missing requirement, and the user reads it as
    "you are not qualified" — so the equivalent spellings are matched, and only
    the exact ones.
    """

    def test_an_alternative_spelling_is_covered_not_missing(self) -> None:
        result = recommend(title="Backend", description="Vaga com postgres.")

        assert result.covered == ("PostgreSQL",), "the candidate's own spelling belongs on screen"
        assert result.missing == ()

    def test_csharp_and_dotnet_spellings_agree_too(self) -> None:
        result = recommend(title="Backend", description="Precisamos de csharp e dotnet.")

        assert result.missing == ()
        assert {term.lower() for term in result.covered} == {"c#", ".net"}

    def test_a_near_neighbour_is_still_a_real_gap(self) -> None:
        # Java is not JavaScript, and merging them to look generous would hide
        # a gap instead of a false one.
        result = recommend(
            title="Backend",
            description="Precisamos de Java.",
            resume_text="Trabalho com JavaScript e TypeScript.",
            vocabulary=("JavaScript", "TypeScript"),
        )

        assert [term.lower() for term in result.missing] == ["java"]
        assert result.covered == ()
