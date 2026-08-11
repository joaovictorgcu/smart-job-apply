"""Per-user event broadcasting over WebSocket.

Per-user isolation is mandatory: one user must never see another user's activity.
Publishing never raises — the automation must not break just because a dashboard
tab was closed.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Iterable

from fastapi import WebSocket

from app.observability.events import Event
from app.observability.logger import get_logger

logger = get_logger(__name__)

# Latest events per user, so the dashboard can rebuild the feed on (re)connect.
_HISTORY_LIMIT = 200


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._history: dict[int, list[Event]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[user_id].add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                self._connections.pop(user_id, None)

    def history(self, user_id: int) -> list[Event]:
        return list(self._history.get(user_id, []))

    async def publish(self, user_id: int, event: Event) -> None:
        """Send to every open tab of the user; send failures are ignored."""
        self._remember(user_id, event)
        payload = event.model_dump(mode="json")

        async with self._lock:
            targets: Iterable[WebSocket] = list(self._connections.get(user_id, ()))

        dead: list[WebSocket] = []
        for connection in targets:
            try:
                await connection.send_json(payload)
            except Exception:  # the connection dropped mid-send
                dead.append(connection)

        for connection in dead:
            await self.disconnect(user_id, connection)

    def _remember(self, user_id: int, event: Event) -> None:
        history = self._history[user_id]
        history.append(event)
        if len(history) > _HISTORY_LIMIT:
            del history[:-_HISTORY_LIMIT]

    def connection_count(self, user_id: int) -> int:
        return len(self._connections.get(user_id, ()))


manager = ConnectionManager()
