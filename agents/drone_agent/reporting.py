from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from communication.messages import Envelope, Payload


class Mailbox:
    """Per-agent, bounded mock outbox. Sender authentication belongs to the fixture."""

    def __init__(
        self,
        owner: str,
        mission: UUID,
        capacity: int,
        *,
        send: Callable[[bytes], bool] | None = None,
    ):
        self.send = send
        self.owner = owner
        self.mission = mission
        self.session = uuid5(mission, owner)
        self.sent: deque[Envelope] = deque(maxlen=capacity)
        self.sequence: dict[str, int] = {}
        self.online = True

    def publish(
        self,
        payload: Payload,
        now: int,
        destination: str = "command",
        *,
        expires_ms: int | None = None,
    ) -> None:
        seq = self.sequence.get(destination, 0)
        key = uuid5(self.session, f"{destination}/{seq}")
        msg = Envelope(
            schema_version="1.2"
            if payload.message_type
            in ("forwarded_report", "human_incident_review", "command_alert")
            else "1.1"
            if payload.message_type == "mission_update"
            else "1.0",
            message_id=key,
            mission_id=self.mission,
            source=self.owner,
            destination=destination,
            session_id=self.session,
            timestamp=datetime(2000, 1, 1, tzinfo=UTC) + timedelta(milliseconds=now),
            sequence=seq,
            sent_ms=now,
            priority="routine",
            correlation_id=payload.acknowledged_id
            if payload.message_type == "acknowledgement"
            else key,
            payload=payload,
            expires_ms=expires_ms,
        )
        self.sent.append(msg)
        if self.send:
            self.send(msg.model_dump_json().encode())
        self.sequence[destination] = seq + 1
