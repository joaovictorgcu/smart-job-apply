#!/usr/bin/env python3
"""Fill the database with believable data, so every screen has something on it.

`demo_server.py` gives you a working app with an empty database, which is the
right starting point but leaves most of the dashboard showing empty states. This
seeds a history: jobs across every status and score band, applications in every
status, outcomes spread over the whole pipeline, interview stages, per-job score
history, tailored resumes and an event timeline.

    python scripts/seed_mock.py --fresh

Everything is deterministic — a fixed RNG seed and dates anchored to a fixed
offset from today — so two runs produce the same database and a screenshot taken
against it does not drift.

The account it creates is written straight to the table with a bcrypt hash
rather than going through `register_user`. That is deliberate and is the only
way to have a short password without touching the rules: `RegisterRequest`
requires 10 characters and `LoginRequest` does not, so a seeded hash logs in
fine while the registration rule stays exactly as strict as it was.

Nothing here is real. The postings, companies and resume text are invented, and
no application has ever been sent anywhere.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_EMAIL = "admin@admin.com"
DEFAULT_PASSWORD = "123"

# Fixed, so the same run twice produces the same rows.
RNG = random.Random(20260907)
NOW = datetime.now(UTC).replace(microsecond=0)


def ago(days: float = 0, hours: float = 0) -> datetime:
    return NOW - timedelta(days=days, hours=hours)


def ahead(days: float) -> datetime:
    return NOW + timedelta(days=days)


# --------------------------------------------------------------------------- #
# Content
# --------------------------------------------------------------------------- #

COMPANIES = [
    ("Nubank", "São Paulo, SP"),
    ("Stone", "Rio de Janeiro, RJ"),
    ("iFood", "Campinas, SP"),
    ("Mercado Livre", "São Paulo, SP"),
    ("Loft", "São Paulo, SP"),
    ("QuintoAndar", "Remote"),
    ("Wildlife Studios", "São Paulo, SP"),
    ("PicPay", "Remote"),
    ("Creditas", "São Paulo, SP"),
    ("Gympass", "Remote"),
    ("Hotmart", "Belo Horizonte, MG"),
    ("Olist", "Curitiba, PR"),
    ("Neon", "São Paulo, SP"),
    ("Zenvia", "Remote"),
    ("Contabilizei", "Curitiba, PR"),
    ("Cortex", "Rio de Janeiro, RJ"),
    ("Grupo Boticário", "Curitiba, PR"),
    ("Alice", "Remote"),
]

TITLES = [
    "Senior Backend Engineer",
    "Backend Engineer (Python)",
    "Staff Software Engineer",
    "Platform Engineer",
    "Senior Python Developer",
    "Backend Engineer - Payments",
    "Site Reliability Engineer",
    "Data Platform Engineer",
    "Tech Lead - Backend",
    "Software Engineer II",
]

DESCRIPTION = (
    "We are hiring a backend engineer for a distributed team. You will own "
    "services in production: Python 3.11+, FastAPI, PostgreSQL and Docker on "
    "AWS, with Kafka between the write-heavy paths. Experience with async "
    "Python and with schema migrations under load is required. Fluent English "
    "is required for the weekly sync with the platform group. Nice to have: "
    "Kubernetes, Terraform, and previous exposure to a regulated domain."
)

SKILLS = [
    "Python",
    "FastAPI",
    "Django",
    "PostgreSQL",
    "Redis",
    "Docker",
    "Kubernetes",
    "AWS",
    "Terraform",
    "Kafka",
    "SQLAlchemy",
    "pytest",
    "TypeScript",
    "React",
    "GraphQL",
    "Airflow",
]

DIMENSIONS = ("skills", "experience", "seniority", "education", "location", "language")

REASONS = [
    "The posting's core stack (Python, FastAPI, PostgreSQL) is the candidate's daily work.",
    "Async Python at production scale appears in two of the listed roles.",
    "Migration-under-load experience is evidenced by the payments platform work.",
    "The seniority asked for is one level below what the profile already holds.",
    "Remote-first arrangement matches the candidate's stated preference.",
]

GAPS = [
    "Kubernetes is named as a requirement and is not evidenced in the resume.",
    "The posting asks for Go; the profile shows none.",
    "Regulated-domain experience (banking) is requested and not stated.",
    "Team-lead responsibility is expected and the profile shows individual contribution.",
]


def cover_letter(company: str, title: str) -> str:
    return (
        f"Dear {company} hiring team,\n\n"
        f"I am applying for the {title} position. Most of my last four years "
        "has been spent on async Python services backed by PostgreSQL — the "
        "same shape as the platform described in the posting — including two "
        "migrations run against live write traffic without a maintenance "
        "window.\n\n"
        "What draws me to this role specifically is that the posting talks "
        "about ownership in production rather than about ticket throughput. "
        "That is the way I prefer to work and the way I have worked.\n\n"
        "I would welcome the chance to go through any of it in detail.\n\n"
        "Kind regards,\nAlex Moreira"
    )


RESUME_TEXT = """# Alex Moreira
Senior Backend Engineer — São Paulo, Brazil

