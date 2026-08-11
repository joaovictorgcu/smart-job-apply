"""Broadcast de eventos por usuário via WebSocket.

Isolamento por usuário é obrigatório: um usuário nunca deve ver a atividade de
outro. Publicar nunca levanta exceção — a automação não pode quebrar porque uma
aba do painel fechou.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Iterable

from fastapi import WebSocket

from app.observability.events import Event
from app.observability.logger import get_logger

logger = get_logger(__name__)

# Últimos eventos por usuário, para o painel reconstruir o feed ao (re)conectar.
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
        """Envia para todas as abas abertas do usuário; ignora falhas de envio."""
        self._remember(user_id, event)
        payload = event.model_dump(mode="json")

        async with self._lock:
            targets: Iterable[WebSocket] = list(self._connections.get(user_id, ()))

        dead: list[WebSocket] = []
        for connection in targets:
            try:
                await connection.send_json(payload)
            except Exception:  # conexão caiu no meio do envio
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
