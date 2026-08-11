"""Fronteira entre lógica de negócio e Playwright.

`Engine` → `LinkedInService` → Playwright. O engine e os serviços só conhecem
estas estruturas; se o LinkedIn mudar a interface, o conserto fica confinado à
implementação de `LinkedInService` (`automation/linkedin/*`) e `selectors.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

QuestionKind = Literal["text", "textarea", "number", "select", "radio", "checkbox", "unknown"]


@dataclass(slots=True)
class SearchFilters:
    """Filtros normalizados de busca (sem detalhes de URL do LinkedIn)."""

    keywords: str
    location: str | None = None
    remote_filter: str | None = None
    date_posted: str | None = None
    experience_levels: list[str] = field(default_factory=list)
    easy_apply_only: bool = True
    max_results: int = 25


@dataclass(slots=True)
class JobPosting:
    """Uma vaga como vista no LinkedIn (sem nada específico de Playwright)."""

    external_id: str
    title: str
    company: str
    location: str | None = None
    url: str | None = None
    description: str | None = None
    workplace_type: str | None = None
    easy_apply: bool = False
    posted_at: datetime | None = None
    already_applied: bool = False


@dataclass(slots=True)
class FormQuestion:
    """Um campo do formulário de Candidatura Simplificada."""

    field_id: str
    label: str
    kind: QuestionKind = "unknown"
    options: list[str] = field(default_factory=list)
    required: bool = False
    current_value: str | None = None


@dataclass(slots=True)
class FormAnswer:
    """Valor a preencher em um campo."""

    field_id: str
    value: str
    kind: QuestionKind = "unknown"


@dataclass(slots=True)
class ApplicationDraft:
    """Formulário preenchido, parado na etapa de revisão, aguardando aprovação."""

    job_external_id: str
    questions: list[FormQuestion] = field(default_factory=list)
    answers: list[FormAnswer] = field(default_factory=list)
    unanswered: list[FormQuestion] = field(default_factory=list)
    total_steps: int | None = None
    current_step: int | None = None
    resume_attached: bool = False
    cover_letter_attached: bool = False
    ready_to_submit: bool = False
    screenshot_path: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SessionState:
    browser_open: bool = False
    logged_in: bool = False
    blocked: bool = False
    blocked_reason: str | None = None
    current_url: str | None = None
    display_name: str | None = None


@runtime_checkable
class LinkedInService(Protocol):
    """O que o engine pode pedir ao LinkedIn.

    Toda implementação deve levantar os erros de `automation.errors` — em
    especial `SecurityCheckpointError`, que interrompe tudo.
    """

    async def start(self) -> SessionState:
        """Abre o navegador (restaurando a sessão salva, se houver)."""
        ...

    async def stop(self) -> None:
        """Fecha o navegador e persiste o estado da sessão."""
        ...

    async def get_state(self) -> SessionState:
        ...

    async def wait_for_login(self, timeout_seconds: int = 300) -> SessionState:
        """Espera o usuário logar manualmente na janela aberta."""
        ...

    async def search_jobs(self, filters: SearchFilters) -> list[JobPosting]:
        """Retorna vagas correspondentes (só Easy Apply se solicitado)."""
        ...

    async def fetch_job_details(self, external_id: str) -> JobPosting:
        """Abre a vaga e retorna a descrição completa."""
        ...

    async def open_easy_apply(self, external_id: str) -> list[FormQuestion]:
        """Abre o modal de Candidatura Simplificada e devolve os campos do passo atual."""
        ...

    async def fill_and_advance(
        self, answers: list[FormAnswer], *, cover_letter: str | None = None
    ) -> ApplicationDraft:
        """Preenche, avança os passos e **para** na revisão. Nunca envia."""
        ...

    async def submit(self) -> bool:
        """Clica em enviar. Só é chamado após aprovação explícita do usuário."""
        ...

    async def discard(self) -> None:
        """Fecha o modal descartando o rascunho."""
        ...

    async def capture_screenshot(self, name: str) -> str | None:
        """Captura a tela atual (para o painel e para debug)."""
        ...


@dataclass(slots=True)
class ProfileContext:
    """Dados do usuário passados à IA e ao preenchimento (sem tocar no ORM)."""

    full_name: str | None = None
    email: str | None = None
    headline: str | None = None
    location: str | None = None
    phone: str | None = None
    years_of_experience: int | None = None
    summary: str | None = None
    resume_text: str | None = None
    resume_path: str | None = None
    skills: list[str] = field(default_factory=list)
    answer_bank: dict[str, Any] = field(default_factory=dict)
    preferred_languages: list[str] = field(default_factory=list)