## Summary
Backend engineer with eight years on Python services in production. Owns
systems end to end: design, rollout, on-call. Comfortable with the parts that
are not the happy path — migrations under load, partial failure, and the
observability needed to tell one from the other.

## Experience

### Senior Backend Engineer, Fintech Platform (2023 - present)
- Rebuilt the settlement pipeline on FastAPI and PostgreSQL, cutting p99 from
  1.8s to 240ms while doubling throughput.
- Ran two schema migrations against live write traffic with no maintenance
  window, using expand-and-contract and a dual-read shim.
- Introduced structured logging and traces; mean time to diagnose fell from
  hours to minutes.

### Backend Engineer, Logistics (2020 - 2023)
- Owned the routing service: Python, Celery, Redis, ~4k requests/minute.
- Cut infrastructure spend 30% by replacing a polling design with Kafka
  consumers.
- Wrote the test harness the team still uses for integration coverage.

### Software Engineer, Agency (2018 - 2020)
- Django and PostgreSQL across a dozen client projects.

## Skills
Python, FastAPI, Django, SQLAlchemy, PostgreSQL, Redis, Kafka, Celery, Docker,
Terraform, AWS, pytest, TypeScript, React

## Education
BSc Computer Science, Universidade de São Paulo (2018)

## Languages
Portuguese (native), English (fluent), Spanish (intermediate)
"""

EXPERIENCES = [
    {
        "company": "Fintech Platform",
        "role": "Senior Backend Engineer",
        "employment_type": "full_time",
        "location": "São Paulo, SP",
        "started_on": date(2023, 2, 1),
        "ended_on": None,
        "is_current": True,
        "summary": "Owns the settlement pipeline end to end, including on-call.",
        "responsibilities": [
            "Design and operate the settlement and reconciliation services.",
            "Run schema migrations against live write traffic.",
            "Share the on-call rotation for the payments domain.",
        ],
        "technologies": ["Python", "FastAPI", "PostgreSQL", "Kafka", "AWS", "Terraform"],
        "results": [
            "p99 latency 1.8s -> 240ms while doubling throughput.",
            "Two zero-downtime migrations using expand-and-contract.",
        ],
        # `ProjectEntry` shaped, not bare strings: `ExperienceRead` validates
        # these on the way out, so a string here is a 500 on /profile.
        "projects": [
            {
                "name": "Settlement pipeline rewrite",
                "description": "Moved settlement onto FastAPI and PostgreSQL.",
                "technologies": ["Python", "FastAPI", "PostgreSQL", "Kafka"],
            },
            {
                "name": "Dual-read migration shim",
                "description": "Expand-and-contract migration with no downtime.",
                "technologies": ["PostgreSQL", "SQLAlchemy"],
            },
        ],
    },
    {
        "company": "Logistics Co",
        "role": "Backend Engineer",
        "employment_type": "full_time",
        "location": "São Paulo, SP",
        "started_on": date(2020, 3, 1),
        "ended_on": date(2023, 1, 31),
        "is_current": False,
        "summary": "Owned the routing service at roughly 4k requests per minute.",
        "responsibilities": [
            "Maintain and scale the routing service.",
            "Replace the polling design with event consumers.",
        ],
        "technologies": ["Python", "Celery", "Redis", "PostgreSQL", "Docker"],
        "results": ["Infrastructure spend down 30% after the Kafka migration."],
        "projects": [
            {
                "name": "Routing service",
                "description": "Owned the service at roughly 4k requests/minute.",
                "technologies": ["Python", "Celery", "Redis"],
            },
            {
                "name": "Integration test harness",
                "description": "The harness the team still uses for coverage.",
                "technologies": ["pytest", "Docker"],
            },
        ],
    },
    {
        "company": "Digital Agency",
        "role": "Software Engineer",
        "employment_type": "full_time",
        "location": "São Paulo, SP",
        "started_on": date(2018, 6, 1),
        "ended_on": date(2020, 2, 28),
        "is_current": False,
        "summary": "Django and PostgreSQL across a dozen client projects.",
        "responsibilities": ["Build and ship client web applications."],
        "technologies": ["Python", "Django", "PostgreSQL", "JavaScript"],
        "results": [],
        "projects": [],
    },
]

ANSWER_BANK = {
    "Years of Python experience": "8",
    "Are you authorized to work in this country?": "Yes",
    "Do you require visa sponsorship?": "No",
    "Notice period (days)": "30",
    "Expected salary (BRL, monthly)": "22000",
    "Level of English": "Advanced",
}


def screening_answers(*, flagged: bool) -> list[dict[str, Any]]:
    """A drafted answer set. `flagged` leaves one for the human to finish."""
    answers = [
        {
            "question": "Years of Python experience?",
            "answer": "8",
            "question_type": "number",
            "confidence": "high",
            "needs_review": False,
            "reasoning": "Taken from the answer bank.",
            "source": "answer_bank",
            "field_id": "numeric-form-component-years",
        },
        {
            "question": "Are you authorized to work in this country?",
            "answer": "Yes",
            "question_type": "radio",
            "confidence": "high",
            "needs_review": False,
            "reasoning": "Taken from the answer bank.",
            "source": "answer_bank",
            "field_id": "radio-form-component-auth",
        },
        {
            "question": "Level of English",
            "answer": "Advanced",
            "question_type": "select",
            "confidence": "high",
            "needs_review": False,
            "reasoning": "Profile states fluent English.",
            "source": "ai",
            "field_id": "select-form-component-english",
        },
    ]
    if flagged:
        answers.append(
            {
                "question": "Describe a production incident you owned end to end.",
                "answer": "",
                "question_type": "textarea",
                "confidence": "low",
                "needs_review": True,
                "reasoning": (
                    "The profile has no incident write-up to ground this; "
                    "answer it yourself."
                ),
                "source": "ai",
                "field_id": "textarea-form-component-incident",
            }
        )
    return answers


def breakdown(overall: int) -> list[dict[str, Any]]:
    """Per-dimension scores whose weights sum to exactly 100."""
    weights = [30, 25, 20, 10, 8, 7]
    rows = []
    for name, weight, offset in zip(DIMENSIONS, weights, (7, 2, -3, -12, 5, 4), strict=True):
        rows.append(
            {
                "dimension": name,
                "score": max(0, min(100, overall + offset)),
                "weight": "hard" if weight >= 20 else "nice_to_have",
                "weight_pct": weight,
                "evidence": f"Assessed {name} against the posting's stated requirements.",
            }
        )
    return rows


def gates(*, language_flag: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "gate": "eligibility",
            "status": "pass",
            "evidence": "The posting states no citizenship or visa restriction.",
        },
        {
            "gate": "language",
            "status": "flag" if language_flag else "pass",
            "evidence": (
                "The posting is written in English and asks for fluency; the profile "
                "states fluent English but has no certification."
                if language_flag
                else "Posting language matches the profile's stated languages."
            ),
        },
    ]


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #


async def wipe(session: Any, user_id: int) -> None:
    """Remove this user's rows, newest tables first, so re-seeding is clean."""
    from sqlalchemy import delete, select

    from app.models import (
        AIAnalysis,
        Application,
        ApplicationEvent,
        AutomationRun,
        InterviewStage,
        Job,
        JobScore,
        Search,
        TailoredResume,
    )

    # Only present on branches that carry the per-application resume feature, so
    # the seeder keeps working on one that does not.
    optional: list[Any] = []
    try:
        from app.models import ApplicationResume, Experience

        optional = [ApplicationResume, Experience]
    except ImportError:
        pass

    app_ids = (
        (await session.execute(select(Application.id).where(Application.user_id == user_id)))
        .scalars()
        .all()
    )
    if app_ids:
        await session.execute(
            delete(ApplicationEvent).where(ApplicationEvent.application_id.in_(app_ids))
        )
    for model in (
        *optional,
        InterviewStage,
        Application,
        JobScore,
        TailoredResume,
        AIAnalysis,
        Job,
        AutomationRun,
        Search,
    ):
        column = getattr(model, "user_id", None)
        if column is not None:
            await session.execute(delete(model).where(column == user_id))
    await session.flush()


