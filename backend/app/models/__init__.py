"""ORM models. Importing this module registers everything in SQLAlchemy's metadata."""

from app.models.audit import AuditEvent
from app.models.automation import AutomationRun
from app.models.enums import (
    AnalysisKind,
    AnswerConfidence,
    ApplicationChannel,
    ApplicationEventType,
    ApplicationOutcome,
    ApplicationStatus,
    AuditAction,
    AutomationRunKind,
    AutomationRunStatus,
    JobStatus,
)
from app.models.job import (
    AIAnalysis,
    Application,
    ApplicationEvent,
    InterviewStage,
    Job,
    Search,
    TailoredResume,
)
from app.models.resume import ApplicationResume, Experience

# `JobScore` here is the persisted verdict; `app.ai.schemas.JobScore` is the
# model's output contract. Modules needing both import this one as `JobScoreRow`.
from app.models.score import JobScore
from app.models.user import JobPreferences, LinkedInAccount, Profile, User, UserSettings

__all__ = [
    "AIAnalysis",
    "AnalysisKind",
    "AnswerConfidence",
    "Application",
    "ApplicationChannel",
    "ApplicationEvent",
    "ApplicationEventType",
    "ApplicationOutcome",
    "ApplicationResume",
    "ApplicationStatus",
    "AuditAction",
    "AuditEvent",
    "AutomationRun",
    "AutomationRunKind",
    "AutomationRunStatus",
    "Experience",
    "InterviewStage",
    "Job",
    "JobPreferences",
    "JobScore",
    "JobStatus",
    "LinkedInAccount",
    "Profile",
    "Search",
    "TailoredResume",
    "User",
    "UserSettings",
]
