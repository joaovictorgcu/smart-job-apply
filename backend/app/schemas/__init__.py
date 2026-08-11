"""Schemas de request/response da API."""

from app.schemas.application import (
    ApplicationDetail,
    ApplicationEventOut,
    ApplicationRead,
    ApplicationUpdate,
)
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.automation import (
    AutomationRunRead,
    PrepareRequest,
    PreviewResponse,
    SearchRunRequest,
    SubmitRequest,
)
from app.schemas.common import Message, Page
from app.schemas.job import JobDetail, JobRead, SearchCreate, SearchRead, SearchUpdate
from app.schemas.stats import DashboardStats
from app.schemas.user import (
    LinkedInAccountRead,
    ProfileRead,
    ProfileUpdate,
    UserRead,
    UserSettingsRead,
    UserSettingsUpdate,
)

__all__ = [
    "ApplicationDetail",
    "ApplicationEventOut",
    "ApplicationRead",
    "ApplicationUpdate",
    "AutomationRunRead",
    "DashboardStats",
    "JobDetail",
    "JobRead",
    "LinkedInAccountRead",
    "LoginRequest",
    "Message",
    "Page",
    "PrepareRequest",
    "PreviewResponse",
    "ProfileRead",
    "ProfileUpdate",
    "RegisterRequest",
    "SearchCreate",
    "SearchRead",
    "SearchRunRequest",
    "SearchUpdate",
    "SubmitRequest",
    "TokenResponse",
    "UserRead",
    "UserSettingsRead",
    "UserSettingsUpdate",
]
