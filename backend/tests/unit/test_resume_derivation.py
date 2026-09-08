"""The demo master resume, driven through the live adaptation: five vacancies, five resumes.

This file's job is narrow and specific: prove that the *demonstration dataset*
(`app.demo`) actually produces visibly different resumes when run through the
engine the application calls (`app.domain.resume.adapt`). `test_resume_adaptation`
covers the engine's own rules against purpose-built fixtures; this covers the
claim the seeder and the demo make to a human, which is a different thing and
the one that breaks silently when either side drifts.

It was originally written against a second, parallel engine that was merged
alongside the live one. That engine is gone; the assertions moved here, because
"cinco vagas, cinco currículos diferentes" is only worth asserting about the
code that runs.

No API key, no network, no database — `adapt` is pure.
"""

from __future__ import annotations

from typing import Any

from app.ai.client import flag_unsupported_skills
from app.demo import DEMO_JOBS, demo_experiences, demo_profile_fields
from app.domain import resume as domain

BACKEND_DOTNET, FULLSTACK_REACT, PYTHON, ENGINEER, APIS = DEMO_JOBS


def master() -> domain.MasterResume:
    """The demo candidate, as the adaptation sees them."""
    fields = demo_profile_fields()
    return domain.MasterResume(
        full_name="Alex Moreira",
        headline=fields["headline"],
        location=fields["location"],
        summary=fields["summary"],
        years_of_experience=fields["years_of_experience"],
        skills=tuple(fields["skills"]),
        resume_text=fields["resume_text"],
        experiences=tuple(
            domain.ExperienceInput(
                company=entry["company"],
                role=entry["role"],
                experience_id=index + 1,
                location=entry["location"],
                employment_type=entry["employment_type"],
                started_on=entry["started_on"],
                ended_on=entry["ended_on"],
                is_current=entry["is_current"],
                summary=entry["summary"],
                responsibilities=tuple(entry["responsibilities"]),
                technologies=tuple(entry["technologies"]),
                results=tuple(entry["results"]),
                projects=tuple(
                    domain.ProjectEntry(
                        name=project["name"],
                        description=project["description"],
                        technologies=tuple(project["technologies"]),
                    )
                    for project in entry["projects"]
                ),
                position=entry["position"],
            )
            for index, entry in enumerate(demo_experiences())
        ),
    )


def target(raw: dict[str, Any]) -> domain.JobTarget:
    return domain.JobTarget(
        title=raw["title"],
        company=raw["company"],
        description=raw["description"],
        location=raw.get("location"),
    )


def experience(adapted: domain.AdaptedResume, company: str) -> domain.AdaptedExperience:
    return next(entry for entry in adapted.experiences if entry.company == company)


class TestTheDemoDatasetIsRichEnough:
    """If these fail, the demo cannot demonstrate anything, however good the engine."""

    def test_the_master_resume_has_breadth_across_several_stacks(self) -> None:
        source = master()

        assert len(source.experiences) == 5
        assert len(source.skills) == 28
        assert not source.is_empty()
        # Four distinct stacks, so four postings can pull in four directions.
        vocabulary = {term.casefold() for term in source.vocabulary()}
        assert {".net", "react", "python", "graphql"} <= vocabulary

    def test_every_experience_carries_bullets_and_technologies(self) -> None:
        for entry in master().experiences:
            assert entry.responsibilities, f"{entry.company} has no bullets to reorder"
            assert entry.technologies, f"{entry.company} has no technologies to match"

    def test_each_posting_names_something_the_candidate_lacks(self) -> None:
        """The gap list has to have something truthful to report, per vacancy."""
        source = master()

        for raw in DEMO_JOBS:
            assert domain.adapt(source, target(raw)).uncovered_requirements, raw["title"]


