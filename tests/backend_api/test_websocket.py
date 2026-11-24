"""Mission-scoped WebSocket delivery: authentication, isolation, ordering, replay, heartbeats."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from backend_support import Api
from starlette.websockets import WebSocketDisconnect

from backend.core.permissions import GlobalRole, Principal
from backend.realtime.hub import CLOSE_FORBIDDEN, CLOSE_UNAUTHENTICATED, Connection, Hub
from backend.schemas import EventOut


def receive_until(ws: Any, predicate: Any, limit: int = 2000) -> list[dict[str, Any]]:
    frames = []
    for _ in range(limit):
        frame = ws.receive_json()
        frames.append(frame)
        if predicate(frame):
            return frames
    raise AssertionError("expected frame not received")


def test_unauthenticated_and_unauthorized_connections_are_closed(
    api: Api, coordinator: str
) -> None:
    mission = api.mission(coordinator)
    path = f"/ws/v1/missions/{mission['id']}"
    with api.client.websocket_connect(path) as ws:
        ws.send_json({"type": "subscribe"})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == CLOSE_UNAUTHENTICATED
    with api.client.websocket_connect(path) as ws:
        ws.send_json({"type": "auth", "token": "forged"})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == CLOSE_UNAUTHENTICATED
    api.user("stranger", GlobalRole.COORDINATOR)
    api.login("stranger")
    with api.client.websocket_connect(path) as ws:
        ws.send_json({"type": "auth", "token": api.tokens["stranger"]})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == CLOSE_FORBIDDEN
    with api.client.websocket_connect(f"/ws/v1/missions/{uuid4()}") as ws:
        ws.send_json({"type": "auth", "token": api.tokens[coordinator]})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == CLOSE_FORBIDDEN


def test_live_delivery_ordering_isolation_and_replay(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator)
    other = api.mission(coordinator)
    with api.client.websocket_connect(f"/ws/v1/missions/{mission['id']}") as ws:
        ws.send_json({"type": "auth", "token": api.tokens[coordinator]})
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome" and welcome["last_sequence"] == 1
        # Run the other mission first: none of its events may arrive here.
        assert api.post(f"/api/v1/missions/{other['id']}/start", coordinator).status_code == 200
        api.wait_status(other["id"], coordinator, {"completed"})
        assert api.post(f"/api/v1/missions/{mission['id']}/start", coordinator).status_code == 200
        frames = receive_until(
            ws,
            lambda f: f.get("type") == "event" and f["event"]["event_type"] == "MISSION_COMPLETED",
        )
        events = [f["event"] for f in frames if f["type"] == "event"]
        assert {e["mission_id"] for e in events} == {mission["id"]}
        sequences = [e["sequence"] for e in events]
        assert sequences == sorted(sequences) and len(set(sequences)) == len(sequences)
        assert sequences[0] == 2  # nothing skipped after the welcome cursor
        kinds = {e["event_type"] for e in events}
        assert {
            "MISSION_STARTED",
            "AGENT_REGISTERED",
            "INCIDENT_CREATED",
            "HUMAN_REVIEW_REQUESTED",
        } <= kinds
        # Topic filter plus replay from the start of the mission.
        ws.send_json({"type": "subscribe", "topics": ["mission"], "after_sequence": 0})
        replay = receive_until(ws, lambda f: f.get("type") == "subscribed")
        replayed = [f["event"] for f in replay if f["type"] == "event"]
        assert next(e["event_type"] for e in replayed) == "MISSION_CREATED"
        assert {e["event_type"] for e in replayed} <= {
            "MISSION_CREATED",
            "MISSION_STARTED",
            "MISSION_COMPLETED",
            "MISSION_PAUSED",
            "MISSION_RESUMED",
            "MISSION_STOPPED",
        }
        ws.send_json({"type": "subscribe", "topics": ["nope"]})
        error = receive_until(ws, lambda f: f.get("type") == "error")
        assert error[-1]["code"] == "invalid_topics"
        ws.send_json({"type": "ping"})
        assert receive_until(ws, lambda f: f.get("type") == "pong")
        heartbeat = receive_until(ws, lambda f: f.get("type") == "heartbeat")
        assert heartbeat[-1]["last_sequence"] >= sequences[-1]
    # Reconnection: REST replay returns the same events by sequence.
    rest = api.get(
        f"/api/v1/missions/{mission['id']}/events",
        coordinator,
        params={"after_sequence": 1, "limit": 1000},
    ).json()
    assert [e["sequence"] for e in rest][: len(sequences)] == sequences


def test_slow_client_is_cut_off_with_resync_instruction() -> None:
    class FakeSocket:
        pass

    hub = Hub.__new__(Hub)
    hub.dropped_slow = 0
    principal = Principal("p", "human")
    mission = uuid4()
    connection = Connection(FakeSocket(), mission, principal, "t", asyncio.Queue(maxsize=2))  # type: ignore[arg-type]

    def event(sequence: int) -> EventOut:
        return EventOut(
            id=uuid4(),
            mission_id=mission,
            sequence=sequence,
            event_type="INCIDENT_UPDATED",
            schema_version="1",
            source="model2",
            occurred_at=datetime.now(UTC),
            sim_time_ms=0,
            correlation_id="c",
            resource_type="incident",
            resource_id="x",
            payload={},
        )

    for sequence in range(1, 6):
        hub._offer(connection, event(sequence))
    assert connection.closed and hub.dropped_slow == 1
    frames = [connection.queue.get_nowait() for _ in range(connection.queue.qsize())]
    assert frames == [{"type": "resync_required", "last_delivered_sequence": 3}]
    hub._offer(connection, event(9))  # closed connections receive nothing further
    assert connection.queue.empty()
