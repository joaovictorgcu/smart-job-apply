"""The derivation itself: does one history really reorder itself per posting?

These are the tests that matter most for this feature, and they need no database
and no model — `app.domain.resume` is pure, so "the .NET vacancy leads with the
.NET job and the Python vacancy leads with the data job" is an assertion over
plain data rather than over a rendered page.

Everything here is driven from the same four-position history the API tests use
(`RESUME_HISTORY`), so a change that makes the fixtures unrealistic breaks both.
"""

from __future__ import annotations

from datetime import date

from app.domain import resume as domain
from tests.fixtures.factories import JOB_POSTINGS, RESUME_HISTORY, RESUME_SKILLS


def _experience(entry: dict[str, object], index: int) -> domain.ExperienceInput:
    return domain.ExperienceInput(
        experience_id=index + 1,
        company=str(entry["company"]),
        role=str(entry["role"]),
        location=entry["location"],  # type: ignore[arg-type]
        employment_type=entry["employment_type"],  # type: ignore[arg-type]
        started_on=entry["started_on"],  # type: ignore[arg-type]
        ended_on=entry["ended_on"],  # type: ignore[arg-type]
        is_current=bool(entry["is_current"]),
        summary=str(entry["summary"]),
        responsibilities=tuple(entry["responsibilities"]),  # type: ignore[arg-type]
        technologies=tuple(entry["technologies"]),  # type: ignore[arg-type]
        results=tuple(entry["results"]),  # type: ignore[arg-type]
        projects=tuple(
            domain.ProjectEntry(
                name=str(project["name"]),
                description=str(project["description"]),
                technologies=tuple(project["technologies"]),
            )
            for project in entry["projects"]  # type: ignore[union-attr]
        ),
        position=int(entry["position"]),  # type: ignore[arg-type]
    )


def master() -> domain.MasterResume:
    return domain.MasterResume(
        full_name="Joana Ribeiro",
        headline="Engenheira de software - .NET, React e Python",
        location="Recife, PE",
        summary="Dez anos entre backend, frontend e dados.",
        years_of_experience=9,
        skills=tuple(RESUME_SKILLS),
        resume_text="",
        experiences=tuple(_experience(entry, index) for index, entry in enumerate(RESUME_HISTORY)),
    )


def target(kind: str) -> domain.JobTarget:
    posting = JOB_POSTINGS[kind]
    return domain.JobTarget(
        title=posting["title"], company=posting["company"], description=posting["description"]
    )


def companies(adapted: domain.AdaptedResume) -> list[str]:
    return [experience.company for experience in adapted.experiences]


class TestPrioritisation:
    """The same history, four postings, four different leading experiences."""

    def test_the_dotnet_vacancy_leads_with_the_dotnet_role(self) -> None:
        adapted = domain.adapt(master(), target("dotnet"))

        assert companies(adapted)[0] == "Globalthings"

    def test_the_fullstack_vacancy_leads_with_the_fullstack_role(self) -> None:
        adapted = domain.adapt(master(), target("fullstack"))

        assert companies(adapted)[0] == "Nuvem Retail"

    def test_the_python_vacancy_leads_with_the_data_role(self) -> None:
        adapted = domain.adapt(master(), target("python"))

        assert companies(adapted)[0] == "Instituto Dados Abertos"

    def test_the_engineering_vacancy_leads_with_the_quality_role(self) -> None:
        adapted = domain.adapt(master(), target("engineering"))

        assert companies(adapted)[0] == "Auditar Sistemas"

    def test_relevance_beats_recency(self) -> None:
        """The whole point of adapting: the current job is not always first.

        `Auditar Sistemas` ended in 2018 and `Globalthings` is the current role,
        so a purely chronological resume would open with Globalthings for every
        posting — including one that only asks about Java and Selenium.
        """
        adapted = domain.adapt(master(), target("engineering"))
        order = companies(adapted)

        assert order.index("Auditar Sistemas") < order.index("Globalthings")

    def test_every_experience_survives_the_reordering(self) -> None:
        """Emphasis, not deletion. A resume that drops jobs misrepresents a career."""
        adapted = domain.adapt(master(), target("python"))

        assert sorted(companies(adapted)) == sorted(
            str(entry["company"]) for entry in RESUME_HISTORY
        )


