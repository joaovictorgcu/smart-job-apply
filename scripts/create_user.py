#!/usr/bin/env python3
"""Create an application account from the command line.

The application has no public sign-up page, so this is how the first account is
created. It only touches this application's own credentials — the LinkedIn
password is never stored anywhere.

    python scripts/create_user.py --email you@example.com --name "Your Name"

Omit --password to be prompted for it without it appearing in your shell
history or in the process list.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import sys
from getpass import getpass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import dispose_engine, init_models, session_scope  # noqa: E402
from app.observability import configure_logging, get_logger  # noqa: E402
from app.schemas.auth import RegisterRequest  # noqa: E402
from app.services.user_service import register_user  # noqa: E402

logger = get_logger(__name__)

MIN_PASSWORD_LENGTH = 10


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="create_user.py",
        description="Create an application account.",
    )
    parser.add_argument("--email", help="Login e-mail address.")
    parser.add_argument(
        "--password",
        help=(
            "Account password, at least "
            f"{MIN_PASSWORD_LENGTH} characters. Prompted for when omitted."
        ),
    )
    parser.add_argument("--name", dest="full_name", help="Display name (optional).")
    return parser.parse_args(argv)


def prompt_email() -> str:
    email = input("E-mail: ").strip()
    if not email:
        raise SystemExit("An e-mail address is required.")
    return email


def prompt_password() -> str:
    password = getpass(f"Password (min {MIN_PASSWORD_LENGTH} chars): ")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"The password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password != getpass("Confirm password: "):
        raise SystemExit("The passwords do not match.")
    return password


async def _call_register(session: object, payload: RegisterRequest) -> object:
    """Invoke `register_user` regardless of which argument shape it declares.

    The service layer is owned by another part of the codebase and may take
    either the validated request object or the individual fields; probing the
    signature keeps this script working with both.
    """
    parameters = list(inspect.signature(register_user).parameters)
    takes_payload = any(name in {"payload", "data", "request"} for name in parameters[1:])
    if takes_payload:
        return await register_user(session, payload)  # type: ignore[arg-type]
    return await register_user(  # type: ignore[call-arg]
        session,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )


async def create_user(email: str, password: str, full_name: str | None) -> None:
    payload = RegisterRequest(email=email, password=password, full_name=full_name)

    # Safe on an existing database: it only creates tables that are missing.
    await init_models()

    try:
        async with session_scope() as session:
            user = await _call_register(session, payload)
    finally:
        await dispose_engine()

    user_id = getattr(user, "id", None)
    logger.info("user_created", extra={"email": payload.email, "user_id": user_id})
    print(f"Created account {payload.email} (id={user_id}).")
    print("Log in at http://localhost:5173 (development) or http://localhost:8000 (Docker).")


def main(argv: list[str] | None = None) -> int:
    configure_logging(level="WARNING")
    args = parse_args(argv)
    email = args.email.strip() if args.email else prompt_email()
    password = args.password if args.password else prompt_password()

    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"The password must be at least {MIN_PASSWORD_LENGTH} characters.")

    try:
        asyncio.run(create_user(email, password, args.full_name))
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, do not traceback
        logger.error("user_creation_failed", extra={"email": email, "error": str(exc)})
        print(f"Could not create the account: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
