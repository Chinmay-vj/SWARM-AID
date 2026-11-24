"""Persistent Model 2 memory: versioned checkpoints with integrity digests and restoration.

What is durable:
- Continuously (every tick, transactionally): observations, evidence, incidents and revisions,
  transitions, recommendations, decisions, alerts, tasks, hazards and outbox events.
- Periodically (every snapshot_every_ticks and at mission end): the Model 2 replay journal
  (agents.command_agent.agent.Checkpoint) and the Model 2 read model.

Restoration replays the journal through CommandAgent.restore, so Model 2 rebuilds its own
memory with its own validation. Router queues, sender sessions and the simulator are not
durable; a restored instance is a read-only reconstruction, not a resumed simulation.
"""

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select

from agents.command_agent.agent import Checkpoint, CommandAgent
from backend.database import models as m
from backend.database.session import Database
from backend.integrations.model2_adapter import digest

SUPPORTED_SCHEMA_VERSIONS = {"1"}


@dataclass(frozen=True)
class StoredSnapshot:
    snapshot_id: UUID
    mission_id: UUID
    kind: str
    schema_version: str
    sim_time_ms: int
    payload: dict[str, Any]
    sha256: str
    complete: bool


class SnapshotRepository(Protocol):
    def save(self, snapshot: StoredSnapshot) -> None: ...
    def latest(self, mission_id: UUID, kind: str) -> StoredSnapshot | None: ...


class InMemorySnapshotRepository:
    """Process-local repository for tests and runs without a database."""

    def __init__(self) -> None:
        self.rows: list[StoredSnapshot] = []

    def save(self, snapshot: StoredSnapshot) -> None:
        self.rows.append(snapshot)

    def latest(self, mission_id: UUID, kind: str) -> StoredSnapshot | None:
        matches = [r for r in self.rows if r.mission_id == mission_id and r.kind == kind]
        return max(matches, key=lambda r: r.sim_time_ms) if matches else None


class SqlSnapshotRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, snapshot: StoredSnapshot) -> None:
        with self.db.transaction() as session:
            session.add(
                m.MissionSnapshot(
                    id=snapshot.snapshot_id,
                    mission_id=snapshot.mission_id,
                    kind=snapshot.kind,
                    schema_version=snapshot.schema_version,
                    sim_time_ms=snapshot.sim_time_ms,
                    payload=snapshot.payload,
                    sha256=snapshot.sha256,
                    complete=snapshot.complete,
                )
            )

    def latest(self, mission_id: UUID, kind: str) -> StoredSnapshot | None:
        with self.db.read() as session:
            row = session.scalar(
                select(m.MissionSnapshot)
                .where(m.MissionSnapshot.mission_id == mission_id, m.MissionSnapshot.kind == kind)
                .order_by(m.MissionSnapshot.sim_time_ms.desc(), m.MissionSnapshot.created_at.desc())
            )
            if row is None:
                return None
            return StoredSnapshot(
                row.id,
                row.mission_id,
                row.kind,
                row.schema_version,
                row.sim_time_ms,
                row.payload,
                row.sha256,
                row.complete,
            )


@dataclass(frozen=True)
class Restoration:
    snapshot: StoredSnapshot | None
    agent: CommandAgent | None
    integrity_ok: bool
    detail: str


def normalized(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(json.dumps(payload, default=str))
    return result


def restore_model2(
    repository: SnapshotRepository, mission_id: UUID, sim_mission_id: UUID
) -> Restoration:
    """Restore Model 2 memory from the latest checkpoint, rejecting corrupt or foreign data."""
    snapshot = repository.latest(mission_id, "model2_checkpoint")
    if snapshot is None:
        return Restoration(None, None, False, "no checkpoint stored")
    if snapshot.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        return Restoration(snapshot, None, False, f"unsupported schema {snapshot.schema_version}")
    if digest(snapshot.payload) != snapshot.sha256:
        return Restoration(snapshot, None, False, "integrity digest mismatch: snapshot corrupted")
    if not snapshot.complete:
        return Restoration(snapshot, None, True, "journal incomplete; full restore unavailable")
    try:
        checkpoint = Checkpoint.model_validate(snapshot.payload)
        agent = CommandAgent.restore(checkpoint, sim_mission_id, frozenset(checkpoint.members))
    except (ValidationError, ValueError) as exc:
        return Restoration(snapshot, None, True, f"checkpoint rejected: {type(exc).__name__}")
    if checkpoint.mission != sim_mission_id:
        return Restoration(snapshot, None, True, "checkpoint belongs to another mission")
    return Restoration(snapshot, agent, True, "restored from replay journal")
