"""Live event feed: one WebSocket per dashboard tab."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.deps import get_current_user_ws
from app.observability import EventName, get_logger, make_event
from app.websocket.manager import manager

logger = get_logger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def event_feed(
    websocket: WebSocket,
    token: Annotated[str | None, Query(description="JWT issued by /api/auth/login.")] = None,
) -> None:
    """Stream `Event` objects for the authenticated user.

    The token travels as a query parameter because browsers cannot set headers on a
    WebSocket handshake. On connect the recent history is replayed so a reloaded
    dashboard rebuilds its feed. Inbound messages are treated as keep-alive pings.
    """
    user = await get_current_user_ws(websocket, token)
    if user is None:
        return

    await manager.connect(user.id, websocket)
    try:
        for event in manager.history(user.id):
            await websocket.send_json(event.model_dump(mode="json"))
        await websocket.send_json(
            make_event(
                EventName.LOG, message="Connected to the live event feed.", level="info"
            ).model_dump(mode="json")
        )
        while True:
            # Keeps the socket open; the payload itself carries no commands.
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(
            "WebSocket closed.", extra={"action": "ws.disconnect", "user_id": user.id}
        )
    finally:
        await manager.disconnect(user.id, websocket)
