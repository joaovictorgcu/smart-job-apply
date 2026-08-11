"""Schemas utilitários."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base para schemas lidos diretamente de modelos ORM."""

    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


class Page(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
