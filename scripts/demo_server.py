#!/usr/bin/env python3
"""Boot the whole application with nothing configured.

One command, no API key, no LinkedIn account, no manual setup:

    python scripts/demo_server.py

It creates a throwaway database, applies the schema, seeds one account, and
serves the API with the offline AI provider and the bundled fake job portal. The
dashboard then works end to end — search, score, draft, review, approve, submit —
and nothing leaves the machine.

This is also what `frontend/playwright.config.ts` launches for the browser
tests, so the flow the tests exercise is the flow a person clicking through the
demo sees.

Two guard rails are not negotiable here:

* `ASSISTED_MODE_ONLY` stays on. The demo is a demo of the real product, and the
  real product never submits without an explicit approval.
* `DEMO_PORTAL` is on, so the automation drives a page served from this process.
  A demo must not be one env var away from applying to real jobs.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_EMAIL = "demo@example.com"
# Long enough for the account rules, and obviously not a secret.
DEFAULT_PASSWORD = "demo-password-123"
DEFAULT_PORT = 8000

# Fixed so a restart does not invalidate the token the browser already holds.
DEMO_SECRET_KEY = "demo-secret-key-not-for-production-use"
DEMO_ENCRYPTION_KEY = "demo-encryption-key-not-for-production-use"


def demo_environment(data_dir: Path, *, port: int) -> dict[str, str]:
    """The settings that make the app self-contained."""
    return {
        "ENVIRONMENT": "development",
        "SECRET_KEY": DEMO_SECRET_KEY,
        "ENCRYPTION_KEY": DEMO_ENCRYPTION_KEY,
        "DATA_DIR": str(data_dir),
        "DATABASE_URL": f"sqlite+aiosqlite:///{(data_dir / 'demo.db').as_posix()}",
        # No key, no quota, no network: the offline provider answers everything.
        "AI_PROVIDER": "stub",
        # The automation drives the bundled fake site, not LinkedIn.
        "DEMO_PORTAL": "true",
        "HEADLESS": "true",
        # A demo should not sit through the anti-detection pacing.
        "DEFAULT_ACTION_DELAY_RANGE": "0,0",
        "DEFAULT_APPLY_DELAY_RANGE": "0,0",
        "DEFAULT_WORKING_HOURS": "0,0",
        "DEFAULT_MIN_SCORE": "0",
        "DEFAULT_DAILY_CAP": "25",
        # Never relaxed, not even here.
        "ASSISTED_MODE_ONLY": "true",
        "CORS_ORIGINS": (
            f"http://localhost:5173,http://127.0.0.1:5173,http://localhost:{port}"
        ),
        # The demo clicks through screens quickly; the default limit is for a
        # deployment facing the internet, not for a test run.
        "RATE_LIMIT_DEFAULT": "1000/minute",
        "RATE_LIMIT_AUTH": "100/minute",
    }


async def seed(email: str, password: str) -> int | None:
    """Apply the schema, create the demo account, and open the demo guard rails.

    Idempotent: re-running against an existing data directory keeps the account
    it already has, so `--fresh` is the only thing that resets state.

    Dry run is turned off, which is the one place this script relaxes a default.
    With it on, preparing an application generates text without ever opening a
    form, so the demo would never exercise the part that matters — and turning
    it off is only safe here because `DEMO_PORTAL` means the form being filled
    is served from this process. `require_manual_approval` stays on: the whole
    point of the demo is to show the approval gate working.
    """
    from app.api.errors import ConflictError
    from app.database.session import dispose_engine, init_models, session_scope
    from app.services.user_service import register_user

    await init_models()
    try:
        async with session_scope() as session:
            try:
                user = await register_user(
                    session, email=email, password=password, full_name="Demo Candidate"
                )
                user_id: int | None = getattr(user, "id", None)
            except ConflictError:
                user_id = None
            await _seed_demo_resume(session, email)
            await _open_demo_guardrails(session, email)
            return user_id
    finally:
        await dispose_engine()


async def _seed_demo_resume(session: object, email: str) -> None:
    """Give the demo account the master resume the product is built around.

    Without one the dashboard is right to show "Comece pelo seu currículo" and
    nothing else: every screen downstream — scoring, the adapted resume, the
    screening answers — is derived from it. A demo that opens on an upload
    prompt demonstrates the empty state, not the product.

    Reuses `app.demo`, the same fixture `scripts/seed_demo.py` and the test
    suite read, so what a demo shows and what the tests assert cannot drift.

    Only fills an empty profile. Re-running the demo server must not overwrite
    a resume somebody edited while trying the app out.
    """
    from sqlalchemy import select

    from app.demo import demo_experiences, demo_profile_fields
    from app.models import Experience, User
    from app.schemas.resume import ExperienceCreate
    from app.schemas.user import ProfileUpdate
    from app.services import resume_service, user_service

    found = await session.execute(  # type: ignore[attr-defined]
        select(User).where(User.email == email.strip().lower())
    )
    user = found.scalar_one_or_none()
    if user is None:
        return

    profile = await user_service.get_or_create_profile(session, user)  # type: ignore[arg-type]
    already = (
        await session.execute(  # type: ignore[attr-defined]
            select(Experience).where(Experience.user_id == user.id)
        )
    ).scalars().first()
    if already is not None or (profile.resume_text or "").strip():
        return

    await user_service.update_profile(  # type: ignore[arg-type]
        session, user, ProfileUpdate(**demo_profile_fields())
    )
    for entry in demo_experiences():
        await resume_service.create_experience(  # type: ignore[arg-type]
            session, user, ExperienceCreate(**entry)
        )


async def _open_demo_guardrails(session: object, email: str) -> None:
    """Make the demo account able to complete a run end to end."""
    from sqlalchemy import select

    from app.models import User, UserSettings

    found = await session.execute(  # type: ignore[attr-defined]
        select(User).where(User.email == email.strip().lower())
    )
    user = found.scalar_one_or_none()
    if user is None:
        return

    rows = await session.execute(  # type: ignore[attr-defined]
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    row = rows.scalar_one_or_none()
    if row is None:
        return

    row.dry_run = False
    # Nothing is scored below this in the demo, so no posting is filtered out
    # before the interesting part.
    row.min_score = 0
    row.action_delay_min = 0
    row.action_delay_max = 0
    row.apply_delay_min = 0
    row.apply_delay_max = 0
    row.working_hour_start = 0
    row.working_hour_end = 0
    # Never touched: this is the guarantee the demo exists to demonstrate.
    row.require_manual_approval = True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="demo_server.py", description="Run the app self-contained, with no configuration."
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument(
        "--data-dir",
        default=str(PROJECT_ROOT / "backend" / "data" / "demo"),
        help="Where the throwaway database lives.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete the data directory first, for a clean run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_dir = Path(args.data_dir).resolve()

    if args.fresh and data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Set before importing anything that reads settings: `get_settings` is cached
    # on first call, so a later change would not be seen.
    os.environ.update(demo_environment(data_dir, port=args.port))

    from app.config import get_settings
    from app.observability import configure_logging

    get_settings.cache_clear()
    configure_logging(level="INFO")

    asyncio.run(seed(args.email, args.password))

    print("=" * 72)
    print("  Demo mode: offline AI provider, bundled fake job portal.")
    print("  No real application is sent anywhere, and no data leaves this machine.")
    print("=" * 72)
    print(f"  API        http://127.0.0.1:{args.port}")
    print("  Dashboard  http://localhost:5173   (run `npm run dev` in frontend/)")
    print(f"  Sign in    {args.email} / {args.password}")
    print("=" * 72)

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
