"""Re-export of the fake portal, which lives in the app package.

It moved to `app.automation.demo_portal` so the *running* application can serve
it too (`DEMO_PORTAL=true`), not just the tests. Keeping this module means the
browser tests import it by the name they always used, and it stays obvious where
the tests' fake site comes from.
"""

from __future__ import annotations

from app.automation.demo_portal import (
    CHECKPOINT_PATH,
    RECORD_SUBMIT_PATH,
    FakePortal,
    PortalField,
    PortalJob,
    PortalStep,
    default_steps,
    install,
    make_jobs,
    multi_step_steps,
    render_job_page,
)

__all__ = [
    "CHECKPOINT_PATH",
    "RECORD_SUBMIT_PATH",
    "FakePortal",
    "PortalField",
    "PortalJob",
    "PortalStep",
    "default_steps",
    "install",
    "make_jobs",
    "multi_step_steps",
    "render_job_page",
]
