"""Shared fixtures.

Every test gets its own in-memory SQLite database, a deterministic `Settings`, and
fakes wired in place of the Anthropic client and the LinkedIn browser service, so
no test can reach the network even by accident.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.security import create_access_token
from app.config import get_settings
from app.database.base import Base
from app.database.session import get_session
from tests import import_first
from tests.fixtures.factories import DEFAULT_PASSWORD, create_user
from tests.fixtures.fake_ai import FakeAIClient
from tests.fixtures.fake_linkedin import FakeLinkedInService

# Fixed, obviously-fake values: a real .env must never leak into a test run.
TEST_ENV: dict[str, str] = {
    "ENVIRONMENT": "test",
    "DEBUG": "false",
    "SECRET_KEY": "test-secret-key-not-for-production-use",
    "ENCRYPTION_KEY": "test-encryption-key-not-for-production-use",
    "ANTHROPIC_API_KEY": "test-anthropic-key-never-sent-anywhere",
    "ANTHROPIC_MODEL": "claude-opus-5",
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "HEADLESS": "true",
    "ASSISTED_MODE_ONLY": "true",
    "DEFAULT_DAILY_CAP": "15",
    "DEFAULT_MIN_SCORE": "70",
    "CORS_ORIGINS": "http://testserver",
}

# Module paths that may hold the pieces other agents still own.
APP_MODULES = ("app.main", "app.api.main", "app.asgi", "app.app")
AI_CLIENT_MODULES = ("app.ai", "app.ai.client", "app.ai.claude")
ENGINE_MODULES = (
    "app.automation.engine",
    "app.automation.orchestrator",
    "app.services.automation",
    "app.automation.runner",
)
LINKEDIN_MODULES = (
    "app.automation.linkedin",
    "app.automation.linkedin.service",
    "app.automation.session",
    "app.automation.factory",
)
AI_CLIENT_FACTORIES = ("get_ai_client", "build_ai_client", "ai_client")
LINKEDIN_FACTORIES = (
    "get_linkedin_service",
    "build_linkedin_service",
    "create_linkedin_service",
    "linkedin_service_factory",
)


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session", autouse=True)
def test_settings(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    """Deterministic settings for the whole session.

    `Settings` reads the environment at instantiation and `get_settings` is
    `lru_cache`d, so setting the environment and clearing the cache is what makes
    every consumer — including modules that did `from app.config import
    get_settings` — see these values.
    """
    from app.auth import crypto

    previous = {key: os.environ.get(key) for key in TEST_ENV}
    os.environ.update(TEST_ENV)
    os.environ["DATA_DIR"] = str(tmp_path_factory.mktemp("data"))

    get_settings.cache_clear()
    crypto._fernet.cache_clear()

    yield get_settings()

    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    os.environ.pop("DATA_DIR", None)
    get_settings.cache_clear()
    crypto._fernet.cache_clear()


# --------------------------------------------------------------------------- #
# Offline guards
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make constructing a real Anthropic or Playwright client fail loudly."""

    def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError(
            "Tests are offline: a real network client was constructed. "
            "Use FakeAIClient / FakeLinkedInService instead."
        )

    anthropic = import_first("anthropic")
    if anthropic is not None:
        for name in ("Anthropic", "AsyncAnthropic"):
            monkeypatch.setattr(anthropic, name, _forbidden, raising=False)

    playwright = import_first("playwright.async_api")
    if playwright is not None:
        monkeypatch.setattr(playwright, "async_playwright", _forbidden, raising=False)


@pytest.fixture(autouse=True)
def cap_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep production delays from making the suite wait on real time.

    Only shortens: a `sleep` still yields to the loop, so cooperative code (the
    kill switch, for one) behaves exactly as it does in production.
    """
    real_sleep = asyncio.sleep

    async def _fast_sleep(delay: float, *args: Any, **kwargs: Any) -> Any:
        return await real_sleep(0, *args, **kwargs)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)


@pytest.fixture
def sleep_spy(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Records every `asyncio.sleep` duration without waiting for it."""
    real_sleep = asyncio.sleep
    recorded: list[float] = []

    async def _record(delay: float, *args: Any, **kwargs: Any) -> Any:
        recorded.append(delay)
        return await real_sleep(0, *args, **kwargs)

    monkeypatch.setattr(asyncio, "sleep", _record)
    return recorded


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


@pytest.fixture
def fake_ai() -> FakeAIClient:
    return FakeAIClient()


@pytest.fixture
def fake_linkedin() -> FakeLinkedInService:
    return FakeLinkedInService()


@pytest.fixture(autouse=True)
def wire_fakes(
    monkeypatch: pytest.MonkeyPatch, fake_ai: FakeAIClient, fake_linkedin: FakeLinkedInService
) -> None:
    """Replace the AI client and LinkedIn service factories everywhere they live."""
    for path in AI_CLIENT_MODULES:
        module = import_first(path)
        if module is None:
            continue
        for name in AI_CLIENT_FACTORIES:
            monkeypatch.setattr(module, name, lambda *a, **k: fake_ai, raising=False)

    for path in (*LINKEDIN_MODULES, *ENGINE_MODULES):
        module = import_first(path)
        if module is None:
            continue
        for name in LINKEDIN_FACTORIES:
            monkeypatch.setattr(module, name, lambda *a, **k: fake_linkedin, raising=False)


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A private in-memory database per test.

    `StaticPool` keeps every connection pointed at the same in-memory database, so
    the API session and a directly-held test session see the same rows.
    """
    import app.models  # noqa: F401  (registers every model on Base.metadata)

    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        future=True,
    )
    async with test_engine.begin() as connection:
        await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield test_engine
    finally:
        await test_engine.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False, class_=AsyncSession)


@pytest.fixture
async def session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as db_session:
        yield db_session


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #


@pytest.fixture
def password() -> str:
    return DEFAULT_PASSWORD


@pytest.fixture
async def user(session: AsyncSession) -> Any:
    return await create_user(session, email="owner@example.com", full_name="Owner User")


@pytest.fixture
async def other_user(session: AsyncSession) -> Any:
    return await create_user(session, email="intruder@example.com", full_name="Intruder User")


@pytest.fixture
def auth_headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def other_auth_headers(other_user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(other_user.id)}"}


# --------------------------------------------------------------------------- #
# ASGI app and HTTP client
# --------------------------------------------------------------------------- #


def build_app() -> Any | None:
    """The FastAPI application, however the app module chose to expose it."""
    module = import_first(*APP_MODULES)
    if module is None:
        return None
    factory = getattr(module, "create_app", None)
    if callable(factory):
        return factory()
    return getattr(module, "app", None)


@pytest.fixture
def app(sessionmaker: async_sessionmaker[AsyncSession]) -> Iterator[Any]:
    """The real app with its database dependency pointed at the test database."""
    application = build_app()
    if application is None:
        pytest.xfail(f"FastAPI app not implemented yet (looked in {', '.join(APP_MODULES)})")

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as db_session:
            try:
                yield db_session
                await db_session.commit()
            except Exception:
                await db_session.rollback()
                raise

    application.dependency_overrides[get_session] = override_get_session
    try:
        yield application
    finally:
        application.dependency_overrides.clear()


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def api_url(app: Any) -> Callable[[str], str]:
    """Prefix a path with `/api`, tolerating a path that already carries it."""

    def _url(path: str) -> str:
        return path if path.startswith("/api") else f"/api{path}"

    return _url
