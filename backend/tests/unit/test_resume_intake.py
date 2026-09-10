"""Reading an uploaded resume into a proposal the user confirms.

Two things are worth testing here and they are not the same thing. One is that
a realistic CV comes back with its positions, dates and technologies in the
right fields. The other — the one that matters more — is that **nothing comes
back that the document did not say**. The second is asserted structurally, by
checking every emitted string against the source text, so a future heuristic
that starts guessing job titles fails here rather than in someone's profile.
"""

from __future__ import annotations

from datetime import date

from app.domain.language import fold
from app.domain.resume_intake import ResumeIntake, extract

PORTUGUESE_CV = """\
João Victor Uchôa
Desenvolvedor Full Stack
Recife, PE
joao@example.com | +55 (81) 99999-1234 | linkedin.com/in/joaovictor

RESUMO
Desenvolvedor full stack com quatro anos construindo APIs em C# e .NET e
interfaces em React.

EXPERIÊNCIA PROFISSIONAL

Desenvolvedor Full Stack — GlobalThings
Jan 2023 - Presente · Recife, PE
- Construí APIs REST em .NET 8 consumidas por um painel React.
- Migrei relatórios de SQL Server para PostgreSQL, reduzindo a carga em 40%.

Estagiário de Desenvolvimento — CESAR
02/2021 - 12/2022
- Automação de testes de regressão com Playwright.

FORMAÇÃO
Bacharelado em Ciência da Computação — CESAR School (2020 — 2024)

TECNOLOGIAS
C#, .NET, React, TypeScript, PostgreSQL, Docker

IDIOMAS
Português (nativo), Inglês (avançado)
"""

ENGLISH_CV = """\
Jane Doe
Senior Backend Engineer
London, United Kingdom
jane@example.com

SUMMARY
Backend engineer with six years in Python and distributed systems.

WORK EXPERIENCE
Senior Backend Engineer | Acme Ltd
March 2020 - Present
- Designed gRPC services in Go and Python.
- Ran the migration from MySQL to PostgreSQL.

EDUCATION
BSc Computer Science | University of London (2013 - 2017)

SKILLS
Python, Go, Kubernetes, AWS, PostgreSQL
"""


class TestAPortugueseResume:
    def test_reads_the_header(self) -> None:
        intake = extract(PORTUGUESE_CV)

        assert intake.full_name == "João Victor Uchôa"
        assert intake.headline == "Desenvolvedor Full Stack"
        assert intake.location == "Recife, PE"
        assert intake.email == "joao@example.com"
        assert intake.phone is not None and "99999" in intake.phone

    def test_reads_the_summary_section_rather_than_the_header_prose(self) -> None:
        intake = extract(PORTUGUESE_CV)

        assert intake.summary is not None
        assert intake.summary.startswith("Desenvolvedor full stack com quatro anos")

    def test_splits_the_positions_with_their_periods(self) -> None:
        intake = extract(PORTUGUESE_CV)

        assert len(intake.experiences) == 2
        current, internship = intake.experiences

        assert current.role == "Desenvolvedor Full Stack"
        assert current.company == "GlobalThings"
        assert current.started_on == date(2023, 1, 1)
        assert current.is_current is True
        assert current.ended_on is None
        assert current.location == "Recife, PE"

        assert internship.role == "Estagiário de Desenvolvimento"
        assert internship.company == "CESAR"
        assert internship.started_on == date(2021, 2, 1)
        assert internship.ended_on == date(2022, 12, 31)
        assert internship.is_current is False

    def test_keeps_each_bullet_as_its_own_achievement(self) -> None:
        current = extract(PORTUGUESE_CV).experiences[0]

        assert len(current.responsibilities) == 2
        assert current.responsibilities[0].startswith("Construí APIs REST")
        # The bullet marker itself is not part of the sentence.
        assert not current.responsibilities[0].startswith("-")

    def test_tags_each_position_with_the_technologies_it_names(self) -> None:
        current, internship = extract(PORTUGUESE_CV).experiences

        assert {fold(term) for term in current.technologies} >= {".net", "react", "postgresql"}
        # Playwright belongs to the internship, and only to it.
        assert any(fold(term) == "playwright" for term in internship.technologies)
        assert all(fold(term) != "playwright" for term in current.technologies)

    def test_reads_the_technology_list_with_its_own_spelling(self) -> None:
        intake = extract(PORTUGUESE_CV)

        assert ".NET" in intake.skills, intake.skills
        assert "C#" in intake.skills
        assert "TypeScript" in intake.skills

    def test_reads_education_and_languages(self) -> None:
        intake = extract(PORTUGUESE_CV)

        assert len(intake.education) == 1
        assert intake.education[0].degree == "Bacharelado em Ciência da Computação"
        assert intake.education[0].institution == "CESAR School"
        assert [fold(entry).split()[0] for entry in intake.languages] == ["portugues", "ingles"]

    def test_reports_no_gaps_on_a_resume_it_read_completely(self) -> None:
        assert extract(PORTUGUESE_CV).warnings == ()


