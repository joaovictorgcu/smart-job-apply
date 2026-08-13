"""ORM models. Importing this module registers everything in SQLAlchemy's metadata."""

from app.models.automation import AutomationRun
from app.models.enums import (
    AnalysisKind,
    AnswerConfidence,
    ApplicationEventType,
    ApplicationOutcome,
    ApplicationStatus,
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
from app.models.user import LinkedInAccount, Profile, User, UserSettings

__all__ = [
    "AIAnalysis",
    "AnalysisKind",
    "AnswerConfidence",
    "Application",
    "ApplicationEvent",
    "ApplicationEventType",
    "ApplicationOutcome",
    "ApplicationStatus",
    "AutomationRun",
    "AutomationRunKind",
    "AutomationRunStatus",
    "InterviewStage",
    "Job",
    "JobStatus",
    "LinkedInAccount",
    "Profile",
    "Search",
    "TailoredResume",
    "User",
    "UserSettings",
]