class TestFiveVacanciesFiveResumes:
    def test_every_posting_produces_a_distinct_document(self) -> None:
        """The acceptance criterion itself, at the level a human sees it."""
        source = master()
        rendered = {
            raw["title"]: tuple(
                (entry.company, entry.responsibilities) for entry in
                domain.adapt(source, target(raw)).experiences
            )
            for raw in DEMO_JOBS
        }

        assert len(set(rendered.values())) == len(DEMO_JOBS)

    def test_each_posting_leads_with_the_experience_that_fits_it(self) -> None:
        source = master()
        leaders = {
            raw["title"]: domain.adapt(source, target(raw)).experiences[0].company
            for raw in DEMO_JOBS
        }

        assert leaders[BACKEND_DOTNET["title"]] == "Globalthings"
        assert leaders[FULLSTACK_REACT["title"]] == "Cofre Digital"
        assert leaders[PYTHON["title"]] == "Nexdata"

    def test_a_tie_on_relevance_is_broken_by_recency(self) -> None:
        """The APIs posting is the dataset's genuine tie, and pins the tie-break rule.

        Nexdata and Pagamentos Vertex each match six of its terms — Vertex on the
        distinctive ones (GraphQL, OAuth2), Nexdata on the desirable ones (Redis,
        Docker), which `adapt` weighs equally by count. On a real tie the more
        recent role leads, and Nexdata (2021-2023) is more recent than Vertex
        (2017-2019). Asserted rather than worked around: a demo whose ranking
        nobody can predict is not a demo.
        """
        adapted = domain.adapt(master(), target(APIS))
        top_two = adapted.experiences[:2]

        assert {entry.company for entry in top_two} == {"Nexdata", "Pagamentos Vertex"}
        assert top_two[0].relevance == top_two[1].relevance
        assert top_two[0].company == "Nexdata"
        assert top_two[0].is_current is False
        assert top_two[0].started_on > top_two[1].started_on

    def test_only_the_integrations_role_backs_the_postings_distinctive_terms(self) -> None:
        """GraphQL and OAuth2 appear in one job of the candidate's history, and only there."""
        adapted = domain.adapt(master(), target(APIS))
        vertex = experience(adapted, "Pagamentos Vertex")

        assert {"GraphQL", "OAuth2"} <= set(vertex.matched_terms)
        for entry in adapted.experiences:
            if entry.company != "Pagamentos Vertex":
                assert "GraphQL" not in entry.matched_terms
                assert "OAuth2" not in entry.matched_terms

    def test_the_emphasised_technologies_follow_the_posting(self) -> None:
        source = master()
        dotnet = domain.adapt(source, target(BACKEND_DOTNET))
        react = domain.adapt(source, target(FULLSTACK_REACT))

        assert ".NET" in dotnet.emphasized_technologies
        assert "React" in react.emphasized_technologies
        # A posting's own stack, not the union of everything the candidate has.
        assert "React" not in dotnet.emphasized_technologies
        assert "Entity Framework" not in react.emphasized_technologies

    def test_skills_are_highlighted_per_posting_and_never_dropped(self) -> None:
        source = master()
        dotnet = domain.adapt(source, target(BACKEND_DOTNET))
        python = domain.adapt(source, target(PYTHON))

        assert dotnet.highlighted_skills != python.highlighted_skills
        assert "Entity Framework" in dotnet.highlighted_skills
        assert "FastAPI" in python.highlighted_skills
        # Highlighting reorders; it does not truncate.
        assert set(dotnet.skills) == set(source.skills)

    def test_a_posting_about_practices_highlights_practices(self) -> None:
        """Competências are not only technologies — the engineer posting wants both."""
        highlighted = domain.adapt(master(), target(ENGINEER)).highlighted_skills

        assert "Arquitetura de software" in highlighted
        assert "Liderança técnica" in highlighted

    def test_the_relevant_project_is_selected_per_posting(self) -> None:
        source = master()
        react = domain.adapt(source, target(FULLSTACK_REACT))
        python = domain.adapt(source, target(PYTHON))

        assert any(project["name"] == "Design system interno" for project in react.projects)
        assert any(
            project["name"] == "Motor de conciliação financeira" for project in python.projects
        )

    def test_the_fit_score_differs_and_is_explained(self) -> None:
        source = master()
        scores = {
            raw["title"]: domain.adapt(source, target(raw)).fit_score for raw in DEMO_JOBS
        }

        assert len(set(scores.values())) > 1
        for raw in DEMO_JOBS:
            adapted = domain.adapt(source, target(raw))
            assert adapted.fit_factors, raw["title"]
            assert sum(factor.weight_pct for factor in adapted.fit_factors) == 100


