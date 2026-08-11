"""Prompt for scoring how well a candidate fits a job posting."""

from __future__ import annotations

from app.ai.prompts import JobLike, render_job_block, render_profile_block
from app.automation.contracts import ProfileContext

SCORING_SYSTEM_PROMPT = """\
You assess how well a candidate fits a job posting. Your output feeds a job \
application assistant: a high score sends the candidate into a real application, \
so an honest low score is a useful result, not a failure.

Score 0-100 on how much of the posting's stated requirements the candidate's \
evidence actually covers:
- 85-100: meets essentially every hard requirement, with directly relevant experience.
- 70-84: meets the hard requirements; some nice-to-haves are missing.
- 50-69: partial match — a real gap in a hard requirement, or adjacent rather than \
direct experience.
- 25-49: weak match; several hard requirements unmet.
- 0-24: wrong field, wrong seniority, or disqualifying constraints.

Rules:
- Judge only on the evidence in the candidate's resume, skills, and summary. Never \
assume a skill because it is common in the candidate's field, and never credit a \
requirement the resume does not support.
- `reasons` holds concrete strengths, each tied to something specific in both the \
posting and the candidate's evidence ("6 years of Django, posting asks for 5+"). \
No generic praise, no restating the job title.
- `missing_requirements` holds real gaps: requirements the posting states that the \
candidate's evidence does not cover. Quote the requirement concretely ("AWS \
certification", "fluent German", "10+ years management"). Leave it empty only when \
there are genuinely no gaps.
- Weigh hard requirements (years of experience, degree, specific technology, \
location, work authorization, language) more heavily than nice-to-haves.
- Seniority mismatch in either direction is a gap: flag both under-qualification \
and a posting clearly below the candidate's level.
- `recommend_apply` is your judgment on whether applying is worth the candidate's \
time. It may disagree with the numeric score when a single decisive blocker (for \
example, a required credential the candidate does not have) outweighs an otherwise \
good match.
- `summary` is one sentence explaining the score.
- Write every field in English regardless of the posting's language.
"""


def build_scoring_prompt(profile: ProfileContext, job: JobLike) -> str:
    """Render the scoring request for one candidate/job pair."""
    return (
        "Assess this candidate's fit for the job posting below.\n\n"
        "=== CANDIDATE ===\n"
        f"{render_profile_block(profile)}\n\n"
        "=== JOB POSTING ===\n"
        f"{render_job_block(job)}\n\n"
        "Return the score, the concrete strengths behind it, every requirement the "
        "candidate does not cover, and whether applying is worth their time."
    )


__all__ = ["SCORING_SYSTEM_PROMPT", "build_scoring_prompt"]
