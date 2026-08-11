"""Enums compartilhados entre ORM, schemas e serviços."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """Ciclo de vida de uma vaga descoberta."""

    DISCOVERED = "discovered"  # encontrada na busca, ainda sem análise
    ANALYZED = "analyzed"  # a IA pontuou
    SKIPPED = "skipped"  # descartada (nota baixa ou decisão do usuário)
    QUEUED = "queued"  # aprovada para preparar candidatura
    APPLIED = "applied"  # candidatura enviada
    FAILED = "failed"  # erro irrecuperável no fluxo


class ApplicationStatus(StrEnum):
    """Ciclo de vida de uma candidatura.

    `AWAITING_REVIEW` é o estado central do modo assistido: o formulário está
    preenchido e parado na etapa de revisão, esperando a confirmação humana.
    """

    DRAFT = "draft"
    PREPARING = "preparing"
    AWAITING_REVIEW = "awaiting_review"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    DISCARDED = "discarded"
    FAILED = "failed"


class ApplicationEventType(StrEnum):
    """Trilha de auditoria por candidatura (para debug e histórico)."""

    JOB_FOUND = "job_found"
    JOB_ANALYZED = "job_analyzed"
    SCORE_ASSIGNED = "score_assigned"
    COVER_LETTER_GENERATED = "cover_letter_generated"
    FORM_OPENED = "form_opened"
    FORM_STEP_COMPLETED = "form_step_completed"
    QUESTION_ANSWERED = "question_answered"
    RESUME_UPLOADED = "resume_uploaded"
    AWAITING_REVIEW = "awaiting_review"
    USER_EDITED = "user_edited"
    USER_APPROVED = "user_approved"
    SUBMITTED = "submitted"
    DISCARDED = "discarded"
    ERROR = "error"


class AutomationRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"  # kill switch
    FAILED = "failed"
    BLOCKED = "blocked"  # CAPTCHA / verificação de segurança


class AutomationRunKind(StrEnum):
    SEARCH = "search"
    PREPARE = "prepare"
    SUBMIT = "submit"


class AnalysisKind(StrEnum):
    SCORING = "scoring"
    COVER_LETTER = "cover_letter"
    SCREENING = "screening"


class AnswerConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"  # exige revisão humana antes do envio
