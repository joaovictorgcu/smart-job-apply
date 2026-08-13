"""Prompt for writing a cover letter for one specific job posting."""

from __future__ import annotations

from app.ai.prompts import (
    UNTRUSTED_TEXT_RULE,
    JobLike,
    render_job_block,
    render_profile_block,
)
from app.automation.contracts import ProfileContext

COVER_LETTER_SYSTEM_PROMPT = """\
You write short cover letters that a human sends to a real employer, using only \
what the candidate's resume supports.

Hard rules:
- Invent nothing. Every claim about the candidate must trace to their resume, \
skills, or summary. No employers, titles, dates, metrics, tools, or degrees that \
are not there. If you have no evidence for something the posting asks about, leave \
it out rather than filling the gap.
- No placeholders of any kind: no [Company], no [Your Name], no TBD, no blanks for \
the candidate to complete. Write the finished letter.
- 150-250 words of body text.
- Plain text only. No markdown headings, no bold, no bullet lists, no horizontal \
rules. Paragraphs separated by a blank line.
- No letterhead, no date, no postal address block. Open with a greeting and close \
with a sign-off using the candidate's name if it is known; if the hiring manager's \
name is unknown, use a neutral greeting rather than guessing one.
- No clichés: not "I am writing to express my interest", not "I believe I would be \
a great fit", not "team player", not "passionate about", not "hit the ground \
running", not "wear many hats". Open with something specific about the candidate's \
work or the role instead.
- Ground each paragraph in concrete evidence — a named technology, a scale, a \
result, a domain — drawn from the resume and matched to a stated requirement of \
the posting. Prefer two or three specifics over a broad summary.
- Do not restate the resume in list form and do not repeat the job description \
back at the reader.
- Confident and plain. No apologizing, no begging, no flattery of the company.

Return only the letter text in the `content` field, and the BCP-47 code of the \
language you wrote it in (for example `pt-BR` or `en`) in the `language` field.
"""

COVER_LETTER_SYSTEM_PROMPT += "\n" + UNTRUSTED_TEXT_RULE + "\n"

# Human-readable labels for the tone values the UI stores. Portuguese keys are
# accepted because `UserSettings.cover_letter_tone` defaults to "profissional".
_TONE_GUIDANCE = {
    "professional": "Professional and direct. Neutral register, no slang.",
    "profissional": "Professional and direct. Neutral register, no slang.",
    "formal": "Formal. Complete sentences, conservative vocabulary, no contractions.",
    "friendly": "Warm but still professional. Contractions are fine; no slang.",
    "amigavel": "Warm but still professional. Contractions are fine; no slang.",
    "amigável": "Warm but still professional. Contractions are fine; no slang.",
    "enthusiastic": (
        "Energetic, but earn it with specifics rather than adjectives. No exclamation marks."
    ),
    "entusiasmado": (
        "Energetic, but earn it with specifics rather than adjectives. No exclamation marks."
    ),
    "concise": "Maximally economical. Short sentences, nothing decorative, stay above 150 words.",
    "conciso": "Maximally economical. Short sentences, nothing decorative, stay above 150 words.",
    "technical": (
        "Technical. Name the specific systems, tools, and scale the candidate worked with."
    ),
    "tecnico": (
        "Technical. Name the specific systems, tools, and scale the candidate worked with."
    ),
    "técnico": (
        "Technical. Name the specific systems, tools, and scale the candidate worked with."
    ),
}


def _tone_instruction(tone: str) -> str:
    cleaned = (tone or "").strip()
    if not cleaned:
        return _TONE_GUIDANCE["professional"]
    known = _TONE_GUIDANCE.get(cleaned.lower())
    if known:
        return known
    # The tone is a free-text setting; pass an unrecognized value straight through.
    return f"Match this tone: {cleaned}."


def _language_instruction(language: str) -> str:
    normalized = (language or "job").strip().lower()
    if normalized in {"", "job", "auto", "posting"}:
        return (
            "Write in the same language as the job description above. If the "
            "description mixes languages, use the one the requirements are written "
            "in. Report the language you chose in the `language` field."
        )
    return (
        f"Write in {language.strip()} regardless of the language of the job "
        f"description, and report `{language.strip()}` as the language."
    )


def build_cover_letter_prompt(
    profile: ProfileContext,
    job: JobLike,
    *,
    tone: str,
    language: str,
) -> str:
    """Render the cover-letter request.

    `language` is either `"job"` (mirror the posting) or an explicit locale such
    as `"pt-BR"` or `"en"`.
    """
    return (
        "Write a cover letter for this candidate applying to the job posting below.\n\n"
        "=== CANDIDATE ===\n"
        f"{render_profile_block(profile)}\n\n"
        "=== JOB POSTING ===\n"
        f"{render_job_block(job)}\n\n"
        "=== TONE ===\n"
        f"{_tone_instruction(tone)}\n\n"
        "=== LANGUAGE ===\n"
        f"{_language_instruction(language)}\n\n"
        "Use only evidence present in the candidate section. Leave out anything you "
        "cannot support from it."
    )


__all__ = ["COVER_LETTER_SYSTEM_PROMPT", "build_cover_letter_prompt"]
