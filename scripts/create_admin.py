#!/usr/bin/env python3
"""Create — or promote — the administrator account for the admin panel.

The panel at /admin sees every account's aggregate metrics, so the role that
opens it is granted here explicitly and never by a request. This script is the
only writer of `users.is_admin`.

The password is read from the environment (`ADMIN_EMAIL` / `ADMIN_PASSWORD`, so
`.env` works) or asked for interactively. It is deliberately *not* a default in
the code: a password committed to a repository is a password in production.

    # values from .env / the environment
    python scripts/create_admin.py

    # explicit, prompted for the password
    python scripts/create_admin.py --email admin@admin.com

    # an existing account becomes an administrator, password untouched
    python scripts/create_admin.py --email me@example.com --promote-only

Running it again on an existing account is safe: it promotes, and rewrites the
password only when `--reset-password` is given.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from getpass import getpass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.auth.security import hash_password  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database.session import dispose_engine, init_models, session_scope  # noqa: E402
from app.observability import configure_logging, get_logger  # noqa: E402
from app.services.user_service import get_by_email, register_user  # noqa: E402

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="create_admin.py",
        description="Create or promote the administrator account.",
    )
    parser.add_argument("--email", help="Login e-mail. Defaults to ADMIN_EMAIL.")
    parser.add_argument(
        "--password",
        help=(
            "Account password. Defaults to ADMIN_PASSWORD; prompted for when "
            "neither is set. Prefer the environment: an argument is visible in "
            "the shell history and the process list."
        ),
    )
    parser.add_argument("--name", dest="full_name", default="Administrador")
    parser.add_argument(
        "--promote-only",
        action="store_true",
        help="Only grant the role to an existing account. Never touches the password.",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Also rewrite the password of an existing account.",
    )
    return parser.parse_args(argv)


def _check_password(password: str) -> None:
    """Refuse a weak password in production; allow it, loudly, anywhere else."""
    settings = get_settings()
    minimum = settings.admin_min_password_length
    if len(password) >= minimum:
        return
    if settings.environment.strip().lower() in {"production", "prod"}:
        raise SystemExit(
            f"ENVIRONMENT={settings.environment}: the administrator password must be "
            f"at least {minimum} characters."
        )
    print(
        f"WARNING: this administrator password is shorter than {minimum} characters. "
        f"Accepted because ENVIRONMENT={settings.environment}. Do not ship it.",
        file=sys.stderr,
    )


async def _apply(
    email: str,
    password: str | None,
    full_name: str,
    *,
    promote_only: bool,
    reset_password: bool,
) -> None:
    normalized = email.strip().lower()

    # Safe on an existing database: only missing tables are created.
    await init_models()
    try:
        async with session_scope() as session:
            existing = await get_by_email(session, normalized)
            if existing is None:
                if promote_only:
                    raise SystemExit(
                        f"No account for {normalized}; drop --promote-only to create one."
                    )
                if password is None:
                    raise SystemExit("A password is required to create the account.")
                user = await register_user(
                    session, email=normalized, password=password, full_name=full_name
                )
                user.is_admin = True
                action = "created"
            else:
                user = existing
                was_admin = user.is_admin
                user.is_admin = True
                # Re-running the script must not silently change the password of
                # an account somebody is already using. Rewriting it is an
                # explicit request.
                if reset_password and password is not None:
                    user.hashed_password = hash_password(password)
                if not user.is_active:
                    # An administrator who cannot log in is not an administrator.
                    user.is_active = True
                if reset_password:
                    action = "password reset"
                else:
                    action = "already an administrator" if was_admin else "promoted"
            user_id = user.id
    finally:
        await dispose_engine()

    # The password is never logged and never printed back.
    logger.info(
        "admin_account_ready",
        extra={"email": normalized, "user_id": user_id, "outcome": action},
    )
    print(f"Administrator {normalized} (id={user_id}) — {action}.")
    print("Open /admin after logging in.")


def main(argv: list[str] | None = None) -> int:
    configure_logging(level="WARNING")
    args = parse_args(argv)
    settings = get_settings()

    email = (args.email or settings.admin_email or "").strip()
    if not email:
        email = input("Admin e-mail: ").strip()
    if not email:
        raise SystemExit("An e-mail address is required.")

    password: str | None = None
    if not args.promote_only:
        password = args.password or settings.admin_password or None
        if password is None:
            password = getpass("Admin password: ") or None
        if password is None:
            raise SystemExit("A password is required (or use --promote-only).")
        _check_password(password)
    elif args.reset_password:
        raise SystemExit("--reset-password and --promote-only contradict each other.")

    try:
        asyncio.run(
            _apply(
                email,
                password,
                args.full_name,
                promote_only=args.promote_only,
                reset_password=args.reset_password,
            )
        )
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, do not traceback
        logger.error("admin_setup_failed", extra={"email": email, "error": str(exc)})
        print(f"Could not set up the administrator: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
