#!/usr/bin/env python3
"""Seed the per-application resume demo: one candidate, five vacancies, five resumes.

    python scripts/seed_demo.py --email demo@exemplo.test --password troque-esta-senha

Creates (or reuses) an account, writes the rich master resume from `app.demo`
onto its profile, creates the five demo postings, opens an application for each
and derives that application's own version of the resume. Then prints, per
vacancy, which experience leads and which skills were promoted — so the whole
claim is verifiable from a terminal before anyone opens the UI.

Idempotent: run it twice and you get the same five applications with freshly
derived versions, not ten. Nothing is submitted anywhere; no browser is opened.

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

from app.database.session import dispose_engine, init_models, session_scope  # noqa: E402
from app.demo import DEMO_EMAIL, DEMO_FULL_NAME, DEMO_JOBS, demo_profile_fields  # noqa: E402
from app.models import Application, ApplicationStatus, Job, User  # noqa: E402
from app.observability import configure_logging  # noqa: E402
from app.schemas.auth import RegisterRequest  # noqa: E402
from app.schemas.user import ProfileUpdate  # noqa: E402
from app.services import tailoring_service, user_service  # noqa: E402

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


async def _account(session: object, email: str, password: str) -> User:
    """The demo account, created on first run and reused afterwards."""
    existing = await user_service.get_by_email(session, email)  # type: ignore[arg-type]
    if existing is not None:
        return existing
    # Validated through the same request schema the sign-up endpoint uses, so a
    # seeded account cannot be one the API would have refused to create.
    payload = RegisterRequest(email=email, password=password, full_name=DEMO_FULL_NAME)
    return await user_service.register_user(  # type: ignore[arg-type]
        session,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )


async def seed(email: str, password: str, wanted: int) -> None:
    # Safe on an existing database: only creates tables that are missing. A
    # deployment that uses Alembic should have run `make migrate` first.
    await init_models()

    try:
        async with session_scope() as session:
            user = await _account(session, email, password)
            if not user.full_name:
                user.full_name = DEMO_FULL_NAME

            # The master resume. Written through the same schema the API uses, so
            # the seeded document is exactly what a user could have typed.
            await user_service.update_profile(
                session, user, ProfileUpdate(**demo_profile_fields())
            )

            seeded: list[tuple[str, int]] = []
            for index in range(wanted):
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

                await tailoring_service.derive_for_application(session, user, application.id)
                seeded.append((job.title, application.id))

            await session.commit()
            await _report(session, user, seeded)
    finally:
        await dispose_engine()


async def _report(session: object, user: User, seeded: list[tuple[str, int]]) -> None:
    """Print what each version emphasises — the demonstration, in text."""
    print(f"\nConta: {user.email} (id={user.id})")
    print(f"Currículo principal: {len(demo_profile_fields()['experiences'])} experiências, "
          f"{len(demo_profile_fields()['skills'])} competências\n")
    print(f"{len(seeded)} candidatura(s), cada uma com a sua própria versão:\n")

    for title, application_id in seeded:
        _application, row = await tailoring_service.get_for_application(
            session, user, application_id  # type: ignore[arg-type]
        )
        if row is None:
            continue
        sections = row.sections or {}
        focus = row.focus or {}
        experiences = sections.get("experiences") or []
        lead = experiences[0] if experiences else {}
        print(f"  #{application_id}  {title}")
        print(f"      pede      : {', '.join((focus.get('keywords') or [])[:8])}")
        print(f"      prioriza  : {', '.join((sections.get('prioritized_skills') or [])[:8])}")
        print(f"      lidera    : {lead.get('role', '?')} — {lead.get('company', '?')} "
              f"({lead.get('relevance', 0)}%)")
        gaps = row.unsupported_requirements or []
        print(f"      lacunas   : {', '.join(gaps) if gaps else '—'}")
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
