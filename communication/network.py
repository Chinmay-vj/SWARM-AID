from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from math import ceil
from random import Random
from statistics import mean, median
from uuid import UUID

from pydantic import Field, NonNegativeInt, PositiveInt, ValidationError

from agents.shared.domain import Record, Score
from communication.messages import Envelope


class Conditions(Record):
    capacity: PositiveInt = 128
    max_bytes: PositiveInt = 65536
    control_retries: NonNegativeInt = 2
    duplicate: Score = 0
    jitter: NonNegativeInt = 0
    retention_ms: PositiveInt = 3000
    heartbeat_ms: PositiveInt = 1500
    server_down: tuple[int, ...] = ()
    endpoint_down: dict[str, tuple[int, ...]] = Field(default_factory=dict)


class State(StrEnum):
    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    UNAVAILABLE = "unavailable"


REPORTS = {"environmental_observation", "hazard_detection", "possible_human_detection"}
PERMISSIONS = {
    ("drone", "drone"): REPORTS | {"agent_health", "heartbeat"},
    ("drone", "command"): REPORTS
    | {
        "registration",
        "heartbeat",
        "agent_health",
        "task_status",
        "evidence_reference",
        "error_report",
        "connection_loss",
        "reconnection",
    },
    ("drone", "human"): {"evidence_reference"},
    ("command", "drone"): {"acknowledgement", "mission_instruction", "error_report"},
    ("command", "human"): {
        "incident_update",
        "mission_update",
        "evidence_reference",
        "heartbeat",
        "acknowledgement",
        "error_report",
    },
    ("human", "command"): {"human_approval", "human_override", "acknowledgement"},
    ("human", "drone"): {"human_override"},
}


@dataclass
class Endpoint:
    name: str
    role: str
    mission: UUID
    session: UUID
    registered: int
    heartbeat: int
    state: State = State.CONNECTED
    lost_at: int | None = None
    inbox: deque[Envelope] = field(default_factory=deque)


@dataclass(frozen=True)
class Attempt:
    due: int
    end: int
    source: str
    recipient: str
    session: UUID
    raw: bytes


