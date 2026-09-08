#!/usr/bin/env python3
"""Seed the per-application resume demo: one candidate, five vacancies, five resumes.

    python scripts/seed_demo.py --email demo@example.com --password troque-esta-senha

Creates (or reuses) an account, writes the demo master resume onto it — the
unstructured half through `ProfileUpdate`, the structured history through
`resume_service.create_experience` — then creates the five demo postings, opens
an application for each and adapts that application's own copy of the resume.
Finally prints, per vacancy, the fit score, which experience leads and which
technologies were emphasised, so the whole claim is verifiable from a terminal
before anyone opens the UI.

Idempotent: run it twice and you get the same five applications with freshly
adapted copies, not ten, and the experience list is rebuilt rather than
duplicated. Nothing is submitted anywhere; no browser is opened.

`--applications N` goes past the five demo postings by cycling their
descriptions with fresh ids, which is how "this is not limited to five" gets
demonstrated rather than asserted.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database.session import dispose_engine, init_models, session_scope  # noqa: E402
from app.demo import (  # noqa: E402
    DEMO_EMAIL,
    DEMO_FULL_NAME,
    DEMO_JOBS,
    demo_experiences,
    demo_profile_fields,
)
from app.models import Application, ApplicationStatus, Job, User  # noqa: E402
from app.models.resume import Experience  # noqa: E402
from app.observability import configure_logging  # noqa: E402
from app.schemas.auth import RegisterRequest  # noqa: E402
from app.schemas.resume import ExperienceCreate  # noqa: E402
from app.schemas.user import ProfileUpdate  # noqa: E402
from app.services import resume_service, user_service  # noqa: E402

DEFAULT_PASSWORD = "demo-curriculos-2026"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="seed_demo.py",
        description="Seed the per-application resume demonstration.",
    )
    parser.add_argument("--email", default=DEMO_EMAIL, help="Account e-mail.")
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help="Password used only when the account has to be created.",
    )
    parser.add_argument(
        "--applications",
        type=int,
        default=len(DEMO_JOBS),
        help=f"How many applications to seed (default {len(DEMO_JOBS)}).",
    )
    return parser.parse_args(argv)


async def _account(session: AsyncSession, email: str, password: str) -> User:
    """The demo account, created on first run and reused afterwards."""
    existing = await user_service.get_by_email(session, email)
    if existing is not None:
        return existing
    # Validated through the same request schema the sign-up endpoint uses, so a
    # seeded account cannot be one the API would have refused to create.
    payload = RegisterRequest(email=email, password=password, full_name=DEMO_FULL_NAME)
    return await user_service.register_user(
        session,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )


async def _seed_master_resume(session: AsyncSession, user: User) -> int:
    """Write the demo master resume, replacing any history a previous run left.

    Rebuilt rather than merged: matching seeded rows against existing ones by
    company and role would silently keep a stale bullet the demo has since
    reworded, and this is a demo seeder, not a migration. Applications that
    already hold an adapted copy are untouched by this — that is the isolation
    the feature is for, and re-running the seeder exercises it.
    """
    await user_service.update_profile(session, user, ProfileUpdate(**demo_profile_fields()))

    for row in (
        (await session.execute(select(Experience).where(Experience.user_id == user.id)))
        .scalars()
        .all()
    ):
        await session.delete(row)
    await session.flush()

    for entry in demo_experiences():
        await resume_service.create_experience(session, user, ExperienceCreate(**entry))
    return len(demo_experiences())


async def _seed_application(session: AsyncSession, user: User, index: int) -> tuple[str, int]:
    """One posting, one application, one adapted copy. Returns (title, id)."""
    template = dict(DEMO_JOBS[index % len(DEMO_JOBS)])
    external_id = f"{template.pop('external_id')}-{index + 1}"

    job = await session.scalar(
        select(Job).where(Job.user_id == user.id, Job.external_id == external_id)
    )
    if job is None:
        job = Job(
            user_id=user.id,
            external_id=external_id,
            source="demo",
            easy_apply=False,
            detected_language="pt-BR",
            **template,
        )
        session.add(job)
        await session.flush()

    application = await session.scalar(
        select(Application).where(Application.job_id == job.id)
    )
    if application is None:
        application = Application(
            user_id=user.id,
            job_id=job.id,
            status=ApplicationStatus.AWAITING_REVIEW,
            screening_answers=[],
        )
        session.add(application)
        await session.flush()

    await resume_service.adapt_application_resume(session, user, application.id)
    return job.title, application.id


async def seed(email: str, password: str, wanted: int) -> None:
    # Safe on an existing database: only creates tables that are missing. A
    # deployment that uses Alembic should have run `make migrate` first.
    await init_models()

    try:
        async with session_scope() as session:
            user = await _account(session, email, password)
            if not user.full_name:
                user.full_name = DEMO_FULL_NAME

            positions = await _seed_master_resume(session, user)
            seeded = [await _seed_application(session, user, index) for index in range(wanted)]

            await session.commit()
            await _report(session, user, positions, seeded)
    finally:
        await dispose_engine()


async def _report(
    session: AsyncSession, user: User, positions: int, seeded: list[tuple[str, int]]
) -> None:
    """Print what each copy emphasises — the demonstration, in text."""
    fields = demo_profile_fields()
    print(f"\nConta: {user.email} (id={user.id})")
    print(
        f"Currículo principal: {positions} experiências, "
        f"{len(fields['skills'])} competências\n"
    )
    print(f"{len(seeded)} candidatura(s), cada uma com a sua própria versão:\n")

    for title, application_id in seeded:
        row = await resume_service.get_application_resume(session, user, application_id)
        if row is None:
            continue
        experiences = row.experiences or []
        lead = experiences[0] if experiences else {}
        print(f"  #{application_id}  {title}")
        print(f"      aderência : {row.fit_score}%  (v{row.version})")
        print(f"      enfatiza  : {', '.join((row.emphasized_technologies or [])[:8])}")
        print(f"      destaca   : {', '.join((row.highlighted_skills or [])[:8])}")
        print(
            f"      lidera    : {lead.get('role', '?')} — {lead.get('company', '?')} "
            f"({lead.get('relevance', 0)}%)"
        )
        uncovered = row.uncovered_requirements or []
        print(f"      lacunas   : {', '.join(uncovered) if uncovered else '—'}")
        print()

    print("Abra /applications no app e veja “Currículo desta candidatura” em cada uma.")


def main(argv: list[str] | None = None) -> int:
    configure_logging(level="WARNING")
    args = parse_args(argv)
    if args.applications < 1:
        raise SystemExit("--applications must be at least 1.")

    try:
        asyncio.run(seed(args.email.strip(), args.password, args.applications))
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, do not traceback
        print(f"Could not seed the demo: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
