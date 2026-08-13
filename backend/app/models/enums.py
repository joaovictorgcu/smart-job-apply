"""Enums shared between the ORM, the schemas and the services."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """Lifecycle of a discovered job."""

    DISCOVERED = "discovered"  # found by the search, not analyzed yet
    ANALYZED = "analyzed"  # the AI scored it
    SKIPPED = "skipped"  # discarded (low score or user decision)
    QUEUED = "queued"  # approved for application preparation
    APPLIED = "applied"  # application submitted
    FAILED = "failed"  # unrecoverable error in the flow


class ApplicationStatus(StrEnum):
    """Lifecycle of an application.

    `AWAITING_REVIEW` is the pivotal state of assisted mode: the form is filled in
    and halted at the review step, waiting for human confirmation.
    """

    DRAFT = "draft"
    PREPARING = "preparing"
    AWAITING_REVIEW = "awaiting_review"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    DISCARDED = "discarded"
    FAILED = "failed"


class ApplicationOutcome(StrEnum):
    """Real-world result of an application, tracked after it was submitted.

    Distinct from `ApplicationStatus`, which is the submission *flow* (draft →
    awaiting_review → submitted). Outcome is what happened next, and it is what
    lets the project ask whether a high AI score actually leads to interviews.
    """

    APPLIED = "applied"  # submitted, still waiting for a response
    INTERVIEW = "interview"  # reached at least one interview
    OFFER = "offer"  # received an offer
    REJECTED = "rejected"  # turned down
    GHOSTED = "ghosted"  # no response after a reasonable wait


class ApplicationEventType(StrEnum):
    """Per-application audit trail (for debugging and history)."""

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
    OUTCOME_CHANGED = "outcome_changed"
    DISCARDED = "discarded"
    ERROR = "error"


class AutomationRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"  # kill switch
    FAILED = "failed"
    BLOCKED = "blocked"  # CAPTCHA / security verification


class AutomationRunKind(StrEnum):
    SEARCH = "search"
    PREPARE = "prepare"
    SUBMIT = "submit"


class AnalysisKind(StrEnum):
    SCORING = "scoring"
    COVER_LETTER = "cover_letter"
    SCREENING = "screening"
    CV_TAILORING = "cv_tailoring"
    REVIEW = "review"
    INTERVIEW_PREP = "interview_prep"


class AnswerConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"  # requires human review before submitting