class TestExperienceDescriptions:
    """The same experience, described differently depending on the vacancy."""

    def test_the_same_role_reorders_its_own_bullets_per_vacancy(self) -> None:
        backend = domain.adapt(master(), target("dotnet"))
        fullstack = domain.adapt(master(), target("fullstack"))

        globalthings_backend = next(
            item for item in backend.experiences if item.company == "Globalthings"
        )
        globalthings_fullstack = next(
            item for item in fullstack.experiences if item.company == "Globalthings"
        )

        assert globalthings_backend.responsibilities != globalthings_fullstack.responsibilities
        assert "C#" in globalthings_backend.responsibilities[0]
        assert "React" in globalthings_fullstack.responsibilities[0]

    def test_matched_technologies_are_listed_first(self) -> None:
        fullstack = domain.adapt(master(), target("fullstack"))
        globalthings = next(
            item for item in fullstack.experiences if item.company == "Globalthings"
        )

        # The posting asks about React and TypeScript; C# and .NET are still
        # there, just no longer leading the list.
        assert globalthings.technologies[0] in {"React", "TypeScript"}
        assert "C#" in globalthings.technologies

    def test_a_refocused_experience_reports_how_much_moved(self) -> None:
        adapted = domain.adapt(master(), target("dotnet"))
        globalthings = next(item for item in adapted.experiences if item.company == "Globalthings")

        assert (
            0
            < globalthings.promoted
            < len(globalthings.responsibilities) + len(globalthings.results)
        )

    def test_no_sentence_is_invented(self) -> None:
        """Every line in the output is a line the candidate wrote."""
        original = master()
        adapted = domain.adapt(original, target("dotnet"))

        written = {
            line
            for experience in original.experiences
            for line in (*experience.responsibilities, *experience.results)
        }
        emitted = {
            line
            for experience in adapted.experiences
            for line in (*experience.responsibilities, *experience.results)
        }
        assert emitted <= written


class TestHighlights:
    def test_skills_the_posting_names_are_highlighted_and_lead_the_list(self) -> None:
        adapted = domain.adapt(master(), target("dotnet"))

        assert "C#" in adapted.highlighted_skills
        assert "Java" not in adapted.highlighted_skills
        assert adapted.skills[0] in adapted.highlighted_skills
        # Nothing is dropped from the skills list, only reordered.
        assert sorted(adapted.skills) == sorted(RESUME_SKILLS)

    def test_emphasised_technologies_are_the_ones_asked_for_and_owned(self) -> None:
        adapted = domain.adapt(master(), target("python"))

        assert {"Python", "pandas", "Airflow"} <= set(adapted.emphasized_technologies)
        assert "React" not in adapted.emphasized_technologies

    def test_the_most_relevant_project_leads_and_the_irrelevant_ones_are_dropped(self) -> None:
        backend = domain.adapt(master(), target("dotnet"))
        data = domain.adapt(master(), target("python"))

        assert backend.projects[0]["name"] == "Gerenciador de Acessos"
        assert data.projects[0]["name"] == "Painel de gastos publicos"
        # The React checkout has nothing either posting asks about, so unlike a
        # bullet it is left out entirely — a resume lists projects as separate
        # exhibits, and four unrelated ones is what makes a resume read untailored.
        for adapted in (backend, data):
            assert "Checkout em tres etapas" not in {
                project["name"] for project in adapted.projects
            }

    def test_a_requirement_the_history_cannot_back_is_surfaced_not_hidden(self) -> None:
        adapted = domain.adapt(
            master(),
            domain.JobTarget(
                title="Backend Engineer",
                description="Precisamos de Python, Kubernetes e Terraform em producao.",
            ),
        )

        assert "kubernetes" in {term.lower() for term in adapted.uncovered_requirements}
        assert "terraform" in {term.lower() for term in adapted.uncovered_requirements}
        assert "Python" in adapted.emphasized_technologies


class TestChangeReport:
    def test_it_reports_the_prioritisation_that_actually_happened(self) -> None:
        adapted = domain.adapt(master(), target("engineering"))
        prioritized = [
            change.target for change in adapted.changes if change.kind == "experience_prioritized"
        ]

        assert any("Auditar Sistemas" in target_label for target_label in prioritized)

    def test_it_reports_nothing_when_nothing_moved(self) -> None:
        """A posting with no recognisable requirement changes nothing, and says so."""
        adapted = domain.adapt(
            master(),
            domain.JobTarget(title="Analista", description="Ambiente colaborativo e desafiador."),
        )

        assert adapted.changes == ()
        assert adapted.fit_factors == ()
        assert adapted.fit_score == 0

    def test_every_kind_it_emits_is_declared(self) -> None:
        adapted = domain.adapt(master(), target("dotnet"))

        assert {change.kind for change in adapted.changes} <= set(domain.CHANGE_KINDS)


