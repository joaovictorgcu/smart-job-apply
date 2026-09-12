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


class ApplicationChannel(StrEnum):
    """How an application reaches the employer.

    `EASY_APPLY` is the LinkedIn form the engine fills in and sends after the
    human approves it. `EXTERNAL` is a posting whose form lives on the company's
    own site — the app prepares the content, the *user* submits it there, and
    then records that it happened. The two are mutually exclusive doors: an
    external application is never sent by the engine, and an Easy Apply one is
    never written down as a manual act.
    """

    EASY_APPLY = "easy_apply"
    EXTERNAL = "external"

    @classmethod
    def for_job(cls, *, source: str, easy_apply: bool) -> ApplicationChannel:
        """Which channel a job's application has to use.

        Derived from the posting rather than asked of the user: a job with no
        Easy Apply button, or one discovered on a portal the automation cannot
        drive, can only be applied to on the company's own site. The app already
        knows both facts, so making the user restate them would be a question
        with exactly one correct answer.
        """
        if easy_apply and source == "linkedin":
            return cls.EASY_APPLY
        return cls.EXTERNAL


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
    # The posting's form no longer matches the one the user reviewed, so the
    # submission was refused instead of sent against a different document.
    FORM_CHANGED = "form_changed"
    QUESTION_ANSWERED = "question_answered"
    RESUME_UPLOADED = "resume_uploaded"
    # The application's own copy of the resume was derived from the master, or
    # derived again. Recorded so "which resume is this application using, and
    # since when" is answerable from the trail the user already reads.
    RESUME_ADAPTED = "resume_adapted"
    AWAITING_REVIEW = "awaiting_review"
    USER_EDITED = "user_edited"
    USER_APPROVED = "user_approved"
    SUBMITTED = "submitted"
    OUTCOME_CHANGED = "outcome_changed"
    DISCARDED = "discarded"
    ERROR = "error"


class AuditAction(StrEnum):
    """Account-level changes that must survive a log rotation.

    Distinct from `ApplicationEventType`, which explains one application: this
    trail answers who loosened the guardrails, and when.
    """

    SETTINGS_UPDATED = "settings_updated"
    PROFILE_UPDATED = "profile_updated"
    RESUME_UPLOADED = "resume_uploaded"
    # An administrator read the platform-wide panel. Recorded once per admin per
    # day rather than per page load: the answer worth keeping is "who has access
    # and used it", and a row per refresh would bury every other entry in the
    # trail. See `admin_service.record_panel_access`.
    ADMIN_ACCESS = "admin_access"


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
