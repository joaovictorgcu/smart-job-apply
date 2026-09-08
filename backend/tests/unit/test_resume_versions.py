"""The rules behind one resume per application, tested without a database.

The promise being checked is narrow and testable: the same history, told
differently for each posting, with nothing invented and nothing rewritten.
Every assertion here is about the derivation itself — no session, no HTTP, no
model call.
"""

from __future__ import annotations

import pytest

from app.domain.document_resume import (
    CONDENSED_HIGHLIGHTS,
    ResumeDocument,
    build_document,
    document_fingerprint,
    extract_focus,
    fold,
    identity_conflicts,
    render_plain_text,
    tailor_for_posting,
    vocabulary,
)
from tests.fixtures.resumes import MASTER_PROFILE, POSTINGS


def master() -> ResumeDocument:
    return build_document(
        headline=MASTER_PROFILE["headline"],
        summary=MASTER_PROFILE["summary"],
        skills=MASTER_PROFILE["skills"],
        technologies=MASTER_PROFILE["technologies"],
        experiences=MASTER_PROFILE["experiences"],
        projects=MASTER_PROFILE["projects"],
        education=MASTER_PROFILE["education"],
        certifications=MASTER_PROFILE["certifications"],
        languages=["pt-BR", "en"],
    )


def derive(key: str) -> ResumeDocument:
    posting = POSTINGS[key]
    return tailor_for_posting(
        master(), title=posting["title"], description=posting["description"]
    ).document


class TestFocus:
    def test_ranks_the_candidates_own_terms_by_what_the_posting_asks(self) -> None:
        posting = POSTINGS["dotnet"]

        focus = extract_focus(master(), title=posting["title"], description=posting["description"])

        assert focus.terms
        # The title carries the weight, so the term in it leads.
        assert ".NET 8" in focus.terms[:2]
        assert focus.weight(".NET 8") > focus.weight("SQL Server")

    def test_never_names_a_term_the_candidate_does_not_have(self) -> None:
        """The invention guarantee, at its source.

        A posting can demand whatever it likes; the focus is an intersection
        with the candidate's own vocabulary, so a technology they never listed
        cannot enter the resume through here.
        """
        focus = extract_focus(
            master(),
            title="Engenheiro Rust Sênior",
            description="Rust, Kubernetes e Terraform em produção. Go é um plus.",
        )

        assert focus.terms == ()
        assert "rust" not in {fold(term) for term in vocabulary(master())}

    def test_a_posting_with_no_overlap_leaves_the_resume_untouched(self) -> None:
        version = tailor_for_posting(
            master(), title="Engenheiro Rust", description="Rust e Kubernetes."
        )

        assert version.changes == ()
        assert version.focus == ()
        assert document_fingerprint(version.document) == document_fingerprint(master())


class TestOnePostingOneResume:
    @pytest.mark.parametrize(
        ("posting", "expected_company"),
        [
            ("dotnet", "Globalthings"),
            ("fullstack", "Nexo Digital"),
            ("python", "DataLab"),
        ],
    )
    def test_the_most_relevant_experience_leads(self, posting: str, expected_company: str) -> None:
        document = derive(posting)

        assert document.experiences[0].company == expected_company

    def test_four_postings_produce_four_different_resumes(self) -> None:
        """The headline behaviour: N applications, N genuinely different resumes."""
        fingerprints = {key: document_fingerprint(derive(key)) for key in POSTINGS}

        assert len(set(fingerprints.values())) == len(POSTINGS)
        assert document_fingerprint(master()) not in set(fingerprints.values())

    def test_the_same_experience_is_described_differently_per_posting(self) -> None:
        """One job, three framings — .NET here, APIs there, SQL elsewhere."""
        dotnet = derive("dotnet").experience("globalthings-tech-lead")
        apis = derive("apis").experience("globalthings-tech-lead")
        python = derive("python").experience("globalthings-tech-lead")

        assert dotnet is not None and apis is not None and python is not None
        summaries = {dotnet.summary, apis.summary, python.summary}
        assert len(summaries) == 3
        assert ".NET 8" in (dotnet.summary or "")
        assert "APIs REST" in (apis.summary or "")
        # The Python posting reaches this job only through the SQL it also
        # asks for, so that — and nothing else — is what it emphasizes here.
        assert python.focus == ["SQL"]
        assert "SQL" in (python.summary or "")
        assert ".NET" not in (python.summary or "")

    def test_the_leading_achievement_follows_the_posting(self) -> None:
        dotnet = derive("dotnet").experience("nexo-fullstack")
        fullstack = derive("fullstack").experience("nexo-fullstack")

        assert dotnet is not None and fullstack is not None
        # Same list of achievements, opened differently.
        assert "APIs REST" in dotnet.highlights[0].text
        assert "React" in fullstack.highlights[0].text
        assert {item.text for item in dotnet.highlights} == {
            item.text for item in fullstack.highlights
        }

    def test_technologies_and_skills_lead_with_what_was_asked_for(self) -> None:
        document = derive("python")

        assert document.technologies[0] in {"Python", "FastAPI", "Airflow"}

    def test_the_derivation_is_deterministic(self) -> None:
        first = derive("dotnet")
        second = derive("dotnet")

        assert document_fingerprint(first) == document_fingerprint(second)


