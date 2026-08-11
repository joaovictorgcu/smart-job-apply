"""Factories for ORM rows and automation contract objects.

Delays default to zero on every created `UserSettings` so no test ever waits on a
production-shaped humanization delay, and `dry_run` defaults to True to mirror the
application's own default.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta
from typing import Any

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
