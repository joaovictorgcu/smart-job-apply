"""AI layer: provider-agnostic contracts plus the Claude implementation."""

from app.ai.client import (
    AIClient,
    AINotConfiguredError,
    detect_language,
    get_ai_client,
)
from app.ai.schemas import (
    AIUsage,
    CoverLetter,
    JobAnalysis,
    JobScore,
    QuestionType,
    ScreeningAnswer,
    ScreeningAnswerSet,
)
from app.ai.scoring import analyze_job, answer_screening, generate_cover_letter

__all__ = [
    "AIClient",
    "AINotConfiguredError",
    "AIUsage",
    "CoverLetter",
    "JobAnalysis",
    "JobScore",
    "QuestionType",
    "ScreeningAnswer",
    "ScreeningAnswerSet",
    "analyze_job",
    "answer_screening",
    "detect_language",
    "generate_cover_letter",
    "get_ai_client",
]