async def seed(email: str, password: str, *, fresh: bool) -> None:
    from sqlalchemy import select

    from app.auth.security import hash_password
    from app.database.session import dispose_engine, init_models, session_scope
    from app.models import (
        AIAnalysis,
        Application,
        ApplicationEvent,
        AutomationRun,
        InterviewStage,
        Job,
        JobScore,
        Profile,
        Search,
        TailoredResume,
        User,
        UserSettings,
    )
    from app.models.enums import (
        AnalysisKind,
        ApplicationChannel,
        ApplicationEventType,
        ApplicationOutcome,
        ApplicationStatus,
        AutomationRunKind,
        AutomationRunStatus,
        JobStatus,
    )

    await init_models()

    async with session_scope() as session:
        normalized = email.strip().lower()
        user = (
            await session.execute(select(User).where(User.email == normalized))
        ).scalar_one_or_none()

        if user is None:
            # Straight to the table: see the module docstring for why this does
            # not go through register_user.
            user = User(
                email=normalized,
                hashed_password=hash_password(password),
                full_name="Alex Moreira",
                is_active=True,
                is_admin=True,
            )
            session.add(user)
            await session.flush()
            created = True
        else:
            user.hashed_password = hash_password(password)
            user.is_admin = True
            created = False
        await session.flush()

        if fresh:
            await wipe(session, user.id)

        # --- settings and profile -----------------------------------------
        settings_row = (
            await session.execute(select(UserSettings).where(UserSettings.user_id == user.id))
        ).scalar_one_or_none()
        if settings_row is None:
            settings_row = UserSettings(user_id=user.id)
            session.add(settings_row)
        settings_row.dry_run = False
        settings_row.min_score = 0
        settings_row.daily_cap = 25
        settings_row.action_delay_min = 0.0
        settings_row.action_delay_max = 0.0
        settings_row.apply_delay_min = 0.0
        settings_row.apply_delay_max = 0.0
        settings_row.working_hour_start = 0
        settings_row.working_hour_end = 0
        # Never relaxed: the approval gate is the product.
        settings_row.require_manual_approval = True

        profile = (
            await session.execute(select(Profile).where(Profile.user_id == user.id))
        ).scalar_one_or_none()
        if profile is None:
            profile = Profile(user_id=user.id)
            session.add(profile)
        profile.headline = "Senior Backend Engineer — Python, FastAPI, PostgreSQL"
        profile.location = "São Paulo, Brazil"
        profile.phone = "+55 11 90000-0000"
        profile.years_of_experience = 8
        profile.summary = (
            "Backend engineer with eight years on Python services in production. "
            "Owns systems end to end: design, rollout, on-call."
        )
        profile.resume_text = RESUME_TEXT
        profile.resume_filename = "alex-moreira-cv.pdf"
        profile.skills = SKILLS
        profile.preferred_languages = ["pt-BR", "en"]
        profile.answer_bank = ANSWER_BANK
        await session.flush()

        # --- structured experience (present only on branches that have it) --
        try:
            from app.models import Experience
        except ImportError:
            Experience = None  # noqa: N806
        if Experience is not None:
            for position, item in enumerate(EXPERIENCES):
                session.add(Experience(user_id=user.id, position=position, **item))
            await session.flush()

        # --- searches -------------------------------------------------------
        searches = [
            Search(
                user_id=user.id,
                name="Backend sênior remoto",
                keywords="senior backend engineer python",
                location="Brazil",
                remote_filter="remote",
                experience_levels=["mid_senior", "senior"],
                date_posted="week",
                easy_apply_only=True,
                max_results=25,
                is_active=True,
                last_run_at=ago(hours=3),
            ),
            Search(
                user_id=user.id,
                name="Plataforma / SRE",
                keywords="platform engineer site reliability python",
                location="São Paulo",
                remote_filter="hybrid",
                experience_levels=["senior"],
                date_posted="month",
                easy_apply_only=True,
                max_results=15,
                is_active=True,
                last_run_at=ago(days=2),
            ),
            Search(
                user_id=user.id,
                name="Tech lead (pausada)",
                keywords="tech lead backend",
                location="Brazil",
                remote_filter=None,
                experience_levels=["director"],
                date_posted=None,
                easy_apply_only=False,
                max_results=10,
                is_active=False,
                last_run_at=ago(days=21),
            ),
        ]
        session.add_all(searches)
        await session.flush()

        # --- automation runs -------------------------------------------------
        session.add_all(
            [
                AutomationRun(
                    user_id=user.id,
                    search_id=searches[0].id,
                    kind=AutomationRunKind.SEARCH,
                    status=AutomationRunStatus.COMPLETED,
                    dry_run=False,
                    jobs_found=18,
                    jobs_analyzed=18,
                    jobs_skipped=4,
                    started_at=ago(hours=3),
                    finished_at=ago(hours=2.8),
                ),
                AutomationRun(
                    user_id=user.id,
                    search_id=None,
                    kind=AutomationRunKind.PREPARE,
                    status=AutomationRunStatus.COMPLETED,
                    dry_run=False,
                    applications_prepared=6,
                    started_at=ago(hours=2),
                    finished_at=ago(hours=1.5),
                ),
                AutomationRun(
                    user_id=user.id,
                    search_id=searches[1].id,
                    kind=AutomationRunKind.SEARCH,
                    status=AutomationRunStatus.BLOCKED,
                    dry_run=False,
                    jobs_found=5,
                    jobs_analyzed=2,
                    blocked_reason="LinkedIn redirected to a security checkpoint (/checkpoint/).",
                    started_at=ago(days=2),
                    finished_at=ago(days=2),
                ),
            ]
        )
        await session.flush()

        # --- jobs -------------------------------------------------------------
        # Scores are spread deliberately across the bands the dashboard charts,
        # and statuses cover every value JobStatus can hold.
        plan: list[tuple[int | None, str, str | None]] = [
            (94, JobStatus.APPLIED, None),
            (91, JobStatus.APPLIED, None),
            (88, JobStatus.APPLIED, None),
            (86, JobStatus.QUEUED, None),
            (83, JobStatus.QUEUED, None),
            (81, JobStatus.QUEUED, None),
            (78, JobStatus.ANALYZED, None),
            (74, JobStatus.ANALYZED, None),
            (71, JobStatus.ANALYZED, None),
            (68, JobStatus.ANALYZED, None),
            (64, JobStatus.ANALYZED, None),
            (58, JobStatus.ANALYZED, None),
            (46, JobStatus.SKIPPED, "Below the minimum score for this account."),
            (
                39,
                JobStatus.SKIPPED,
                "The posting requires Go, which the profile does not evidence.",
            ),
            (27, JobStatus.SKIPPED, "Requires on-site work in another state."),
            (None, JobStatus.DISCOVERED, None),
            (None, JobStatus.DISCOVERED, None),
            (None, JobStatus.FAILED, "The job page did not load after three attempts."),
        ]

        jobs: list[Job] = []
        for index, (score, status, skip) in enumerate(plan):
            company, location = COMPANIES[index % len(COMPANIES)]
            title = TITLES[index % len(TITLES)]
            workplace = ("remote", "hybrid", "onsite")[index % 3]
            external_id = str(4020000000 + index)
            # Every seventh posting comes from another portal, which is what the
            # external channel exists for. Source, URL and easy_apply have to
            # agree, or the card reads "Gupy / external form / linkedin.com".
            from_linkedin = index % 7 != 0
            job = Job(
                user_id=user.id,
                search_id=searches[index % 2].id,
                external_id=external_id,
                source="linkedin" if from_linkedin else "gupy",
                title=title,
                company=company,
                location="Remote" if workplace == "remote" else location,
                url=(
                    f"https://www.linkedin.com/jobs/view/{external_id}/"
                    if from_linkedin
                    else f"https://{company.split()[0].lower()}.gupy.io/jobs/{external_id}"
                ),
                description=DESCRIPTION,
                workplace_type=workplace,
                easy_apply=from_linkedin,
                detected_language="en" if index % 3 else "pt-BR",
                posted_at=ago(days=index * 0.7 + 0.3),
                deadline=ahead(14 - index) if index % 5 == 0 else None,
                expired_at=ago(days=1) if index == 17 else None,
                status=status,
                score=score,
                score_reasons=RNG.sample(REASONS, 3) if score else [],
                missing_requirements=RNG.sample(GAPS, 2) if score else [],
                score_breakdown=breakdown(score) if score else [],
                score_gates=gates(language_flag=score is not None and score < 60) if score else [],
                skip_reason=skip,
            )
            jobs.append(job)
            session.add(job)
        await session.flush()

        # --- score history + AI audit rows -------------------------------------
        for job in jobs:
            if job.score is None:
                continue
            session.add(
                AIAnalysis(
                    user_id=user.id,
                    job_id=job.id,
                    kind=AnalysisKind.SCORING,
                    model="stub-offline",
                    result={"score": job.score, "recommend_apply": job.score >= 70},
                    input_tokens=1180 + job.id,
                    output_tokens=260 + job.id,
                    latency_ms=900 + job.id * 7,
                    was_refusal=False,
                    cost_usd=0.0,
                )
            )
            # Two versions for a few jobs, so the history panel has something to
            # compare: an earlier, lower read of the same posting.
            versions = (
                [(job.score - 6, ago(days=6)), (job.score, ago(hours=3))]
                if job.id % 4 == 0
                else [(job.score, ago(hours=3))]
            )
            for overall, when in versions:
                overall = max(0, min(100, overall))
                row = JobScore(
                    job_id=job.id,
                    user_id=user.id,
                    overall=overall,
                    verdict="recommend" if overall >= 70 else "skip",
                    dimensions=breakdown(overall),
                    gates=gates(),
                    model="stub-offline",
                    depth="low",
                    profile_fingerprint="seed-fingerprint",
                )
                row.created_at = when
                session.add(row)
        await session.flush()

        # --- tailored resumes ---------------------------------------------------
        for job in jobs[:4]:
            session.add(
                TailoredResume(
                    user_id=user.id,
                    job_id=job.id,
                    content=RESUME_TEXT.replace(
                        "## Summary",
                        f"## Summary (adapted for {job.company})",
                    ),
                    changes=[
                        {
                            "section": "Summary",
                            "action": "reordered",
                            "detail": "Led with the settlement work the posting's stack matches.",
                        },
                        {
                            "section": "Skills",
                            "action": "emphasized",
                            "detail": "Moved Kafka and Terraform ahead of the frontend skills.",
                        },
                    ],
                    unsupported_requirements=["Kubernetes in production"],
                    invention_flags=[],
                    stretch_flags=[
                        {
                            "text": "Owns systems end to end, including on-call.",
                            "why_stretch": "On-call was shared with two other engineers.",
                        },
                    ],
                    summary="Reordered and re-emphasized; nothing added.",
                    model="stub-offline",
                    source_fingerprint="seed-fingerprint",
                    was_edited=job.id % 2 == 0,
                )
            )
        await session.flush()

        # --- applications --------------------------------------------------------
        # (job index, status, outcome, channel, flagged, days ago)
        app_plan: list[tuple[int, str, str | None, str, bool, float]] = [
            (
                0,
                ApplicationStatus.SUBMITTED,
                ApplicationOutcome.OFFER,
                ApplicationChannel.EASY_APPLY,
                False,
                24,
            ),
            (
                1,
                ApplicationStatus.SUBMITTED,
                ApplicationOutcome.INTERVIEW,
                ApplicationChannel.EASY_APPLY,
                False,
                17,
            ),
            (
                2,
                ApplicationStatus.SUBMITTED,
                ApplicationOutcome.INTERVIEW,
                ApplicationChannel.EXTERNAL,
                False,
                12,
            ),
            (
                3,
                ApplicationStatus.SUBMITTED,
                ApplicationOutcome.REJECTED,
                ApplicationChannel.EASY_APPLY,
                False,
                9,
            ),
            (
                4,
                ApplicationStatus.SUBMITTED,
                ApplicationOutcome.GHOSTED,
                ApplicationChannel.EASY_APPLY,
                False,
                31,
            ),
            (
                5,
                ApplicationStatus.SUBMITTED,
                ApplicationOutcome.APPLIED,
                ApplicationChannel.EASY_APPLY,
                False,
                2,
            ),
            (6, ApplicationStatus.AWAITING_REVIEW, None, ApplicationChannel.EASY_APPLY, False, 0.1),
            (7, ApplicationStatus.AWAITING_REVIEW, None, ApplicationChannel.EASY_APPLY, True, 0.15),
            (8, ApplicationStatus.AWAITING_REVIEW, None, ApplicationChannel.EASY_APPLY, False, 0.2),
            (9, ApplicationStatus.AWAITING_REVIEW, None, ApplicationChannel.EASY_APPLY, True, 0.3),
            (10, ApplicationStatus.DRAFT, None, ApplicationChannel.EASY_APPLY, False, 0.4),
            (11, ApplicationStatus.DISCARDED, None, ApplicationChannel.EASY_APPLY, False, 5),
            (12, ApplicationStatus.FAILED, None, ApplicationChannel.EASY_APPLY, False, 4),
        ]

        for job_index, status, outcome, _channel, flagged, days in app_plan:
            job = jobs[job_index]
            submitted = status == ApplicationStatus.SUBMITTED
            # Derived, not taken from the plan: a posting without Easy Apply can
            # only ever have been applied to through the external channel, and a
            # row saying otherwise would contradict the card next to it.
            channel = (
                ApplicationChannel.EASY_APPLY
                if job.easy_apply
                else ApplicationChannel.EXTERNAL
            )
            application = Application(
                user_id=user.id,
                job_id=job.id,
                status=status,
                channel=channel,
                cover_letter=cover_letter(job.company, job.title),
                screening_answers=screening_answers(flagged=flagged),
                resume_filename="alex-moreira-cv.pdf",
                total_steps=4,
                current_step=4,
                form_fingerprint=f"seed-form-{job.id}",
                needs_human_input=flagged,
                was_dry_run=False,
                approved_at=ago(days=days) if submitted else None,
                submitted_at=ago(days=days) if submitted else None,
                error_message=(
                    "The Easy Apply modal closed before the review step could be reached."
                    if status == ApplicationStatus.FAILED
                    else None
                ),
                outcome=outcome,
                outcome_updated_at=ago(days=days / 2) if outcome else None,
                outcome_note=(
                    "Two rounds done; waiting on the take-home result."
                    if outcome == ApplicationOutcome.INTERVIEW
                    else None
                ),
                submitted_snapshot=(
                    {
                        "cover_letter": cover_letter(job.company, job.title),
                        "answers": screening_answers(flagged=False),
                    }
                    if submitted
                    else None
                ),
            )
            session.add(application)
            await session.flush()

            timeline = [
                (ApplicationEventType.JOB_FOUND, "Found by the saved search.", days + 0.4),
                (ApplicationEventType.SCORE_ASSIGNED, f"Scored {job.score}/100.", days + 0.35),
                (ApplicationEventType.COVER_LETTER_GENERATED, "Cover letter drafted.", days + 0.3),
                (
                    ApplicationEventType.FORM_OPENED,
                    "Easy Apply form opened with 4 field(s).",
                    days + 0.25,
                ),
                (
                    ApplicationEventType.AWAITING_REVIEW,
                    "Form filled and closed. Nothing is typed into the site until you approve.",
                    days + 0.2,
                ),
            ]
            if submitted:
                timeline += [
                    (
                        ApplicationEventType.USER_APPROVED,
                        "You approved this application.",
                        days + 0.05,
                    ),
                    (ApplicationEventType.SUBMITTED, "Application sent.", days),
                ]
                if outcome and outcome != ApplicationOutcome.APPLIED:
                    timeline.append(
                        (
                            ApplicationEventType.OUTCOME_CHANGED,
                            f"Outcome set to {outcome}.",
                            days / 2,
                        )
                    )
            if status == ApplicationStatus.DISCARDED:
                timeline.append((ApplicationEventType.DISCARDED, "Draft discarded.", days))
            if status == ApplicationStatus.FAILED:
                timeline.append(
                    (
                        ApplicationEventType.ERROR,
                        "The Easy Apply modal closed before the review step.",
                        days,
                    )
                )

            for event_type, message, when in timeline:
                event = ApplicationEvent(
                    application_id=application.id,
                    event_type=event_type,
                    message=message,
                    payload={},
                    is_error=event_type == ApplicationEventType.ERROR,
                )
                event.created_at = ago(days=when)
                session.add(event)

            if outcome in (ApplicationOutcome.INTERVIEW, ApplicationOutcome.OFFER):
                session.add(
                    InterviewStage(
                        user_id=user.id,
                        application_id=application.id,
                        stage_type="screening",
                        scheduled_at=ago(days=days / 1.5),
                        completed_at=ago(days=days / 1.6),
                        note="30 minutes with the recruiter. Comp range confirmed.",
                    )
                )
                session.add(
                    InterviewStage(
                        user_id=user.id,
                        application_id=application.id,
                        stage_type="technical",
                        scheduled_at=ago(days=days / 3),
                        completed_at=ago(days=days / 3.2)
                        if outcome == ApplicationOutcome.OFFER
                        else None,
                        note="System design: a settlement pipeline under partial failure.",
                    )
                )
            if outcome == ApplicationOutcome.OFFER:
                session.add(
                    InterviewStage(
                        user_id=user.id,
                        application_id=application.id,
                        stage_type="offer",
                        scheduled_at=ago(days=1),
                        completed_at=None,
                        note="Offer received; deciding.",
                    )
                )

        await session.flush()

        print("=" * 68)
        print("  Mock data seeded. Nothing here is real and nothing was sent.")
        print("=" * 68)
        print(f"  Sign in   {normalized} / {password}")
        print(f"  Account   {'created' if created else 'password reset'}, id={user.id}, admin=True")
        print(
            f"  Data      {len(jobs)} jobs, {len(app_plan)} applications, {len(searches)} searches"
        )
        print("=" * 68)

    await dispose_engine()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="seed_mock.py", description="Fill the database with believable demo data."
    )
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument(
        "--data-dir",
        default=str(PROJECT_ROOT / "backend" / "data" / "demo"),
        help="Must match the running server's DATA_DIR (default: the demo one).",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete this account's existing jobs and applications first.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_dir = Path(args.data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Set before anything reads settings: get_settings is cached on first call.
    os.environ.setdefault("SECRET_KEY", "demo-secret-key-not-for-production-use")
    os.environ.setdefault("ENCRYPTION_KEY", "demo-encryption-key-not-for-production-use")
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(data_dir / 'demo.db').as_posix()}"

    from app.config import get_settings

    get_settings.cache_clear()

    asyncio.run(seed(args.email, args.password, fresh=args.fresh))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
