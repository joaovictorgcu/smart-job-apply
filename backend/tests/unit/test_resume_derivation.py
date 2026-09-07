"""The derivation engine: five postings, five different resumes, nothing invented.

These are the tests the feature lives or dies by, and they run with no API key,
no network and no database — which is the whole reason the structure is computed
deterministically instead of asked of a model. Every assertion here is about a
property that must hold for *any* posting, not about one golden string.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.ai.client import flag_unsupported_skills
from app.demo import DEMO_JOBS, demo_profile_fields
from app.domain.resume import MasterResume, derive

BACKEND_DOTNET, FULLSTACK_REACT, PYTHON, ENGINEER, APIS = DEMO_JOBS


def master() -> MasterResume:
    return MasterResume.from_profile(
        SimpleNamespace(full_name="Alex Moreira", **demo_profile_fields())
    )


def job(raw: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(**raw)


def experience(derivation: Any, company: str) -> Any:
    return next(
        entry for entry in derivation.sections.experiences if entry.company == company
    )


class TestDifferentJobsDifferentResumes:
    def test_every_posting_produces_its_own_document(self) -> None:
        """Five vacancies, five distinct resumes — the acceptance criterion itself."""
        documents = {raw["title"]: derive(master(), job(raw)).content for raw in DEMO_JOBS}

        assert len(set(documents.values())) == len(DEMO_JOBS)

    def test_each_posting_leads_with_the_experience_that_fits_it(self) -> None:
        leaders = {
            raw["title"]: derive(master(), job(raw)).sections.experiences[0].company
            for raw in DEMO_JOBS
        }

        assert leaders[BACKEND_DOTNET["title"]] == "Globalthings"
        assert leaders[FULLSTACK_REACT["title"]] == "Cofre Digital"
        assert leaders[PYTHON["title"]] == "Nexdata"
        assert leaders[APIS["title"]] == "Pagamentos Vertex"

    def test_the_focus_keywords_come_from_the_posting_not_the_resume_order(self) -> None:
        dotnet = derive(master(), job(BACKEND_DOTNET)).focus
        react = derive(master(), job(FULLSTACK_REACT)).focus

        assert dotnet.keywords[0] == ".NET"
        assert react.keywords[0] == "React"
        # A posting's own stack, not the union of everything the candidate has.
        assert "React" not in dotnet.keywords
        assert "Entity Framework" not in react.keywords

    def test_a_title_requirement_outranks_a_body_requirement(self) -> None:
        """The title states what the role *is*; the body also lists the nice-to-haves."""
        focus = derive(master(), job(PYTHON)).focus

        assert focus.keywords[0] == "Python"
        assert focus.keywords.index("Python") < focus.keywords.index("Docker")

    def test_the_seniority_of_the_posting_is_read(self) -> None:
        assert derive(master(), job(ENGINEER)).focus.level == "senior"


class TestExperiencesAreAdapted:
    def test_one_experience_reads_differently_for_two_postings(self) -> None:
        """The requirement from the brief, asserted on the same employer."""
        for_dotnet = experience(derive(master(), job(BACKEND_DOTNET)), "Globalthings")
        for_react = experience(derive(master(), job(FULLSTACK_REACT)), "Globalthings")

        assert for_dotnet.description != for_react.description
        assert "ASP.NET Core" in for_dotnet.description
        assert "React" in for_react.description

    def test_every_selected_sentence_was_already_in_the_master(self) -> None:
        """Adaptation is selection. No sentence is written, only chosen."""
        source = master()
        written = {
            highlight.text
            for entry in source.experiences
            for highlight in entry.highlights
        } | {entry.summary for entry in source.experiences}

        for raw in DEMO_JOBS:
            for entry in derive(source, job(raw)).sections.experiences:
                for line in entry.highlights:
                    assert line in written

    def test_the_bullets_left_out_are_recorded_rather_than_lost(self) -> None:
        derivation = derive(master(), job(PYTHON))
        globalthings = experience(derivation, "Globalthings")

        assert globalthings.omitted
        # Kept plus omitted accounts for every bullet the user wrote.
        original = next(
            entry for entry in master().experiences if entry.company == "Globalthings"
        )
        assert len(globalthings.highlights) + len(globalthings.omitted) == len(
            original.highlights
        )

    def test_an_unrelated_experience_still_appears_with_its_own_summary(self) -> None:
        """Employment history with a hole in it reads as a lie, so nothing is dropped."""
        derivation = derive(master(), job(ENGINEER))
        cofre = experience(derivation, "Cofre Digital")

        assert cofre.emphasis == "context"
        assert cofre.description
        assert len(derivation.sections.experiences) == len(master().experiences)

    def test_an_entrys_technologies_are_reordered_towards_the_posting(self) -> None:
        globalthings = experience(derive(master(), job(FULLSTACK_REACT)), "Globalthings")

        assert globalthings.technologies[0] == "React"
        # Reordered, not filtered: the entry still lists everything it involved.
        assert "PostgreSQL" in globalthings.technologies

    def test_relevance_and_emphasis_describe_the_same_ranking(self) -> None:
        entries = derive(master(), job(APIS)).sections.experiences

        assert [entry.relevance for entry in entries] == sorted(
            (entry.relevance for entry in entries), reverse=True
        )
        assert entries[0].emphasis == "lead"


class TestSkillsArePrioritised:
    def test_the_postings_skills_come_first_and_nothing_is_lost(self) -> None:
        source = master()
        sections = derive(source, job(BACKEND_DOTNET)).sections

        assert sections.prioritized_skills[0] == ".NET"
        assert "React" in sections.other_skills
        assert set(sections.prioritized_skills) | set(sections.other_skills) == set(source.skills)

    def test_two_postings_prioritise_different_skills(self) -> None:
        dotnet = derive(master(), job(BACKEND_DOTNET)).sections.prioritized_skills
        python = derive(master(), job(PYTHON)).sections.prioritized_skills

        assert dotnet != python
        assert "Entity Framework" in dotnet
        assert "FastAPI" in python

    def test_a_posting_about_practices_prioritises_practices(self) -> None:
        """Competências are not only technologies — the engineer posting asks for both."""
        prioritized = derive(master(), job(ENGINEER)).sections.prioritized_skills

        assert "Arquitetura de software" in prioritized
        assert "Liderança técnica" in prioritized


class TestNothingIsInvented:
    def test_the_invention_guard_finds_nothing_in_any_derived_resume(self) -> None:
        """The guarantee the whole feature rests on, checked by the same guard the AI path uses."""
        source = master()

        for raw in DEMO_JOBS:
            flags = flag_unsupported_skills(source.source_text, derive(source, job(raw)).content)
            assert flags == [], f"{raw['title']} introduced {flags}"

    def test_a_requirement_the_resume_cannot_back_is_surfaced_not_added(self) -> None:
        derivation = derive(master(), job(BACKEND_DOTNET))

        assert "elixir" in [item.casefold() for item in derivation.unsupported_requirements]
        assert "elixir" not in derivation.content.casefold()
        # And it never becomes something the resume claims to have.
        assert not any(
            "elixir" in term.casefold() for term in derivation.sections.prioritized_skills
        )

    def test_identity_and_history_are_copied_verbatim(self) -> None:
        source = master()

        for raw in DEMO_JOBS:
            sections = derive(source, job(raw)).sections
            assert sections.full_name == source.full_name
            assert sections.headline == source.headline
            assert sections.summary == source.summary
            assert sections.years_of_experience == source.years_of_experience
            by_id = {entry.id: entry for entry in source.experiences}
            for entry in sections.experiences:
                original = by_id[entry.id]
                assert entry.role == original.role
                assert entry.company == original.company
                assert entry.period == original.period

    def test_the_change_log_never_claims_to_have_added_anything(self) -> None:
        for raw in DEMO_JOBS:
            actions = {change["action"] for change in derive(master(), job(raw)).changes}
            assert actions <= {"reordered", "emphasized", "rephrased", "condensed", "omitted"}


class TestProjects:
    def test_relevant_projects_come_first(self) -> None:
        assert derive(master(), job(FULLSTACK_REACT)).sections.projects[0].name == (
            "Design system interno"
        )
        assert derive(master(), job(PYTHON)).sections.projects[0].name == (
            "Motor de conciliação financeira"
        )

    def test_no_project_is_dropped(self) -> None:
        source = master()

        for raw in DEMO_JOBS:
            assert len(derive(source, job(raw)).sections.projects) == len(source.projects)


class TestDeterminismAndDegradation:
    def test_the_same_input_derives_the_same_document_every_time(self) -> None:
        """No model, no clock, no randomness — the reason this is testable at all."""
        first = derive(master(), job(APIS))
        second = derive(master(), job(APIS))

        assert first.content == second.content
        assert first.sections.as_dict() == second.sections.as_dict()
        assert first.focus.as_dict() == second.focus.as_dict()

    def test_a_free_text_only_profile_still_derives(self) -> None:
        """The pre-feature profile shape: prose and skills, no structured entries."""
        legacy = MasterResume.from_profile(
            SimpleNamespace(
                full_name="Legacy User",
                headline="Backend engineer",
                summary="",
                location="Remote",
                years_of_experience=7,
                resume_text="Python, FastAPI and PostgreSQL for seven years.",
                skills=["Python", "FastAPI", "PostgreSQL"],
            )
        )
        derivation = derive(legacy, job(PYTHON))

        assert derivation.sections.experiences == ()
        assert "Python" in derivation.sections.prioritized_skills
        assert derivation.content.strip()

    def test_an_empty_master_is_reported_as_empty_rather_than_derived(self) -> None:
        assert MasterResume.from_profile(SimpleNamespace()).is_empty is True
        assert master().is_empty is False

    def test_a_posting_with_no_description_degrades_to_the_master_order(self) -> None:
        source = master()
        derivation = derive(source, SimpleNamespace(title="", company="", description=None))

        assert derivation.focus.keywords == ()
        assert derivation.sections.prioritized_skills == ()
        # Untailored, but complete and in the candidate's own order.
        assert [entry.company for entry in derivation.sections.experiences] == [
            entry.company for entry in source.experiences
        ]

    def test_malformed_structured_entries_are_skipped_not_fatal(self) -> None:
        """These columns are loose JSON; a bad row must not take the screen down."""
        resume = MasterResume.from_profile(
            SimpleNamespace(
                skills=["Python"],
                experiences=[None, "not a dict", {}, {"role": "Dev", "company": "Acme"}],
                projects=[{"description": "no name"}],
                education=[{"unexpected": "shape"}],
            )
        )

        assert len(resume.experiences) == 1
        assert resume.projects == ()
        assert resume.education == ()
