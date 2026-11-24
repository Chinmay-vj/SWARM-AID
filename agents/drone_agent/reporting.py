from collections import deque
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from communication.messages import Envelope, Payload


class Mailbox:
    """Per-agent, bounded mock outbox. Sender authentication belongs to the fixture."""

    def __init__(self, owner: str, mission: UUID, capacity: int):
        self.owner = owner
        self.mission = mission
        self.session = uuid5(mission, owner)
        self.sent: deque[Envelope] = deque(maxlen=capacity)
        self.sequence: dict[str, int] = {}
        self.online = True

    def publish(self, payload: Payload, now: int, destination: str = "command") -> None:
        seq = self.sequence.get(destination, 0)
        key = uuid5(self.session, f"{destination}/{seq}")
        msg = Envelope(
            schema_version="1.0",
            message_id=key,
            mission_id=self.mission,
            source=self.owner,
            destination=destination,
            session_id=self.session,
            timestamp=datetime(2000, 1, 1, tzinfo=UTC) + timedelta(milliseconds=now),
            sequence=seq,
            sent_ms=now,
            priority="routine",
            correlation_id=key,
            payload=payload,
        )
        self.sent.append(msg)
        self.sequence[destination] = seq + 1
