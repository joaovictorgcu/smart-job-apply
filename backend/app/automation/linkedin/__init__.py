"""LinkedIn page objects and the service facade built on top of them."""

from app.automation.linkedin.apply import EasyApplyModal
from app.automation.linkedin.job import JobDetailPage
from app.automation.linkedin.search import JobSearchPage
from app.automation.linkedin.service import LinkedInBrowserService

__all__ = [
    "EasyApplyModal",
    "JobDetailPage",
    "JobSearchPage",
    "LinkedInBrowserService",
]
