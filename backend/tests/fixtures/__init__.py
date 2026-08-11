"""Test doubles and object factories."""

from tests.fixtures.factories import (
    DEFAULT_PASSWORD,
    create_analysis,
    create_application,
    create_job,
    create_run,
    create_search,
    create_user,
    make_form_question,
    make_job_posting,
    make_profile_context,
)
from tests.fixtures.fake_ai import FakeAIClient, FakeAIError
from tests.fixtures.fake_linkedin import FakeLinkedInService, FakePage, make_postings

__all__ = [
    "DEFAULT_PASSWORD",
    "FakeAIClient",
    "FakeAIError",
    "FakeLinkedInService",
    "FakePage",
    "create_analysis",
    "create_application",
    "create_job",
    "create_run",
    "create_search",
    "create_user",
    "make_form_question",
    "make_job_posting",
    "make_postings",
    "make_profile_context",
]
