"""Usuário, perfil, configurações e status da conexão com o LinkedIn."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.common import ORMModel


class UserRead(ORMModel):
    id: int
    email: EmailStr
    full_name: str | None = None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class ProfileRead(ORMModel):
    headline: str | None = None
    location: str | None = None
    phone: str | None = None
    years_of_experience: int | None = None
    summary: str | None = None
    resume_text: str | None = None
    resume_filename: str | None = None
    skills: list[str] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    answer_bank: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None


class ProfileUpdate(BaseModel):
    headline: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    years_of_experience: int | None = Field(default=None, ge=0, le=70)
    summary: str | None = None
    resume_text: str | None = None
    skills: list[str] | None = None
    preferred_languages: list[str] | None = None
    answer_bank: dict[str, Any] | None = None


class UserSettingsRead(ORMModel):
    daily_cap: int
    min_score: int
    action_delay_min: float
    action_delay_max: float
    apply_delay_min: float
    apply_delay_max: float
    working_hour_start: int
    working_hour_end: int
    require_manual_approval: bool
    dry_run: bool
    ai_model: str | None = None
    cover_letter_tone: str
    content_language: str
    generate_cover_letter: bool


class UserSettingsUpdate(BaseModel):
    # Teto de 50/dia: acima disso o padrão de uso deixa de parecer humano.
    daily_cap: int | None = Field(default=None, ge=1, le=50)
    min_score: int | None = Field(default=None, ge=0, le=100)
    action_delay_min: float | None = Field(default=None, ge=0.5, le=60)
    action_delay_max: float | None = Field(default=None, ge=0.5, le=120)
    apply_delay_min: float | None = Field(default=None, ge=5, le=600)
    apply_delay_max: float | None = Field(default=None, ge=5, le=1800)
    working_hour_start: int | None = Field(default=None, ge=0, le=23)
    working_hour_end: int | None = Field(default=None, ge=1, le=24)
    require_manual_approval: bool | None = None
    dry_run: bool | None = None
    ai_model: str | None = Field(default=None, max_length=100)
    cover_letter_tone: str | None = Field(default=None, max_length=50)
    content_language: str | None = Field(default=None, max_length=20)
    generate_cover_letter: bool | None = None

    @model_validator(mode="after")
    def _check_ranges(self) -> UserSettingsUpdate:
        if (
            self.action_delay_min is not None
            and self.action_delay_max is not None
            and self.action_delay_min > self.action_delay_max
        ):
            raise ValueError("action_delay_min não pode ser maior que action_delay_max.")
        if (
            self.apply_delay_min is not None
            and self.apply_delay_max is not None
            and self.apply_delay_min > self.apply_delay_max
        ):
            raise ValueError("apply_delay_min não pode ser maior que apply_delay_max.")
        if (
            self.working_hour_start is not None
            and self.working_hour_end is not None
            and self.working_hour_start >= self.working_hour_end
        ):
            raise ValueError("working_hour_start deve ser menor que working_hour_end.")
        return self


class LinkedInAccountRead(ORMModel):
    """Só metadados. Nenhum cookie ou credencial sai pela API."""

    display_name: str | None = None
    is_connected: bool = False
    last_verified_at: datetime | None = None


class SessionStatus(BaseModel):
    """Estado atual do navegador/automação para o painel."""

    browser_open: bool = False
    logged_in: bool = False
    blocked: bool = False
    blocked_reason: str | None = None
    active_run_id: int | None = None
    applications_today: int = 0
    daily_cap: int = 0
    dry_run: bool = True
    ai_configured: bool = False
