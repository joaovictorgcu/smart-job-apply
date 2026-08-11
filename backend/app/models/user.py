"""Usuário da aplicação, perfil profissional e configurações."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.automation import AutomationRun
    from app.models.job import Application, Job, Search


class User(Base, TimestampMixin):
    """Conta local da aplicação.

    Só guardamos credenciais **da nossa aplicação** (hash bcrypt). A senha do
    LinkedIn nunca é armazenada: o usuário faz login manualmente no navegador e
    a sessão persiste como cookies criptografados (ver `LinkedInAccount`).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(200), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)

    profile: Mapped[Profile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    settings: Mapped[UserSettings | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    linkedin_account: Mapped[LinkedInAccount | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    searches: Mapped[list[Search]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(back_populates="user", cascade="all, delete-orphan")
    applications: Mapped[list[Application]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    runs: Mapped[list[AutomationRun]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Profile(Base, TimestampMixin):
    """Currículo em texto + banco de respostas usado pela IA."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    headline: Mapped[str | None] = mapped_column(String(300), default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    phone: Mapped[str | None] = mapped_column(String(50), default=None)
    years_of_experience: Mapped[int | None] = mapped_column(Integer, default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    resume_text: Mapped[str | None] = mapped_column(Text, default=None)
    resume_filename: Mapped[str | None] = mapped_column(String(255), default=None)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Respostas padrão para perguntas recorrentes de triagem, ex.:
    # {"salary_expectation": "R$ 15.000", "notice_period": "30 dias",
    #  "work_authorization": "Sim", "years_python": "6"}
    answer_bank: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped[User] = relationship(back_populates="profile")


class UserSettings(Base, TimestampMixin):
    """Guarda-corpos de automação e preferências de IA, por usuário."""

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    # --- Guarda-corpos ---
    daily_cap: Mapped[int] = mapped_column(Integer, default=15)
    min_score: Mapped[int] = mapped_column(Integer, default=70)
    action_delay_min: Mapped[float] = mapped_column(default=2.5)
    action_delay_max: Mapped[float] = mapped_column(default=7.0)
    apply_delay_min: Mapped[float] = mapped_column(default=45.0)
    apply_delay_max: Mapped[float] = mapped_column(default=120.0)
    working_hour_start: Mapped[int] = mapped_column(Integer, default=8)
    working_hour_end: Mapped[int] = mapped_column(Integer, default=20)
    # Nenhum envio sem confirmação explícita. Desligar exige entender o risco.
    require_manual_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)

    # --- IA ---
    ai_model: Mapped[str | None] = mapped_column(String(100), default=None)
    cover_letter_tone: Mapped[str] = mapped_column(String(50), default="profissional")
    # "job" = seguir o idioma da vaga; ou fixar "pt-BR" / "en".
    content_language: Mapped[str] = mapped_column(String(20), default="job")
    generate_cover_letter: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="settings")


class LinkedInAccount(Base, TimestampMixin):
    """Sessão do LinkedIn do usuário — **cookies criptografados em repouso**.

    Nunca armazenamos e-mail/senha do LinkedIn. O usuário loga manualmente no
    navegador; persistimos apenas o estado de sessão, cifrado com AES-GCM
    (Fernet) via `app.auth.crypto`.
    """

    __tablename__ = "linkedin_accounts"
    __table_args__ = (UniqueConstraint("user_id", name="uq_linkedin_account_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    # Rótulo apenas informativo (ex.: nome exibido no LinkedIn).
    display_name: Mapped[str | None] = mapped_column(String(200), default=None)
    encrypted_storage_state: Mapped[str | None] = mapped_column(Text, default=None)
    browser_profile_dir: Mapped[str | None] = mapped_column(String(500), default=None)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(back_populates="linkedin_account")