class TestTheSameExperienceReadsDifferently:
    def test_one_employer_leads_with_different_bullets_per_posting(self) -> None:
        """The requirement from the brief, asserted on the same employer."""
        source = master()
        for_dotnet = experience(domain.adapt(source, target(BACKEND_DOTNET)), "Globalthings")
        for_react = experience(domain.adapt(source, target(FULLSTACK_REACT)), "Globalthings")

        assert for_dotnet.responsibilities != for_react.responsibilities
        assert "ASP.NET Core" in for_dotnet.responsibilities[0]
        assert "React" in for_react.responsibilities[0]
        # The facts about the position never move with the emphasis.
        assert for_dotnet.role == for_react.role
        assert for_dotnet.started_on == for_react.started_on
        assert set(for_dotnet.responsibilities) == set(for_react.responsibilities)

    def test_reordering_is_reported_rather_than_left_implicit(self) -> None:
        adapted = domain.adapt(master(), target(BACKEND_DOTNET))

        kinds = {change.kind for change in adapted.changes}
        assert "experience_prioritized" in kinds
        assert kinds <= set(domain.CHANGE_KINDS)
        # And no change ever claims something was added.
        assert "experience_added" not in kinds

    def test_an_unrelated_experience_still_appears(self) -> None:
        """Employment history with a hole in it reads as a lie, so nothing is dropped."""
        source = master()

        for raw in DEMO_JOBS:
            adapted = domain.adapt(source, target(raw))
            assert len(adapted.experiences) == len(source.experiences)
            assert all(entry.responsibilities for entry in adapted.experiences)


class TestNothingIsInvented:
    def test_every_sentence_was_already_in_the_master(self) -> None:
        source = master()
        written = {
            sentence
            for entry in source.experiences
            for sentence in (*entry.responsibilities, *entry.results, entry.summary)
        }

        for raw in DEMO_JOBS:
            for entry in domain.adapt(source, target(raw)).experiences:
                for sentence in (*entry.responsibilities, *entry.results):
                    assert sentence in written

    def test_the_invention_guard_finds_nothing_in_any_adapted_resume(self) -> None:
        """Checked with the same guard the AI path uses, over the same source text."""
        source = master()

        for raw in DEMO_JOBS:
            adapted = domain.adapt(source, target(raw))
            rendered = "\n".join(
                [
                    adapted.headline or "",
                    adapted.summary or "",
                    " ".join(adapted.skills),
                    *(
                        "\n".join(
                            [
                                entry.role,
                                entry.company,
                                entry.summary,
                                *entry.responsibilities,
                                *entry.results,
                                *entry.technologies,
                            ]
                        )
                        for entry in adapted.experiences
                    ),
                ]
            )
            flags = flag_unsupported_skills(source.searchable(), rendered)
            assert flags == [], f"{raw['title']} introduced {flags}"

    def test_a_gap_is_surfaced_and_never_written_into_the_document(self) -> None:
        adapted = domain.adapt(master(), target(BACKEND_DOTNET))

        uncovered = [term.casefold() for term in adapted.uncovered_requirements]
        assert "elixir" in uncovered
        assert not any("elixir" in skill.casefold() for skill in adapted.skills)
        assert not any(
            "elixir" in term.casefold() for term in adapted.emphasized_technologies
        )

    def test_identity_is_copied_verbatim(self) -> None:
        source = master()

        for raw in DEMO_JOBS:
            adapted = domain.adapt(source, target(raw))
            assert adapted.headline == source.headline
            assert adapted.summary == source.summary


class TestDeterminism:
    def test_the_same_input_adapts_the_same_way_every_time(self) -> None:
        """No model, no clock, no randomness — the reason this is testable at all."""
        source = master()
        first = domain.adapt(source, target(APIS))
        second = domain.adapt(source, target(APIS))

        assert first == second

    def test_the_fingerprint_tracks_the_master_and_nothing_else(self) -> None:
        source = master()
        same = domain.adapt(source, target(APIS)).fingerprint
        other_posting = domain.adapt(source, target(PYTHON)).fingerprint

        # The fingerprint answers "which master was this derived from", so two
        # postings share it and a master edit changes it.
        assert same == other_posting == domain.fingerprint(source)
