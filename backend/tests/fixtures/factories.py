"""Factories for ORM rows and automation contract objects.

Delays default to zero on every created `UserSettings` so no test ever waits on a
production-shaped humanization delay, and `dry_run` defaults to True to mirror the
application's own default.
"""

from __future__ import annotations

import itertools
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.automation.contracts import FormQuestion, JobPosting, ProfileContext, QuestionKind
from app.database.base import utcnow
from app.models import (
    AIAnalysis,
    AnalysisKind,
    Application,
    ApplicationStatus,
    AutomationRun,
    AutomationRunKind,
    AutomationRunStatus,
    Experience,
    Job,
    JobStatus,
    LinkedInAccount,
    Profile,
    Search,
    User,
    UserSettings,
)

# Long enough for the 10-character minimum on RegisterRequest.
DEFAULT_PASSWORD = "correct-horse-battery"

_counter = itertools.count(1)


def next_id() -> int:
    """Monotonic counter for unique emails and external ids within a test."""
    return next(_counter)


async def create_user(
    session: AsyncSession,
    *,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    full_name: str | None = "Test User",
    is_active: bool = True,
    is_admin: bool = False,
    with_profile: bool = True,
    with_settings: bool = True,
    with_linkedin: bool = True,
    linkedin_connected: bool = True,
    profile: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> User:
    """A user with the profile, settings and LinkedIn rows the app expects."""
    user = User(
        email=email or f"user{next_id()}@example.com",
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=is_active,
        is_admin=is_admin,
    )
    session.add(user)
    await session.flush()

    if with_profile:
        defaults: dict[str, Any] = {
            "headline": "Senior Backend Engineer",
            "location": "Remote",
            "phone": "+1 555 0100",
            "years_of_experience": 7,
            "summary": "Backend engineer focused on Python and distributed systems.",
            "resume_text": "Python, FastAPI, PostgreSQL, Playwright, seven years of experience.",
            "resume_filename": "resume.pdf",
            "skills": ["Python", "FastAPI", "SQL", "Docker"],
            "preferred_languages": ["en"],
            "answer_bank": {
                "salary_expectation": "120000",
                "notice_period": "30 days",
                "work_authorization": "Yes",
            },
        }
        defaults.update(profile or {})
        session.add(Profile(user_id=user.id, **defaults))

    if with_settings:
        # Zero delays: humanization is asserted explicitly in the throttle tests,
        # never paid for by every other test.
        settings_defaults: dict[str, Any] = {
            "daily_cap": 15,
            "min_score": 70,
            "action_delay_min": 0.0,
            "action_delay_max": 0.0,
            "apply_delay_min": 0.0,
            "apply_delay_max": 0.0,
            "working_hour_start": 0,
            "working_hour_end": 24,
            "require_manual_approval": True,
            "dry_run": True,
            "cover_letter_tone": "professional",
            "content_language": "en",
            "generate_cover_letter": True,
        }
        settings_defaults.update(settings or {})
        session.add(UserSettings(user_id=user.id, **settings_defaults))

    if with_linkedin:
        session.add(
            LinkedInAccount(
                user_id=user.id,
                display_name="Test Candidate",
                is_connected=linkedin_connected,
                last_verified_at=utcnow() if linkedin_connected else None,
            )
        )

    await session.flush()
    await session.commit()
    await session.refresh(user)
    return user


async def create_search(session: AsyncSession, user: User, **overrides: Any) -> Search:
    values: dict[str, Any] = {
        "name": "Backend roles",
        "keywords": "python backend engineer",
        "location": "Remote",
        "remote_filter": "remote",
        "experience_levels": ["mid", "senior"],
        "date_posted": "week",
        "easy_apply_only": True,
        "max_results": 25,
        "is_active": True,
    }
    values.update(overrides)
    search = Search(user_id=user.id, **values)
    session.add(search)
    await session.flush()
    await session.commit()
    await session.refresh(search)
    return search


async def create_job(session: AsyncSession, user: User, **overrides: Any) -> Job:
    index = next_id()
    values: dict[str, Any] = {
        "external_id": f"ext-{index}",
        "title": "Senior Backend Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "url": f"https://www.linkedin.com/jobs/view/{index}",
        "description": "We need a Python engineer with FastAPI and SQL experience.",
        "workplace_type": "remote",
        "easy_apply": True,
        "detected_language": "en",
        "status": JobStatus.DISCOVERED,
    }
    values.update(overrides)
    job = Job(user_id=user.id, **values)
    session.add(job)
    await session.flush()
    await session.commit()
    await session.refresh(job)
    return job


async def create_application(
    session: AsyncSession, user: User, job: Job, **overrides: Any
) -> Application:
    values: dict[str, Any] = {
        "status": ApplicationStatus.AWAITING_REVIEW,
        "cover_letter": "I would be glad to contribute to this team.",
        "screening_answers": [
            {
                "question": "Years of Python experience?",
                "answer": "7",
                "question_type": "number",
                "confidence": "high",
                "needs_review": False,
                "field_id": "q-years",
            }
        ],
        "resume_filename": "resume.pdf",
        "total_steps": 3,
        "current_step": 3,
        "needs_human_input": False,
        "was_dry_run": False,
    }
    values.update(overrides)
    application = Application(user_id=user.id, job_id=job.id, **values)
    session.add(application)
    await session.flush()
    await session.commit()
    await session.refresh(application)
    return application


async def create_run(session: AsyncSession, user: User, **overrides: Any) -> AutomationRun:
    values: dict[str, Any] = {
        "kind": AutomationRunKind.SEARCH,
        "status": AutomationRunStatus.PENDING,
        "dry_run": True,
        "started_at": utcnow(),
    }
    values.update(overrides)
    run = AutomationRun(user_id=user.id, **values)
    session.add(run)
    await session.flush()
    await session.commit()
    await session.refresh(run)
    return run


async def create_analysis(
    session: AsyncSession, user: User, job: Job | None = None, **overrides: Any
) -> AIAnalysis:
    values: dict[str, Any] = {
        "kind": AnalysisKind.SCORING,
        "model": "claude-opus-5",
        "result": {"score": 85, "recommend_apply": True},
        "input_tokens": 1200,
        "output_tokens": 180,
        "latency_ms": 640,
        "was_refusal": False,
    }
    values.update(overrides)
    analysis = AIAnalysis(user_id=user.id, job_id=job.id if job is not None else None, **values)
    session.add(analysis)
    await session.flush()
    await session.commit()
    await session.refresh(analysis)
    return analysis


def make_job_posting(**overrides: Any) -> JobPosting:
    index = next_id()
    values: dict[str, Any] = {
        "external_id": f"posting-{index}",
        "title": "Senior Backend Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "url": f"https://www.linkedin.com/jobs/view/{index}",
        "description": "Python, FastAPI and SQL. Remote friendly.",
        "workplace_type": "remote",
        "easy_apply": True,
        "posted_at": utcnow() - timedelta(days=1),
        "already_applied": False,
    }
    values.update(overrides)
    return JobPosting(**values)


def make_form_question(
    field_id: str = "q-1",
    label: str = "Years of Python experience?",
    kind: QuestionKind = "number",
    *,
    options: list[str] | None = None,
    required: bool = True,
    current_value: str | None = None,
) -> FormQuestion:
    return FormQuestion(
        field_id=field_id,
        label=label,
        kind=kind,
        options=options or [],
        required=required,
        current_value=current_value,
    )


async def create_demo_user(session: AsyncSession, **overrides: Any) -> User:
    """A user whose master resume is the rich demo document, history included.

    The default factory profile is deliberately thin — four skills and one line
    of resume text — which is right for the tests that only need *a* profile and
    useless for the per-application resume tests: a candidate with four skills
    produces five near-identical adaptations however good the engine is. This
    hands over the same master resume `scripts/seed_demo.py` seeds, so what the
    tests assert and what a demo shows are the same thing.

    The two halves are written the way the app writes them: the unstructured
    fields onto `Profile`, and the history as `Experience` rows. An earlier
    version passed the whole demo dict as `Profile(**...)` kwargs, which cannot
    work — the history is its own table — and went unnoticed because nothing
    called this helper.
    """
    from app.demo import demo_experiences, demo_profile_fields
    from app.models.resume import Experience

    profile = {**demo_profile_fields(), **(overrides.pop("profile", None) or {})}
    with_experiences = overrides.pop("with_experiences", True)
    user = await create_user(
        session,
        email=overrides.pop("email", None) or f"demo{next_id()}@example.com",
        full_name=overrides.pop("full_name", "Alex Moreira"),
        profile=profile,
        **overrides,
    )

    if with_experiences:
        for entry in demo_experiences():
            session.add(Experience(user_id=user.id, **entry))
        await session.flush()
        await session.commit()
    return user


async def create_demo_jobs(
    session: AsyncSession, user: User, count: int | None = None
) -> list[Job]:
    """The demo postings, as `Job` rows — five vacancies that pull one resume apart.

    `count` above five cycles the descriptions with fresh external ids, so a test
    about "N applications" can ask for ten without inventing more copy.
    """
    from app.demo import DEMO_JOBS

    total = len(DEMO_JOBS) if count is None else count
    jobs: list[Job] = []
    for index in range(total):
        template = dict(DEMO_JOBS[index % len(DEMO_JOBS)])
        # `external_id` is unique per (user, external id); a cycled posting needs
        # its own or the second copy would be deduplicated away.
        template["external_id"] = f"{template['external_id']}-{index + 1}"
        jobs.append(await create_job(session, user, **template))
    return jobs


def make_profile_context(**overrides: Any) -> ProfileContext:
    values: dict[str, Any] = {
        "full_name": "Test User",
        "email": "owner@example.com",
        "headline": "Senior Backend Engineer",
        "location": "Remote",
        "phone": "+1 555 0100",
        "years_of_experience": 7,
        "summary": "Backend engineer focused on Python.",
        "resume_text": "Python, FastAPI, PostgreSQL, seven years of experience.",
        "skills": ["Python", "FastAPI", "SQL"],
        "answer_bank": {"salary_expectation": "120000", "notice_period": "30 days"},
        "preferred_languages": ["en"],
    }
    values.update(overrides)
    return ProfileContext(**values)


def days_ago(days: int) -> datetime:
    return utcnow() - timedelta(days=days)


# --------------------------------------------------------------------------- #
# The structured master resume
# --------------------------------------------------------------------------- #

# A coherent career, not four unrelated rows. Each position leans on a different
# stack, so the same history genuinely reorders itself per posting instead of the
# tests having to assert on a difference that was staged. Written in Portuguese
# because that is what a user of this app writes — and because it exercises the
# accent folding the term matching depends on.
RESUME_HISTORY: tuple[dict[str, Any], ...] = (
    {
        "company": "Globalthings",
        "role": "Engenheiro de Software Senior",
        "employment_type": "full_time",
        "location": "Recife, PE",
        "started_on": date(2022, 3, 1),
        "ended_on": None,
        "is_current": True,
        "summary": (
            "Responsavel pelas APIs corporativas e pelo portal web de gestao de acessos, "
            "de ponta a ponta."
        ),
        "responsibilities": [
            "Projetei e mantive APIs REST em C# e ASP.NET Core consumidas por 12 sistemas.",
            "Modelei e otimizei o banco PostgreSQL do gerenciador de acessos.",
            "Construi telas do portal em React e TypeScript integradas as APIs internas.",
            "Escrevi testes de integracao com xUnit cobrindo os fluxos de autenticacao.",
            "Conduzi revisoes de codigo e defini a arquitetura em camadas adotada pelo time.",
        ],
        "technologies": [
            "C#",
            ".NET",
            "ASP.NET Core",
            "PostgreSQL",
            "React",
            "TypeScript",
            "Docker",
            "Azure DevOps",
            "xUnit",
        ],
        "results": [
            "Reduzi o tempo de resposta medio das APIs de 800 ms para 210 ms.",
            "Levei a cobertura de testes do modulo de acesso de 18% para 74%.",
        ],
        "projects": [
            {
                "name": "Gerenciador de Acessos",
                "description": (
                    "Portal de gestao de acessos corporativos, API em .NET e front em React."
                ),
                "technologies": ["C#", ".NET", "React", "PostgreSQL"],
            }
        ],
        "position": 0,
    },
    {
        "company": "Nuvem Retail",
        "role": "Desenvolvedor Full Stack",
        "employment_type": "full_time",
        "location": "Remoto",
        "started_on": date(2020, 1, 6),
        "ended_on": date(2022, 2, 28),
        "is_current": False,
        "summary": "Frente de loja e checkout de um e-commerce com trafego nacional.",
        "responsibilities": [
            "Desenvolvi a vitrine e o checkout do e-commerce em React com Redux.",
            "Integrei o frontend a APIs REST de pagamento e logistica de terceiros.",
            "Implementei componentes acessiveis e responsivos no design system, em CSS.",
            "Mantive servicos Node que agregavam dados de estoque para a vitrine.",
        ],
        "technologies": ["React", "TypeScript", "Node", "JavaScript", "REST", "CSS", "Jest"],
        "results": [
            "Aumentei a conversao do checkout em 9% ao reescrever o fluxo em tres etapas.",
        ],
        "projects": [
            {
                "name": "Checkout em tres etapas",
                "description": "Reescrita do checkout em React, com testes em Jest.",
                "technologies": ["React", "TypeScript", "Jest"],
            }
        ],
        "position": 1,
    },
    {
        "company": "Instituto Dados Abertos",
        "role": "Engenheiro de Dados",
        "employment_type": "contract",
        "location": "Remoto",
        "started_on": date(2018, 6, 1),
        "ended_on": date(2019, 12, 20),
        "is_current": False,
        "summary": "Consolidacao de bases publicas em um painel aberto de gastos.",
        "responsibilities": [
            "Construi pipelines de ETL em Python com pandas para consolidar bases publicas.",
            "Automatizei as coletas com Airflow e publiquei os dados em PostgreSQL.",
            "Escrevi testes com pytest para as transformacoes mais sensiveis.",
        ],
        "technologies": ["Python", "pandas", "Airflow", "PostgreSQL", "pytest", "Docker"],
        "results": ["Reduzi de 6 horas para 25 minutos a consolidacao mensal."],
        "projects": [
            {
                "name": "Painel de gastos publicos",
                "description": "Painel aberto alimentado por pipelines em Python.",
                "technologies": ["Python", "pandas", "PostgreSQL"],
            }
        ],
        "position": 2,
    },
    {
        "company": "Auditar Sistemas",
        "role": "Analista de Qualidade de Software",
        "employment_type": "full_time",
        "location": "Recife, PE",
        "started_on": date(2016, 2, 1),
        "ended_on": date(2018, 5, 30),
        "is_current": False,
        "summary": "Qualidade e manutencao de sistemas legados de auditoria.",
        "responsibilities": [
            "Defini a estrategia de testes automatizados de regressao com Selenium.",
            "Refatorei modulos legados em Java para reduzir acoplamento.",
            "Documentei a arquitetura dos sistemas criticos e os critérios de qualidade.",
        ],
        "technologies": ["Java", "Selenium", "JUnit", "SQL", "Git"],
        "results": ["Cortei em 40% o retrabalho por defeitos encontrados em producao."],
        "projects": [],
        "position": 3,
    },
)

# The skills the profile lists, kept consistent with the history above so a
# highlighted skill is always something the experience can actually back.
RESUME_SKILLS: list[str] = [
    "C#",
    ".NET",
    "PostgreSQL",
    "React",
    "TypeScript",
    "Python",
    "Docker",
    "SQL",
    "Node",
    "Java",
]

# Four postings that lean on four different parts of the same history. These are
# the example vacancies the feature is meant to tell apart.
JOB_POSTINGS: dict[str, dict[str, str]] = {
    "dotnet": {
        "title": "Desenvolvedor Backend .NET Senior",
        "company": "Banco Meridiano",
        "description": (
            "Buscamos pessoa desenvolvedora backend com 5+ anos de experiencia em C# e "
            ".NET. Voce vai manter APIs REST em ASP.NET Core, modelar dados em "
            "PostgreSQL e cuidar das pipelines no Azure DevOps."
        ),
    },
    "fullstack": {
        "title": "Pessoa Desenvolvedora Full Stack",
        "company": "Trilha Educacao",
        "description": (
            "Time de produto procurando alguem confortavel no frontend: React, "
            "TypeScript e CSS, consumindo APIs REST. Ha tambem servicos em Node "
            "para manter. Desejavel experiencia com Jest."
        ),
    },
    "python": {
        "title": "Engenheiro de Dados Python",
        "company": "Agro Insights",
        "description": (
            "Vaga para engenharia de dados: Python e pandas no dia a dia, orquestracao "
            "com Airflow e cargas em PostgreSQL. Minimo de 3 anos na area."
        ),
    },
    "engineering": {
        "title": "Engenheiro de Software - Arquitetura e Qualidade",
        "company": "Consorcio Atlas",
        "description": (
            "Foco em arquitetura, manutenibilidade e testes. Sistemas legados em Java, "
            "regressao automatizada com Selenium e testes de unidade com JUnit. "
            "Esperamos 4+ anos de experiencia."
        ),
    },
}


async def create_experience(session: AsyncSession, user: User, **overrides: Any) -> Experience:
    values: dict[str, Any] = {
        "company": "Globalthings",
        "role": "Engenheiro de Software Senior",
        "employment_type": "full_time",
        "location": "Recife, PE",
        "started_on": date(2022, 3, 1),
        "ended_on": None,
        "is_current": True,
        "summary": "APIs corporativas e portal web de gestao de acessos.",
        "responsibilities": ["Mantive APIs REST em C# e ASP.NET Core."],
        "technologies": ["C#", ".NET", "PostgreSQL"],
        "results": ["Reduzi a latencia media das APIs em 70%."],
        "projects": [],
        "position": 0,
    }
    values.update(overrides)
    experience = Experience(user_id=user.id, **values)
    session.add(experience)
    await session.flush()
    await session.commit()
    await session.refresh(experience)
    return experience


async def create_resume_history(session: AsyncSession, user: User) -> list[Experience]:
    """Seed the full four-position history and the matching profile skills.

    Both halves together: an adaptation reads the profile's skills and the
    positions, and seeding one without the other would make the highlighted
    skills disagree with the experience backing them.
    """
    rows = [Experience(user_id=user.id, **dict(entry)) for entry in RESUME_HISTORY]
    session.add_all(rows)

    profile = (
        await session.execute(select(Profile).where(Profile.user_id == user.id))
    ).scalar_one_or_none()
    if profile is not None:
        profile.skills = list(RESUME_SKILLS)

    await session.flush()
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows


async def create_posting_job(session: AsyncSession, user: User, kind: str, **overrides: Any) -> Job:
    """A job row for one of the four example vacancies in `JOB_POSTINGS`."""
    posting = JOB_POSTINGS[kind]
    values: dict[str, Any] = {**posting, "detected_language": "pt-BR"}
    values.update(overrides)
    return await create_job(session, user, **values)
