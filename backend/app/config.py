"""Application configuration, loaded from environment variables / .env."""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "LinkedIn Auto Apply"
    environment: str = "development"
    debug: bool = False

    # --- Security ---
    # Signs the JWTs. Set it explicitly in production; without a value we generate
    # a random one per process (every session is dropped on each restart).
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    # Derives the key that encrypts sensitive data at rest (LinkedIn session
    # cookies). Changing this value makes already stored data unreadable.
    encryption_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 12

    # --- AI ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"
    # Effort used for bulk scoring (cheaper); the cover letter uses "high".
    scoring_effort: str = "low"

    # --- Database ---
    # SQLite by default; switch to postgresql+asyncpg://... without touching code.
    database_url: str = ""

    # --- Automation ---
    headless: bool = False
    max_concurrent_sessions: int = 1
    # Conservative default guardrails — the user can adjust them in settings.
    default_daily_cap: int = 15
    default_min_score: int = 70
    default_action_delay_range: tuple[float, float] = (2.5, 7.0)
    default_apply_delay_range: tuple[float, float] = (45.0, 120.0)
    default_working_hours: tuple[int, int] = (8, 20)
    # Never submits an application without explicit confirmation from the user.
    assisted_mode_only: bool = True

    # --- Network ---
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    rate_limit_default: str = "120/minute"
    rate_limit_auth: str = "10/minute"

    # --- Paths ---
    data_dir: Path = BACKEND_DIR / "data"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("default_action_delay_range", "default_apply_delay_range", mode="before")
    @classmethod
    def _parse_range(cls, value: object) -> object:
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",")]
            if len(parts) == 2:
                return (float(parts[0]), float(parts[1]))
        return value

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def browser_profiles_dir(self) -> Path:
        path = self.data_dir / "browser_profiles"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def resumes_dir(self) -> Path:
        path = self.data_dir / "resumes"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
