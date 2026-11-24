"""Mission-scoped WebSocket fan-out from the transactional outbox.

Protocol (JSON text frames):
  client -> {"type": "auth", "token": "<human access token>"}           (first frame, required)
  server -> {"type": "welcome", "mission_id", "last_sequence", "topics"}
  client -> {"type": "subscribe", "topics": [...], "after_sequence": n}  (replays backlog)
  server -> {"type": "event", "event": {...}}                           (ordered by sequence)
  server -> {"type": "heartbeat", "last_sequence": n}
  client -> {"type": "ping"}  /  server -> {"type": "pong"}
  server -> {"type": "resync_required", "last_delivered_sequence": n}   then close 4008

Tokens are never accepted in the URL. Delivery is at-least-once per connection; clients
de-duplicate by sequence and resynchronize from GET /missions/{id}/events after a gap.
"""

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select, update

from backend.core.config import BackendSettings
from backend.core.errors import AppError
from backend.core.permissions import Permission, Principal
from backend.database import models as m
from backend.database.session import Database
from backend.schemas import EventOut
from backend.services.auth import AuthService
from backend.services.events import ALL_TOPICS, TOPICS, EventType

log = logging.getLogger("backend.realtime")
BACKLOG_LIMIT = 1000

CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_SLOW = 4008
CLOSE_LIMIT = 4029
CLOSE_PROTOCOL = 4400


@dataclass(eq=False)
class Connection:
    websocket: WebSocket
    mission_id: UUID
    principal: Principal
    token: str
    queue: "asyncio.Queue[dict[str, Any]]"
    topics: set[str] = field(default_factory=lambda: set(ALL_TOPICS))
    cursor: int = 0
    closed: bool = False
    sent: int = 0