class TestFit:
    def test_a_matching_vacancy_scores_higher_than_a_mismatched_one(self) -> None:
        strong = domain.adapt(master(), target("dotnet"))
        weak = domain.adapt(
            master(),
            domain.JobTarget(
                title="Engenheiro de Machine Learning",
                description="PyTorch, TensorFlow e Kubeflow em producao. 5+ anos.",
            ),
        )

        assert strong.fit_score > weak.fit_score

    def test_the_factor_weights_sum_to_one_hundred(self) -> None:
        adapted = domain.adapt(master(), target("dotnet"))

        assert sum(factor.weight_pct for factor in adapted.fit_factors) == 100

    def test_the_score_is_the_weighted_sum_of_its_factors(self) -> None:
        """The number has to be reproducible from the breakdown shown next to it."""
        adapted = domain.adapt(master(), target("fullstack"))
        recomputed = round(
            sum(factor.score * factor.weight_pct for factor in adapted.fit_factors) / 100
        )

        assert adapted.fit_score == recomputed

    def test_seniority_is_only_scored_when_the_posting_states_a_requirement(self) -> None:
        with_years = domain.adapt(master(), target("dotnet"))
        without_years = domain.adapt(
            master(),
            domain.JobTarget(title="Backend", description="Trabalhamos com C# e PostgreSQL."),
        )

        assert "seniority" in {factor.factor for factor in with_years.fit_factors}
        assert "seniority" not in {factor.factor for factor in without_years.fit_factors}

    def test_a_junior_profile_is_docked_against_a_senior_requirement(self) -> None:
        junior = domain.MasterResume(
            years_of_experience=2,
            skills=("C#", ".NET"),
            experiences=master().experiences[:1],
        )
        seniority = next(
            factor
            for factor in domain.adapt(junior, target("dotnet")).fit_factors
            if factor.factor == "seniority"
        )

        assert seniority.score == 40  # two of the five years asked for
        assert (seniority.matched, seniority.total) == (2, 5)

    def test_a_multi_word_requirement_is_not_counted_twice(self) -> None:
        """ "Azure DevOps" names one requirement, not "azure" plus "azure devops"."""
        adapted = domain.adapt(
            master(),
            domain.JobTarget(title="DevOps", description="Pipelines no Azure DevOps."),
        )
        technologies = next(
            factor for factor in adapted.fit_factors if factor.factor == "technologies"
        )

        assert technologies.total == 1

    def test_java_survives_next_to_javascript(self) -> None:
        """Whole-term containment, not substring: `java` is not inside `javascript`.

        The guard against double-counting "Azure DevOps" must not quietly delete
        a real requirement whose name happens to be a prefix of another.
        """
        adapted = domain.adapt(
            master(),
            domain.JobTarget(title="Dev", description="Precisamos de Java e de JavaScript."),
        )

        assert {"java", "javascript"} <= {term.lower() for term in adapted.emphasized_technologies}


class TestDeterminismAndFingerprint:
    def test_the_same_inputs_always_produce_the_same_document(self) -> None:
        first = domain.adapt(master(), target("dotnet"))
        second = domain.adapt(master(), target("dotnet"))

        assert companies(first) == companies(second)
        assert first.fit_score == second.fit_score
        assert [change.as_dict() for change in first.changes] == [
            change.as_dict() for change in second.changes
        ]

    def test_editing_an_experience_bullet_moves_the_fingerprint(self) -> None:
        """A staleness check that ignored the structured half would be useless."""
        before = master()
        first = before.experiences[0]
        after = domain.MasterResume(
            headline=before.headline,
            summary=before.summary,
            years_of_experience=before.years_of_experience,
            skills=before.skills,
            experiences=(
                domain.ExperienceInput(
                    company=first.company,
                    role=first.role,
                    experience_id=first.experience_id,
                    started_on=first.started_on,
                    is_current=first.is_current,
                    summary=first.summary,
                    responsibilities=(*first.responsibilities, "Migrei o build para o GitHub."),
                    technologies=first.technologies,
                    results=first.results,
                ),
                *before.experiences[1:],
            ),
        )

        assert domain.fingerprint(before) != domain.fingerprint(after)

    def test_reordering_the_positions_does_not_move_the_fingerprint(self) -> None:
        """Display order is not a fact about the candidate, so it is not stale-worthy."""
        original = master()
        reversed_order = domain.MasterResume(
            headline=original.headline,
            summary=original.summary,
            years_of_experience=original.years_of_experience,
            skills=original.skills,
            experiences=tuple(reversed(original.experiences)),
        )

        assert domain.fingerprint(original) == domain.fingerprint(reversed_order)


class TestDegenerateInputs:
    def test_an_empty_master_resume_is_reported_as_empty(self) -> None:
        assert domain.MasterResume().is_empty() is True
        assert domain.MasterResume(skills=("Python",)).is_empty() is False

    def test_adapting_a_profile_with_no_experience_still_works(self) -> None:
        adapted = domain.adapt(
            domain.MasterResume(skills=("Python", "React"), resume_text="Python e React."),
            target("python"),
        )

        assert adapted.experiences == ()
        assert "Python" in adapted.highlighted_skills

    def test_a_posting_with_no_description_names_nothing(self) -> None:
        adapted = domain.adapt(master(), domain.JobTarget(title="", description=""))

        assert adapted.emphasized_technologies == ()
        assert adapted.uncovered_requirements == ()
        assert companies(adapted) == [str(entry["company"]) for entry in RESUME_HISTORY]

    def test_an_experience_with_no_dates_sorts_last_among_equals(self) -> None:
        undated = domain.ExperienceInput(
            company="Sem Data",
            role="Desenvolvedor",
            responsibilities=("Trabalhei com Java e Selenium.",),
            technologies=("Java", "Selenium"),
            position=9,
        )
        dated = domain.ExperienceInput(
            company="Com Data",
            role="Desenvolvedor",
            started_on=date(2019, 1, 1),
            ended_on=date(2021, 1, 1),
            responsibilities=("Trabalhei com Java e Selenium.",),
            technologies=("Java", "Selenium"),
            position=0,
        )
        adapted = domain.adapt(
            domain.MasterResume(experiences=(undated, dated)), target("engineering")
        )

        assert companies(adapted) == ["Com Data", "Sem Data"]
