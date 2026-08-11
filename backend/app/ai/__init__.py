"""AI layer: provider-agnostic contracts plus the Claude implementation."""

from app.ai.client import (
    AIClient,
    AINotConfiguredError,
    detect_language,
    flag_unsupported_skills,
    get_ai_client,
)
from app.ai.schemas import (
    AIUsage,
    CoverLetter,
    CVChange,
    JobAnalysis,
    JobScore,
    QuestionType,
    ScreeningAnswer,
    ScreeningAnswerSet,
    TailoredResume,
)
from app.ai.scoring import analyze_job, answer_screening, generate_cover_letter, tailor_resume

__all__ = [
    "AIClient",
    "AINotConfiguredError",
    "AIUsage",
    "CVChange",
    "CoverLetter",
    "JobAnalysis",
    "JobScore",
    "QuestionType",
    "ScreeningAnswer",
    "ScreeningAnswerSet",
    "TailoredResume",
    "analyze_job",
    "answer_screening",
    "detect_language",
    "flag_unsupported_skills",
    "generate_cover_letter",
    "get_ai_client",
    "tailor_resume",
]