class TestNothingIsInventedOrRewritten:
    def test_every_word_in_a_version_comes_from_the_master(self) -> None:
        """No technology may appear in a version that the master lacks."""
        master_terms = {fold(term) for term in vocabulary(master())}

        for key in POSTINGS:
            for experience in derive(key).experiences:
                for term in experience.technologies:
                    assert fold(term) in master_terms, f"{term} appeared in the {key} version"

    def test_company_role_and_period_survive_every_derivation(self) -> None:
        expected = {experience.key: experience.identity for experience in master().experiences}

        for key in POSTINGS:
            document = derive(key)
            assert set(document.experience_keys) == set(expected)
            for experience in document.experiences:
                assert experience.identity == expected[experience.key]

    def test_an_irrelevant_experience_is_condensed_but_never_dropped(self) -> None:
        """A job with nothing in common with the posting stays in the resume.

        Built from a two-position document rather than the full fixture,
        because in a real history almost everything overlaps a little — and the
        rule being checked here is what happens at exactly zero overlap.
        """
        document = build_document(
            technologies=["Python", "Delphi"],
            experiences=[
                {
                    "company": "Nova",
                    "role": "Engenheira Python",
                    "start": "2022-01",
                    "technologies": ["Python"],
                    "highlights": [{"text": "Serviços em Python.", "technologies": ["Python"]}],
                },
                {
                    "company": "Antiga",
                    "role": "Analista",
                    "start": "2012-01",
                    "end": "2015-12",
                    "summary": "Manutenção do ERP legado.",
                    "technologies": ["Delphi"],
                    "highlights": [
                        {"text": "Telas de faturamento em Delphi.", "technologies": ["Delphi"]},
                        {"text": "Relatórios operacionais.", "technologies": ["Delphi"]},
                        {"text": "Rotinas de fechamento.", "technologies": ["Delphi"]},
                    ],
                },
            ],
        )

        version = tailor_for_posting(
            document, title="Pessoa Engenheira Python", description="Python no dia a dia."
        )
        legacy = version.document.experience("antiga-analista-2012-01")

        assert legacy is not None
        assert len(legacy.highlights) == CONDENSED_HIGHLIGHTS
        # Still a full entry: employer, role, dates and its own wording intact.
        assert legacy.company == "Antiga"
        assert legacy.summary == "Manutenção do ERP legado."
        assert legacy.focus == []
        assert any(change.action == "condensed" for change in version.changes)

    def test_the_change_list_explains_the_derivation(self) -> None:
        version = tailor_for_posting(
            master(),
            title=POSTINGS["dotnet"]["title"],
            description=POSTINGS["dotnet"]["description"],
        )

        actions = {change.action for change in version.changes}
        assert "rephrased" in actions
        assert {change.section for change in version.changes} & {"Resumo", "Experiência"}
        # No "added": the vocabulary has no such action, by design.
        assert "added" not in actions

    def test_the_master_document_is_never_mutated(self) -> None:
        before = document_fingerprint(master())

        source = master()
        tailor_for_posting(
            source, title=POSTINGS["apis"]["title"], description=POSTINGS["apis"]["description"]
        )

        assert document_fingerprint(source) == before


class TestIdentityGuard:
    def test_a_changed_employer_is_a_conflict(self) -> None:
        base = master()
        edited = base.model_copy(deep=True)
        edited.experiences[0].company = "Outra Empresa"

        assert identity_conflicts(base, edited) == [edited.experiences[0].key]

    def test_an_experience_the_master_never_had_is_a_conflict(self) -> None:
        base = master()
        edited = base.model_copy(deep=True)
        edited.experiences.append(
            base.experiences[0].model_copy(
                deep=True, update={"key": "inventada", "company": "Empresa Fantasma"}
            )
        )

        assert identity_conflicts(base, edited) == ["inventada"]

    def test_re_emphasizing_is_not_a_conflict(self) -> None:
        base = master()
        edited = base.model_copy(deep=True)
        edited.experiences.reverse()
        edited.experiences[0].summary = "Outra ênfase, mesma história."
        edited.experiences[0].highlights = edited.experiences[0].highlights[:1]

        assert identity_conflicts(base, edited) == []


class TestDocumentPlumbing:
    def test_an_experience_gets_a_stable_key_when_none_is_given(self) -> None:
        document = build_document(
            experiences=[{"company": "Acme Ltda", "role": "Dev Sênior", "start": "2020-01"}]
        )

        assert document.experiences[0].key == "acme-ltda-dev-senior-2020-01"

    def test_two_identical_positions_do_not_collide(self) -> None:
        entry = {"company": "Acme", "role": "Dev", "start": "2020-01"}

        document = build_document(experiences=[dict(entry), dict(entry)])

        assert len(set(document.experience_keys)) == 2

    def test_plain_text_carries_every_structured_claim(self) -> None:
        """What the invention guard checks against has to include the history."""
        text = fold(render_plain_text(master()))

        assert "airflow" in text
        assert "globalthings" in text
        assert "p95 de 420 ms para 120 ms" in text

    def test_an_empty_document_is_reported_as_empty(self) -> None:
        assert build_document().is_empty
        assert not master().is_empty
