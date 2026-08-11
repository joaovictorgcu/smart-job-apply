"""Liveness probe. The only unauthenticated endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the API is up, and which version is running."""
    return HealthResponse(status="ok", version=__version__)