class Router:
    def __init__(
        self,
        mission: UUID,
        conditions: Conditions,
        seed: int,
        delay_ms: int,
        loss: float,
        jitter_unit: int = 1,
    ):
        self.mission = mission
        self.config = conditions
        self.seed = seed
        self.delay = delay_ms
        self.loss = loss
        self.unit = jitter_unit
        self.now = 0
        self.endpoints: dict[str, Endpoint] = {}
        self.sessions: set[UUID] = set()
        self.pending: list[Attempt] = []
        self.events: list[dict[str, object]] = []
        self.receipts: set[tuple[str, UUID]] = set()
        self.originals: dict[UUID, tuple[str, bytes]] = {}
        self.heartbeat_ids: dict[UUID, int] = {}
        self.confirmed_contact: dict[str, int] = {}
        self.recipient_sessions: dict[UUID, tuple[tuple[str, UUID], ...]] = {}
        self.acks: set[tuple[str, UUID]] = set()
        self.latencies: list[int] = []
        self.recoveries: list[int] = []
        self.connected_samples = self.samples = 0
        self.link: Callable[[str, str], bool] = lambda a, b: True

    def register(self, name: str, role: str, session: UUID) -> Endpoint:
        if (
            session in self.sessions
            or name in self.endpoints
            or role not in {"drone", "command", "human"}
            or name in ("peers", "human_review")
        ):
            raise ValueError("invalid or duplicate endpoint")
        ep = Endpoint(name, role, self.mission, session, self.now, self.now)
        self.confirmed_contact[name] = self.now
        self.sessions.add(session)
        self.endpoints[name] = ep
        self.event("registered", name)
        return ep

    def deregister(self, name: str) -> None:
        endpoint = self.endpoints.pop(name)
        while endpoint.inbox:
            msg = endpoint.inbox.popleft()
            self.event("dropped", msg.source, name, msg.message_id, "closed unread inbox")
        self.event("deregistered", name)

    def event(
        self,
        kind: str,
        source: str = "",
        recipient: str = "",
        mid: UUID | None = None,
        reason: str = "",
        size: int = 0,
    ) -> None:
        self.events.append(
            {
                "time_ms": self.now,
                "mission": str(self.mission),
                "sender": source,
                "recipient": recipient,
                "message_id": str(mid) if mid else None,
                "event": kind,
                "reason": reason,
                "bytes": size,
            }
        )

    def availability(self, name: str, available: bool) -> None:
        ep = self.endpoints[name]
        if not available and ep.state != State.DISCONNECTED:
            ep.state = State.DISCONNECTED
            ep.lost_at = self.now
            self.event("connection_lost", name)
        elif available and ep.state == State.DISCONNECTED:
            ep.state = State.RECONNECTING
            self.event("reconnecting", name)
            self.recoveries.append(self.now - (ep.lost_at if ep.lost_at is not None else self.now))
            ep.state = State.CONNECTED
            ep.heartbeat = self.now
            self.event("connection_restored", name)
        self.samples += 1
        self.connected_samples += int(available)

    def submit(self, principal: str, raw: bytes) -> bool:
        if len(raw) > self.config.max_bytes:
            self.event("generated", principal)
            self.event("rejected", principal, reason="size")
            return False
        try:
            msg = Envelope.model_validate_json(raw)
        except ValidationError:
            self.event("generated", principal)
            self.event("rejected", principal, reason="invalid_schema")
            return False
        ep = self.endpoints.get(principal)
        mid = msg.message_id
        self.event("generated", principal, msg.destination, mid)
        if (
            not ep
            or (msg.source, msg.mission_id, msg.session_id) != (principal, self.mission, ep.session)
            or msg.sent_ms > self.now
        ):
            self.event("rejected", principal, msg.destination, mid, "identity_scope_time")
            return False
        if msg.payload.message_type == "registration" and msg.payload.role != ep.role:
            self.event("rejected", principal, msg.destination, mid, "role mismatch")
            return False
        digest = sha256(raw).digest()
        if self.originals.get(mid, (principal, digest)) != (principal, digest):
            self.event("rejected", principal, msg.destination, mid, "id_conflict")
            return False
        recipients = (
            [
                p
                for p in self.endpoints.values()
                if p.role == "drone" and p.name != principal and self.link(principal, p.name)
            ]
            if msg.destination == "peers"
            else [p for p in self.endpoints.values() if p.role == "human"]
            if msg.destination == "human_review"
            else [self.endpoints[msg.destination]]
            if msg.destination in self.endpoints
            else []
        )
        if mid in self.recipient_sessions:
            recipients = [
                self.endpoints[n]
                for n, session in self.recipient_sessions[mid]
                if n in self.endpoints and self.endpoints[n].session == session
            ]
        if msg.destination == "peers" and (
            ep.role != "drone" or msg.payload.message_type not in PERMISSIONS["drone", "drone"]
        ):
            self.event("rejected", principal, msg.destination, mid, "unauthorized_group")
            return False
        if not recipients:
            self.event(
                "no_members" if msg.destination == "peers" else "rejected",
                principal,
                msg.destination,
                mid,
                "empty destination",
            )
            return False
        for p in recipients:
            if msg.payload.message_type not in PERMISSIONS.get((ep.role, p.role), set()):
                self.event("rejected", principal, p.name, mid, "unauthorized_category")
                return False
        if (
            msg.expires_ms is not None
            and self.now >= msg.expires_ms
            and not any((p.name, mid) in self.receipts for p in recipients)
        ):
            self.event("expired", principal, msg.destination, mid)
            return False
        self.recipient_sessions.setdefault(mid, tuple((p.name, p.session) for p in recipients))
        if msg.payload.message_type == "heartbeat" and msg.destination == "command":
            self.heartbeat_ids[mid] = msg.sent_ms
        self.originals[mid] = (principal, digest)
        self.event("validated", principal, msg.destination, mid)
        for p in recipients:
            self.event("intended", principal, p.name, mid)
            if (p.name, mid) in self.receipts:
                self.event("duplicate", principal, p.name, mid)
                continue
            if msg.expires_ms is not None and self.now >= msg.expires_ms:
                self.event("expired", principal, p.name, mid)
                continue
            rng = Random(f"{self.seed}/{mid}/{p.name}/{self.now}")
            for _ in range(1 + int(rng.random() < self.config.duplicate)):
                if sum(a.source == principal for a in self.pending) >= self.config.capacity:
                    self.event("overflow", principal, p.name, mid, "outbound")
                    break
                self.event("transmitted", principal, p.name, mid, size=len(raw))
                retry = 0
                reliable = msg.payload.message_type in {
                    "registration",
                    "mission_instruction",
                    "human_override",
                    "human_approval",
                }
                while rng.random() < self.loss:
                    self.event("dropped", principal, p.name, mid, "packet_loss")
                    if not reliable or retry >= self.config.control_retries:
                        break
                    retry += 1
                    self.event("retry", principal, p.name, mid, "simulated retransmission")
                    self.event("transmitted", principal, p.name, mid, size=len(raw))
                else:
                    deadline = min(
                        msg.sent_ms + self.config.retention_ms,
                        msg.expires_ms
                        if msg.expires_ms is not None
                        else msg.sent_ms + self.config.retention_ms,
                    )
                    self.pending.append(
                        Attempt(
                            self.now
                            + self.delay * (1 + retry)
                            + self.unit * rng.randint(0, self.config.jitter),
                            deadline,
                            principal,
                            p.name,
                            p.session,
                            raw,
                        )
                    )

        return True

    def advance(self, now: int) -> None:
        if now < self.now:
            raise ValueError("clock reversal")
        self.now = now
        retained = []
        for a in sorted(self.pending, key=lambda a: a.due):
            msg = Envelope.model_validate_json(a.raw)
            key = (a.recipient, msg.message_id)
            p = self.endpoints.get(a.recipient)
            sender = self.endpoints.get(a.source)
            if not p or not sender or p.session != a.session or sender.session != msg.session_id:
                self.event("dropped", a.source, a.recipient, msg.message_id, "session closed")
            elif key in self.receipts:
                self.event("duplicate", a.source, a.recipient, msg.message_id)
            elif now >= a.end:
                self.event("expired", a.source, a.recipient, msg.message_id)
            elif (
                a.due > now
                or State.DISCONNECTED in (p.state, sender.state)
                or not self.link(a.source, a.recipient)
            ):
                retained.append(a)
            elif len(p.inbox) >= self.config.capacity:
                self.event("overflow", a.source, a.recipient, msg.message_id, "inbound")
            else:
                self.receipts.add(key)
                p.inbox.append(msg)
                self.latencies.append(now - msg.sent_ms)
                self.event("delivered", a.source, a.recipient, msg.message_id)
                if msg.payload.message_type == "heartbeat" and p.role == "command":
                    sender.heartbeat = max(sender.heartbeat, msg.sent_ms)
                    sender.state = State.CONNECTED
                if (
                    msg.payload.message_type == "acknowledgement"
                    and msg.payload.outcome in ("accepted", "duplicate")
                    and (a.source, msg.payload.acknowledged_id) not in self.acks
                    and (a.source, msg.payload.acknowledged_id) in self.receipts
                    and self.originals[msg.payload.acknowledged_id][0] == p.name
                ):
                    if msg.payload.acknowledged_id in self.heartbeat_ids:
                        self.confirmed_contact[p.name] = max(
                            self.confirmed_contact[p.name],
                            self.heartbeat_ids[msg.payload.acknowledged_id],
                        )
                    self.acks.add((a.source, msg.payload.acknowledged_id))
                    self.event("acknowledged", a.source, a.recipient, msg.message_id)
        self.pending = retained
        for ep in self.endpoints.values():
            if (
                ep.role == "drone"
                and ep.state == State.CONNECTED
                and now - ep.heartbeat >= self.config.heartbeat_ms
            ):
                ep.state = State.DEGRADED
                self.event("heartbeat_stale", ep.name)

    def port(self, name: str) -> "SimulatedPort":
        return SimulatedPort(self, self.endpoints[name])

    def drain(self, name: str) -> tuple[Envelope, ...]:
        result = []
        while (msg := self.pop_valid(name)) is not None:
            result.append(msg)
        return tuple(result)

    def pop_valid(self, name: str) -> Envelope | None:
        inbox = self.endpoints[name].inbox
        while inbox:
            msg = inbox.popleft()
            if msg.expires_ms is not None and self.now >= msg.expires_ms:
                self.event("expired", msg.source, name, msg.message_id, "before consumption")
                continue
            return msg
        return None

    def metrics(self) -> dict[str, object]:
        c = Counter(str(e["event"]) for e in self.events)
        delays = sorted(self.latencies)
        intended = {
            (e["recipient"], e["message_id"]) for e in self.events if e["event"] == "intended"
        }
        return {
            **{
                k: c[k]
                for k in (
                    "generated",
                    "delivered",
                    "rejected",
                    "expired",
                    "duplicate",
                    "overflow",
                    "dropped",
                    "acknowledged",
                    "connection_lost",
                    "connection_restored",
                )
            },
            "intended_pairs": len(intended),
            "delivery_ratio": len(self.receipts) / len(intended) if intended else None,
            "pending": len(self.pending),
            "bytes": sum(int(str(e["bytes"])) for e in self.events),
            "mean_ms": mean(delays) if delays else None,
            "median_ms": median(delays) if delays else None,
            "p95_ms": delays[ceil(0.95 * len(delays)) - 1] if delays else None,
            "recovery_ms": list(self.recoveries),
            "availability": self.connected_samples / self.samples if self.samples else None,
        }


class SimulatedPort:
    """Nonblocking Phase 1 async port for a single registered simulation participant."""

    def __init__(self, router: Router, endpoint: Endpoint):
        self._router = router
        self._endpoint = endpoint

    async def send(self, message: Envelope) -> None:
        if self._router.endpoints.get(
            self._endpoint.name
        ) is not self._endpoint or not self._router.submit(
            self._endpoint.name, message.model_dump_json().encode()
        ):
            raise ValueError("message rejected")

    async def receive(self) -> Envelope:
        from asyncio import QueueEmpty

        if self._router.endpoints.get(self._endpoint.name) is not self._endpoint:
            raise ValueError("closed endpoint")
        msg = self._router.pop_valid(self._endpoint.name)
        if msg is None:
            raise QueueEmpty
        return msg