class TestAnEnglishResume:
    def test_reads_a_pipe_separated_title_line(self) -> None:
        intake = extract(ENGLISH_CV)

        assert len(intake.experiences) == 1
        position = intake.experiences[0]
        assert position.role == "Senior Backend Engineer"
        assert position.company == "Acme Ltd"
        assert position.started_on == date(2020, 3, 1)
        assert position.is_current is True

    def test_reads_the_header_and_the_skills(self) -> None:
        intake = extract(ENGLISH_CV)

        assert intake.full_name == "Jane Doe"
        assert intake.location == "London, United Kingdom"
        assert "Kubernetes" in intake.skills
        assert intake.education[0].institution == "University of London"


class TestItNeverInventsAnything:
    """Every string handed back has to be quotable from the uploaded file.

    This is the same guarantee `app.domain.resume` makes about the adapted
    resume, applied one step earlier: a proposal the user confirms with one
    click must not slip a job title, an employer or a technology into their
    profile that their CV never mentioned.
    """

    @staticmethod
    def _strings(intake: ResumeIntake) -> list[str]:
        values: list[str] = [
            value
            for value in (
                intake.full_name,
                intake.headline,
                intake.location,
                intake.email,
                intake.phone,
                intake.summary,
            )
            if value
        ]
        values += list(intake.skills)
        values += list(intake.languages)
        values += list(intake.certifications)
        for experience in intake.experiences:
            values += [
                experience.role,
                experience.company,
                experience.period_text,
                experience.summary,
                *experience.responsibilities,
                *experience.technologies,
            ]
            extra = (experience.location, experience.employment_type)
            values += [value for value in extra if value]
        for entry in intake.education:
            values += [entry.degree, entry.institution, entry.period_text]
        for project in intake.projects:
            values += [project.name, project.description, *project.technologies]
        return [value for value in values if value.strip()]

    def test_every_extracted_string_appears_in_the_source(self) -> None:
        for source in (PORTUGUESE_CV, ENGLISH_CV):
            haystack = fold(" ".join(source.split()))
            for value in self._strings(extract(source)):
                needle = fold(" ".join(value.split()))
                assert needle in haystack, f"{value!r} is not in the uploaded resume"

    def test_a_technology_the_resume_never_names_is_never_proposed(self) -> None:
        intake = extract(PORTUGUESE_CV)

        proposed = {fold(term) for term in intake.skills}
        for experience in intake.experiences:
            proposed |= {fold(term) for term in experience.technologies}
        assert "kubernetes" not in proposed
        assert "rust" not in proposed


class TestADocumentItCannotRead:
    def test_an_empty_file_is_a_warning_not_a_crash(self) -> None:
        intake = extract("   \n\n  ")

        assert intake.is_empty
        assert intake.warnings and "legível" in intake.warnings[0]

    def test_prose_with_no_sections_reports_the_missing_experience(self) -> None:
        intake = extract("Sou desenvolvedor e gosto de Python.\nProcuro uma vaga nova.")

        assert intake.experiences == ()
        assert any("experiências" in warning for warning in intake.warnings)
        # The technologies it did name are still an honest starting point.
        assert any(fold(term) == "python" for term in intake.skills)

    def test_a_position_with_no_company_is_flagged_rather_than_guessed(self) -> None:
        intake = extract(
            "EXPERIÊNCIA\nDesenvolvedor\n2019 - 2021\n- Mantive um sistema legado.\n"
        )

        assert len(intake.experiences) == 1
        assert intake.experiences[0].company == ""
        assert intake.experiences[0].is_complete is False
        assert any("sem empresa" in warning for warning in intake.warnings)
