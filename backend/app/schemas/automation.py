"""Execuções de automação: iniciar busca, preparar, confirmar envio."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AutomationRunKind, AutomationRunStatus
from app.schemas.common import ORMModel
from app.schemas.job import JobRead


class SearchRunRequest(BaseModel):
    """Executa uma busca salva ou filtros ad-hoc."""

    search_id: int | None = None
    keywords: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    remote_filter: str | None = None
    date_posted: str | None = None
    experience_levels: list[str] = Field(default_factory=list)
    max_results: int = Field(default=25, ge=1, le=100)
    # Busca + análise de IA nunca envia nada; o envio é sempre um passo separado.
    analyze: bool = True


class PreviewResponse(BaseModel):
    """Confirmação antes de processar: o usuário vê o volume e decide.

    Exigido antes de qualquer candidatura real, para nunca haver surpresa de
    "enviei dezenas sem você ver".
    """

    jobs_to_process: int
    already_applied: int = 0
    below_threshold: int = 0
    remaining_today: int = 0
    daily_cap: int = 0
    dry_run: bool = True
    requires_confirmation: bool = True
    jobs: list[JobRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PrepareRequest(BaseModel):
    """Preenche o formulário até a etapa de revisão. Não envia."""

    job_ids: list[int] = Field(min_length=1, max_length=50)
    confirmed: bool = Field(
        default=False, description="Precisa ser true após o usuário revisar o preview."
    )


class SubmitRequest(BaseModel):
    """Aprovação explícita de uma candidatura já revisada."""

    confirm: bool = Field(description="Precisa ser true; é o consentimento do envio.")


class AutomationRunRead(ORMModel):
    id: int
    kind: AutomationRunKind
    status: AutomationRunStatus
    dry_run: bool
    search_id: int | None = None
    jobs_found: int = 0
    jobs_analyzed: int = 0
    jobs_skipped: int = 0
    applications_prepared: int = 0
    applications_submitted: int = 0
    stop_requested: bool = False
    blocked_reason: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
