"""Saved job searches."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.job import SearchCreate, SearchRead, SearchUpdate
from app.services import search_service

router = APIRouter(prefix="/searches", tags=["searches"])


@router.get("", response_model=list[SearchRead])
async def list_searches(user: CurrentUser, session: SessionDep) -> list[SearchRead]:
    """List this account's saved searches, newest first."""
    searches = await search_service.list_searches(session, user)
    return [SearchRead.model_validate(search) for search in searches]


@router.post("", response_model=SearchRead, status_code=status.HTTP_201_CREATED)
async def create_search(
    payload: SearchCreate, user: CurrentUser, session: SessionDep
) -> SearchRead:
    """Save a set of filters so it can be run again later."""
    search = await search_service.create_search(session, user, payload)
    return SearchRead.model_validate(search)


@router.patch("/{search_id}", response_model=SearchRead)
async def update_search(
    search_id: int, payload: SearchUpdate, user: CurrentUser, session: SessionDep
) -> SearchRead:
    """Update a saved search. Only the fields present in the body change."""
    search = await search_service.update_search(session, user, search_id, payload)
    return SearchRead.model_validate(search)


@router.delete("/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search(search_id: int, user: CurrentUser, session: SessionDep) -> Response:
    """Delete a saved search. Jobs already found keep their history."""
    await search_service.delete_search(session, user, search_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
