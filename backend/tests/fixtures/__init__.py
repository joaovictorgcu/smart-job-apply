"""Test doubles and object factories."""

from tests.fixtures.factories import (
    DEFAULT_PASSWORD,
    create_analysis,
    create_application,
    create_job,
    create_run,
    create_search,
    create_user,
    days_ago,
    make_form_question,
    make_job_posting,
    make_profile_context,
)
from tests.fixtures.fake_ai import FakeAIClient
from tests.fixtures.fake_linkedin import (
    CHECKPOINT_MARKERS,
    CHECKPOINT_URL,
    FakeLinkedInService,
    FakePage,
    make_postings,
)

__all__ = [
    "CHECKPOINT_MARKERS",
    "CHECKPOINT_URL",
    "DEFAULT_PASSWORD",
    "FakeAIClient",
    "FakeLinkedInService",
    "FakePage",
    "create_analysis",
    "create_application",
    "create_job",
    "create_run",
    "create_search",
    "create_user",
    "days_ago",
    "make_form_question",
    "make_job_posting",
    "make_postings",
    "make_profile_context",
]