class Hub:
    def __init__(self, db: Database, settings: BackendSettings, auth: AuthService) -> None:
        self.db = db
        self.settings = settings
        self.auth = auth
        self.connections: dict[UUID, set[Connection]] = {}
        self.locks: dict[UUID, asyncio.Lock] = {}
        self.dispatched = 0
        self.dropped_slow = 0
        self.publish_failures = 0
        self.delivery_latency_ms: list[float] = []

    @property
    def count(self) -> int:
        return sum(len(c) for c in self.connections.values())

    def queue_depth(self) -> int:
        return sum(c.queue.qsize() for conns in self.connections.values() for c in conns)

    def _lock(self, mission_id: UUID) -> asyncio.Lock:
        return self.locks.setdefault(mission_id, asyncio.Lock())

    # ----- outbox dispatch -----------------------------------------------------------------
    def _fetch(self, mission_id: UUID, after: int | None) -> list[EventOut]:
        with self.db.read() as session:
            query = select(m.DomainEvent).where(m.DomainEvent.mission_id == mission_id)
            if after is None:
                query = query.where(m.DomainEvent.dispatched_at.is_(None))
            else:
                query = query.where(m.DomainEvent.sequence > after)
            rows = session.scalars(query.order_by(m.DomainEvent.sequence).limit(BACKLOG_LIMIT + 1))
            return [EventOut.model_validate(r) for r in rows]

    def _mark(self, mission_id: UUID, up_to: int) -> None:
        with self.db.transaction() as session:
            session.execute(
                update(m.DomainEvent)
                .where(
                    m.DomainEvent.mission_id == mission_id,
                    m.DomainEvent.sequence <= up_to,
                    m.DomainEvent.dispatched_at.is_(None),
                )
                .values(dispatched_at=datetime.now(UTC))
            )

    async def dispatch(self, mission_id: UUID) -> None:
        async with self._lock(mission_id):
            try:
                events = await asyncio.to_thread(self._fetch, mission_id, None)
            except AppError:
                self.publish_failures += 1
                return
            if not events:
                return
            for connection in list(self.connections.get(mission_id, ())):
                for event in events:
                    self._offer(connection, event)
            try:
                await asyncio.to_thread(self._mark, mission_id, events[-1].sequence)
                self.dispatched += len(events)
            except AppError:
                self.publish_failures += 1  # events stay undispatched and are retried

    def _offer(self, connection: Connection, event: EventOut) -> None:
        if connection.closed or event.sequence <= connection.cursor:
            return
        connection.cursor = event.sequence
        topic = TOPICS.get(EventType(event.event_type), "mission")
        if topic not in connection.topics:
            return
        frame = {"type": "event", "event": event.model_dump(mode="json")}
        try:
            connection.queue.put_nowait(frame)
        except asyncio.QueueFull:
            self._slow(connection)

    def _slow(self, connection: Connection) -> None:
        if connection.closed:
            return
        connection.closed = True
        self.dropped_slow += 1
        while not connection.queue.empty():
            connection.queue.get_nowait()
        connection.queue.put_nowait(
            {"type": "resync_required", "last_delivered_sequence": connection.cursor}
        )

    async def replay(self, connection: Connection, after: int) -> None:
        """Send events after `after` to one connection, serialized with live dispatch."""
        async with self._lock(connection.mission_id):
            events = await asyncio.to_thread(self._fetch, connection.mission_id, after)
            if len(events) > BACKLOG_LIMIT:
                self._slow(connection)
                return
            connection.cursor = after
            for event in events:
                self._offer(connection, event)

    # ----- connection handling -------------------------------------------------------------
    def _authorize(self, token: str, mission_id: UUID) -> Principal:
        with self.db.read() as session:
            principal = self.auth.principal_for_human(session, token)
            if not principal.can(Permission.MISSION_READ, mission_id):
                raise PermissionError("mission not visible")
            if session.get(m.Mission, mission_id) is None:
                raise PermissionError("mission not found")
            return principal

    def _last_sequence(self, mission_id: UUID) -> int:
        with self.db.read() as session:
            state = session.get(m.MissionRuntime, mission_id)
            return state.last_event_sequence if state else 0

    async def serve(self, websocket: WebSocket, mission_id: UUID) -> None:
        await websocket.accept()
        if self.count >= self.settings.websocket_max_connections:
            await websocket.close(CLOSE_LIMIT, "connection limit reached")
            return
        try:
            first = await asyncio.wait_for(
                websocket.receive_json(), timeout=self.settings.websocket_auth_timeout_seconds
            )
        except (TimeoutError, WebSocketDisconnect, json.JSONDecodeError, KeyError, ValueError):
            with contextlib.suppress(Exception):
                await websocket.close(CLOSE_UNAUTHENTICATED, "authentication required")
            return
        token = (
            first.get("token") if isinstance(first, dict) and first.get("type") == "auth" else None
        )
        if not isinstance(token, str):
            await websocket.close(CLOSE_UNAUTHENTICATED, "authentication required")
            return
        try:
            principal = await asyncio.to_thread(self._authorize, token, mission_id)
        except AppError:
            await websocket.close(CLOSE_UNAUTHENTICATED, "invalid token")
            return
        except PermissionError:
            await websocket.close(CLOSE_FORBIDDEN, "mission not available")
            return
        connection = Connection(
            websocket,
            mission_id,
            principal,
            token,
            asyncio.Queue(maxsize=self.settings.websocket_queue_size),
        )
        last = await asyncio.to_thread(self._last_sequence, mission_id)
        connection.cursor = last
        self.connections.setdefault(mission_id, set()).add(connection)
        await websocket.send_json(
            {
                "type": "welcome",
                "mission_id": str(mission_id),
                "last_sequence": last,
                "topics": sorted(connection.topics),
                "heartbeat_seconds": self.settings.websocket_heartbeat_seconds,
            }
        )
        sender = asyncio.create_task(self._send_loop(connection))
        heartbeat = asyncio.create_task(self._heartbeat_loop(connection))
        try:
            await self._receive_loop(connection)
        finally:
            connection.closed = True
            self.connections.get(mission_id, set()).discard(connection)
            for task in (sender, heartbeat):
                task.cancel()
            await asyncio.gather(sender, heartbeat, return_exceptions=True)
            with contextlib.suppress(Exception):
                await websocket.close()

    async def _receive_loop(self, connection: Connection) -> None:
        ws = connection.websocket
        while not connection.closed:
            try:
                message = await ws.receive_json()
            except WebSocketDisconnect:
                return
            except (json.JSONDecodeError, ValueError, KeyError):
                await ws.close(CLOSE_PROTOCOL, "invalid frame")
                return
            if not isinstance(message, dict):
                await ws.close(CLOSE_PROTOCOL, "invalid frame")
                return
            kind = message.get("type")
            if kind == "ping":
                await self._enqueue_control(connection, {"type": "pong"})
            elif kind == "subscribe":
                topics = message.get("topics", sorted(ALL_TOPICS))
                after = message.get("after_sequence")
                if not isinstance(topics, list) or not set(topics) <= ALL_TOPICS:
                    await self._enqueue_control(
                        connection,
                        {"type": "error", "code": "invalid_topics", "allowed": sorted(ALL_TOPICS)},
                    )
                    continue
                connection.topics = set(topics)
                if isinstance(after, int) and after >= 0:
                    await self.replay(connection, after)
                await self._enqueue_control(
                    connection, {"type": "subscribed", "topics": sorted(connection.topics)}
                )
            else:
                await self._enqueue_control(connection, {"type": "error", "code": "unknown_type"})

    async def _enqueue_control(self, connection: Connection, frame: dict[str, Any]) -> None:
        try:
            connection.queue.put_nowait(frame)
        except asyncio.QueueFull:
            self._slow(connection)

    async def _send_loop(self, connection: Connection) -> None:
        ws = connection.websocket
        try:
            while True:
                frame = await connection.queue.get()
                await ws.send_json(frame)
                connection.sent += 1
                if frame.get("type") == "resync_required":
                    await ws.close(CLOSE_SLOW, "client too slow; resynchronize")
                    return
                if frame.get("type") == "event":
                    occurred = datetime.fromisoformat(frame["event"]["occurred_at"])
                    latency = (datetime.now(UTC) - occurred).total_seconds() * 1000
                    self.delivery_latency_ms = [*self.delivery_latency_ms[-999:], latency]
        except (WebSocketDisconnect, RuntimeError):
            connection.closed = True

    async def _heartbeat_loop(self, connection: Connection) -> None:
        while not connection.closed:
            await asyncio.sleep(self.settings.websocket_heartbeat_seconds)
            try:
                await asyncio.to_thread(self._authorize, connection.token, connection.mission_id)
            except (AppError, PermissionError):
                # Token expired, account disabled or membership revoked: stop streaming.
                connection.closed = True
                with contextlib.suppress(Exception):
                    await connection.websocket.close(CLOSE_FORBIDDEN, "authorization expired")
                return
            await self._enqueue_control(
                connection, {"type": "heartbeat", "last_sequence": connection.cursor}
            )

    async def close_all(self) -> None:
        for conns in list(self.connections.values()):
            for connection in list(conns):
                connection.closed = True
                with contextlib.suppress(Exception):
                    await connection.websocket.close(1001, "server shutdown")
