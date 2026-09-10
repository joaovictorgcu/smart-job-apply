"""What kind of vacancy the account is looking for.

Validated against the vocabularies the portal filters already speak, so a
preference maps onto a search with no translation table and a typo is caught
here rather than silently producing a query that matches nothing.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.domain.preferences import SENIORITY_VALUES, WORK_MODELS
from app.schemas.common import ORMModel

MAX_ROLES = 5
MAX_TERMS = 40


def _clean(values: list[str] | None) -> list[str]:
    """Trim, drop blanks, and collapse repeats keeping the first spelling."""
    seen: dict[str, str] = {}
    for value in values or []:
        cleaned = value.strip()
        if cleaned:
            seen.setdefault(cleaned.casefold(), cleaned)
    return list(seen.values())


class JobPreferencesRead(ORMModel):
    target_role: str | None = None
    alternative_roles: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    work_models: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    salary_currency: str = "BRL"
    priority_technologies: list[str] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class JobPreferencesUpdate(BaseModel):
    """Partial update. Only the fields present in the body are touched."""

    target_role: str | None = Field(default=None, max_length=200)
    alternative_roles: list[str] | None = Field(default=None, max_length=MAX_ROLES)
    seniority: list[str] | None = None
    work_models: list[str] | None = None
    locations: list[str] | None = Field(default=None, max_length=MAX_ROLES)
    # A floor, in whole currency units. The ceiling keeps a mistyped "1200000"
    # from silently excluding every posting the user can see.
    salary_min: int | None = Field(default=None, ge=0, le=10_000_000)
    salary_currency: str | None = Field(default=None, max_length=10)
    priority_technologies: list[str] | None = Field(default=None, max_length=MAX_TERMS)
    excluded_terms: list[str] | None = Field(default=None, max_length=MAX_TERMS)

    @field_validator("alternative_roles", "locations", "priority_technologies", "excluded_terms")
    @classmethod
    def _tidy(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _clean(value)

    @field_validator("seniority")
    @classmethod
    def _known_seniority(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = _clean(value)
        unknown = [item for item in cleaned if item not in SENIORITY_VALUES]
        if unknown:
            raise ValueError(
                f"Unknown seniority {unknown}. Use one of: {', '.join(SENIORITY_VALUES)}."
            )
        return cleaned

    @field_validator("work_models")
    @classmethod
    def _known_work_models(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = _clean(value)
        unknown = [item for item in cleaned if item not in WORK_MODELS]
        if unknown:
            raise ValueError(
                f"Unknown work model {unknown}. Use one of: {', '.join(WORK_MODELS)}."
            )
        return cleaned
