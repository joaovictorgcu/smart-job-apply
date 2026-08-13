"""Prompt for the interview preparation pack.

Fed only by what the app already stores: the posting (frozen at submit time,
because LinkedIn postings vanish), the exact materials that were sent, the fit
score's gaps, and the candidate's profile. No web research, no invention.
"""

from __future__ import annotations

from typing import Any

from app.ai.prompts import (
    UNTRUSTED_TEXT_RULE,
    JobLike,
    render_job_block,
    render_profile_block,
)
from app.automation.contracts import ProfileContext

INTERVIEW_PREP_SYSTEM_PROMPT = f"""\
You prepare a candidate for a job interview. Work only from the material given: \
the posting, the candidate's profile, the exact application that was submitted, \
and the fit analysis. Never invent facts about the company, the interviewers, or \
the candidate.

{UNTRUSTED_TEXT_RULE}

Write the pack in Markdown, in the same language as the submitted cover letter \
(default to the posting's language when there is none), with exactly these \
sections:

## Provaveis perguntas
The requirements the fit analysis marked as missing or weak are what an \
interviewer probes first. For each, one likely question and a one-line honest \
angle the candidate can take (bridge from adjacent experience — never a claim \
the profile cannot back).

## Consistencia com o que foi enviado
Every concrete claim in the submitted letter and answers (numbers, years, named \
technologies) listed as a checklist, so the candidate re-reads exactly what the \
interviewer read and contradicts nothing.

## Historias para ter na ponta da lingua
2-4 experiences from the profile worth telling as stories for THIS posting, one \
line each on why.

## Perguntas para fazer
3-5 questions the candidate can ask, grounded in what the posting actually says \
— never generic filler.

Keep the whole pack under 600 words. Be direct; no motivational padding.
"""


def build_interview_prep_prompt(
    profile: ProfileContext,
    job: JobLike,
    *,
    submitted_cover_letter: str | None,
    submitted_answers: list[dict[str, Any]],
    missing_requirements: list[str],
    score_summary: str | None,
) -> str:
    """Render the prep request from the stored application data."""
    answers = "\n".join(
        f"Q: {answer.get('question', '')}\nA: {answer.get('answer', '')}"
        for answer in submitted_answers
    )
    gaps = "\n".join(f"- {item}" for item in missing_requirements) or "(none recorded)"
    return (
        "Prepare this candidate for an interview for the posting below.\n\n"
        "=== CANDIDATE ===\n"
        f"{render_profile_block(profile)}\n\n"
        "=== JOB POSTING ===\n"
        f"{render_job_block(job)}\n\n"
        "=== FIT ANALYSIS: REQUIREMENTS MARKED MISSING/WEAK ===\n"
        f"{gaps}\n"
        f"Score summary: {score_summary or '(none)'}\n\n"
        "=== SUBMITTED COVER LETTER (what the interviewer read) ===\n"
        f"{(submitted_cover_letter or '').strip() or '(no cover letter was sent)'}\n\n"
        "=== SUBMITTED SCREENING ANSWERS ===\n"
        f"{answers or '(none)'}\n\n"
        "Write the four-section prep pack."
    )


__all__ = ["INTERVIEW_PREP_SYSTEM_PROMPT", "build_interview_prep_prompt"]
