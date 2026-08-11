"""Shared fixtures.

Every test gets its own in-memory SQLite database, a deterministic `Settings`, and
fakes in place of the Anthropic client and the LinkedIn browser service, so no test
can reach the network even by accident.

The test engine is installed into `app.database.session` itself, not only into the
FastAPI dependency: the automation engine opens its own sessions with
`session_scope()`, and it has to see the same rows the test does.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.auth.security import create_access_token
from app.config import get_settings
from app.database.base import Base
from app.database.session import get_session
from tests import import_first
from tests.fixtures.factories import create_user
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

# Where `get_ai_client` is looked up. Patching every binding covers callers that
# imported the name into their own module namespace.
AI_FACTORY_MODULES = ("app.ai.scoring", "app.ai.client", "app.ai")


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
    previous["DATA_DIR"] = os.environ.get("DATA_DIR")
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
    client_module = import_first("app.ai.client")
    if client_module is not None:
        monkeypatch.setattr(client_module, "AsyncAnthropic", _forbidden, raising=False)

    playwright = import_first("playwright.async_api")
    if playwright is not None:
        monkeypatch.setattr(playwright, "async_playwright", _forbidden, raising=False)
    browser_module = import_first("app.automation.browser")
    if browser_module is not None:
        monkeypatch.setattr(browser_module, "async_playwright", _forbidden, raising=False)


@pytest.fixture(autouse=True)
def cap_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep production delays from making the suite wait on real time.

    Only ever shortens a sleep. It still yields to the loop, so cooperative code
    (the kill switch, for one) behaves exactly as it does in production.
    """
    real_sleep = asyncio.sleep

    async def _fast_sleep(delay: float = 0, *args: Any, **kwargs: Any) -> Any:
        return await real_sleep(0, *args, **kwargs)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)


@pytest.fixture
def sleep_spy(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Records every `asyncio.sleep` duration without waiting for it."""
    real_sleep = asyncio.sleep
    recorded: list[float] = []

    async def _record(delay: float = 0, *args: Any, **kwargs: Any) -> Any:
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
    """Replace the AI client factory and the browser service at their real seams."""
    for path in AI_FACTORY_MODULES:
        module = import_first(path)
        if module is not None:
            monkeypatch.setattr(
                module, "get_ai_client", lambda *a, **k: fake_ai, raising=False
            )

    engine_module = import_first("app.automation.engine")
    if engine_module is not None:
        monkeypatch.setattr(
            engine_module,
            "LinkedInBrowserService",
            lambda *a, **k: fake_linkedin,
            raising=False,
        )


@pytest.fixture(autouse=True)
def automation_engine(monkeypatch: pytest.MonkeyPatch) -> Any:
    """A fresh engine per test: the real one is a process-wide singleton."""
    engine_module = import_first("app.automation.engine")
    if engine_module is None:
        return None
    monkeypatch.setattr(engine_module, "_engine", None, raising=False)
    instance = engine_module.get_engine()
    monkeypatch.setattr(engine_module, "_engine", instance, raising=False)
    return instance


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #


@pytest.fixture
async def engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> AsyncIterator[AsyncEngine]:
    """A private database per test, installed app-wide.

    A throwaway SQLite *file* rather than `:memory:`. The automation engine opens
    its own sessions with `session_scope()` while the test holds one of its own,
    and a single shared in-memory connection cannot serve both — a file gives each
    session a real connection, exactly as in production.
    """
    import app.models  # noqa: F401  (registers every model on Base.metadata)
    from app.database import session as session_module

    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    async with test_engine.begin() as connection:
        # WAL keeps a reader from blocking the engine's writer mid-test.
        await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(
        test_engine, expire_on_commit=False, autoflush=False, class_=AsyncSession
    )
    monkeypatch.setattr(session_module, "_engine", test_engine, raising=False)
    monkeypatch.setattr(session_module, "_sessionmaker", maker, raising=False)
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


@pytest.fixture
def app(sessionmaker: async_sessionmaker[AsyncSession]) -> Iterator[Any]:
    """The real app with its database dependency pointed at the test database.

    The rate limiter is disabled: the suite fires far more requests per minute from
    one address than a human would, and 429s are not what these tests are about.
    """
    from app.main import create_app

    application = create_app()
    if getattr(application.state, "limiter", None) is not None:
        application.state.limiter.enabled = False

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
