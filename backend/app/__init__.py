"""LinkedIn Auto Apply backend.

Assisted-mode job application helper: it searches, scores with AI and fills the
LinkedIn Easy Apply form, then stops for explicit human approval before any
submission.
"""

__all__ = ["__version__"]

# Keep in sync with [project].version in pyproject.toml. Served by GET /api/health.
__version__ = "0.1.0"
