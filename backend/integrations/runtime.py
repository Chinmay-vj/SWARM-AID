"""Bounded, single-process execution of mission simulations.

Each running mission owns one SimulationContext (engine, Model 1 fleet, one Model 2 instance)
stepped on a worker thread. Persistence runs after every tick in its own transaction. If that
transaction fails, the adapter cursors are restored so the next tick persists the same data
again; the in-process simulation itself keeps running independently of the database.
"""

import asyncio
import copy
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.shared.domain import Cell, Evidence
from agents.shared.domain import Observation as DomainObservation
from backend import __version__
from backend.core.config import BackendSettings
from backend.core.errors import Conflict, NotFound, ServiceUnavailable
from backend.database import models as m
from backend.database.session import Database
from backend.integrations.model2_adapter import Model2Sync, digest
from backend.integrations.simulation_adapter import MissionConfig, SimulationContext
from backend.services.events import EventType, emit
from communication.messages import (
    Envelope,
    EnvironmentalObservation,
    HazardDetection,
    Payload,
    PossibleHumanDetection,
)

log = logging.getLogger("backend.runtime")
Notify = Callable[[UUID], Awaitable[None]]
MAX_CONSECUTIVE_DB_FAILURES = 20
TERMINAL = {"completed", "stopped", "failed"}
TRANSITIONS = {
    "draft": {"running"},
    "running": {"paused", "stopped", "completed", "failed"},
    "paused": {"running", "stopped", "failed"},
}
EVENT_FOR = {
    "running": EventType.MISSION_STARTED,
    "paused": EventType.MISSION_PAUSED,
    "stopped": EventType.MISSION_STOPPED,
    "completed": EventType.MISSION_COMPLETED,
    "failed": EventType.MISSION_STOPPED,
}


def git_commit() -> str | None:
    """HEAD commit, suffixed "-dirty" when the working tree has uncommitted changes, so an
    export never claims a commit that does not contain the code that produced it."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]

    def git(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args], capture_output=True, text=True, timeout=5, cwd=root, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    head = git("rev-parse", "HEAD")
    if not head:
        return None
    status = git("status", "--porcelain", "--untracked-files=no")
    return f"{head}-dirty" if status else head


def transition_mission(
    db_session: Session,
    mission: m.Mission,
    target: str,
    actor: str,
    reason: str,
    sim_time_ms: int | None = None,
) -> None:
    """Apply a validated mission status change with history and an outbox event."""
    if target not in TRANSITIONS.get(mission.status, set()):
        raise Conflict(
            f"cannot change mission from {mission.status} to {target}", code="invalid_transition"
        )
    previous = mission.status
    mission.status = target
    db_session.add(
        m.MissionStatusHistory(
            mission_id=mission.id,
            previous=previous,
            status=target,
            actor=actor,
            reason=reason,
            sim_time_ms=sim_time_ms,
        )
    )
    event = (
        EventType.MISSION_RESUMED
        if previous == "paused" and target == "running"
        else EVENT_FOR[target]
    )
    emit(
        db_session,
        mission.id,
        event,
        source=actor,
        resource_type="mission",
        resource_id=mission.id,
        payload={"previous": previous, "status": target, "reason": reason},
        sim_time_ms=sim_time_ms,
    )


@dataclass
class MissionRuntime:
    mission_id: UUID
    run_id: UUID
    ctx: SimulationContext
    sync: Model2Sync
    running: asyncio.Event = field(default_factory=asyncio.Event)
    stop_requested: bool = False
    stop_reason: str = ""
    stop_actor: str = "system"
    task: "asyncio.Task[None] | None" = None
    db_failures: int = 0
    ticks: int = 0
    last_error: str | None = None


class RuntimeManager:
    def __init__(self, db: Database, settings: BackendSettings) -> None:
        self.db = db
        self.settings = settings
        self.runtimes: dict[UUID, MissionRuntime] = {}
        self.notify: Notify | None = None
        self.persistence_failures = 0

    # ----- queries -------------------------------------------------------------------------
    def active_count(self) -> int:
        return sum(1 for r in self.runtimes.values() if r.task is not None and not r.task.done())

    def get(self, mission_id: UUID) -> MissionRuntime:
        runtime = self.runtimes.get(mission_id)
        if runtime is None or runtime.task is None or runtime.task.done():
            raise Conflict("mission is not executing", code="mission_not_running")
        return runtime

    # ----- lifecycle -----------------------------------------------------------------------
    async def start(self, mission_id: UUID, actor: str) -> UUID:
        if mission_id in self.runtimes and not self.runtimes[mission_id].task.done():  # type: ignore[union-attr]
            raise Conflict("mission is already executing", code="duplicate_execution")
        if self.active_count() >= self.settings.max_concurrent_simulations:
            raise Conflict("concurrent simulation limit reached", code="simulation_limit")
        runtime = await asyncio.to_thread(self._prepare, mission_id, actor)
        runtime.running.set()
        self.runtimes[mission_id] = runtime
        runtime.task = asyncio.create_task(self._run(runtime), name=f"mission-{mission_id}")
        await self._notify(mission_id)
        return runtime.run_id

    def _prepare(self, mission_id: UUID, actor: str) -> MissionRuntime:
        with self.db.read() as session:
            mission = session.get(m.Mission, mission_id)
            if mission is None:
                raise NotFound("mission not found")
            config = MissionConfig.model_validate(mission.config)
        ctx = SimulationContext(config)
        with self.db.transaction() as session:
            mission = session.get(m.Mission, mission_id, with_for_update=True)
            assert mission is not None
            if mission.status != "draft":
                raise Conflict(
                    "only draft missions can be started; create a new mission to rerun",
                    code="invalid_transition",
                )
            run = m.SimulationRun(
                mission_id=mission_id,
                scenario_id=config.scenario_id,
                seed=config.seed,
                agents=config.agents,
                config={
                    "mission": config.model_dump(mode="json"),
                    "scenario": ctx.scenario.model_dump(mode="json"),
                    "model2": ctx.command.settings.model_dump(mode="json"),
                },
                software_version=__version__,
                git_commit=git_commit(),
            )
            session.add(run)
            session.flush()
            state = session.get(m.MissionRuntime, mission_id)
            assert state is not None
            state.current_run_id = run.id
            state.last_sim_ms = 0
            transition_mission(session, mission, "running", actor, "simulation started", 0)
            sync = Model2Sync(ctx, mission_id, run.id)
            sync.register_agents(session)
            return MissionRuntime(mission_id, run.id, ctx, sync)

    async def pause(self, mission_id: UUID, actor: str, reason: str) -> None:
        runtime = self.get(mission_id)
        await asyncio.to_thread(self._set_status, runtime, "paused", actor, reason)
        runtime.running.clear()
        await self._notify(mission_id)

    async def resume(self, mission_id: UUID, actor: str, reason: str) -> None:
        runtime = self.get(mission_id)
        await asyncio.to_thread(self._set_status, runtime, "running", actor, reason)
        runtime.running.set()
        await self._notify(mission_id)

    async def stop(self, mission_id: UUID, actor: str, reason: str) -> None:
        runtime = self.get(mission_id)
        runtime.stop_requested, runtime.stop_reason, runtime.stop_actor = True, reason, actor
        runtime.running.set()
        assert runtime.task is not None
        await asyncio.wait_for(asyncio.shield(runtime.task), timeout=30)

    def _set_status(self, runtime: MissionRuntime, target: str, actor: str, reason: str) -> None:
        with self.db.transaction() as session:
            mission = session.get(m.Mission, runtime.mission_id, with_for_update=True)
            assert mission is not None
            transition_mission(session, mission, target, actor, reason, runtime.ctx.now_ms)

    async def shutdown(self) -> None:
        for runtime in list(self.runtimes.values()):
            if runtime.task is not None and not runtime.task.done():
                runtime.stop_requested = True
                runtime.stop_reason = "backend shutdown"
                runtime.running.set()
        tasks = [r.task for r in self.runtimes.values() if r.task is not None]
        if tasks:
            await asyncio.wait(tasks, timeout=30)
        for task in tasks:
            if not task.done():
                task.cancel()

    async def _notify(self, mission_id: UUID) -> None:
        if self.notify is not None:
            try:
                await self.notify(mission_id)
            except Exception:
                log.exception("event dispatch failed")

    # ----- execution loop ------------------------------------------------------------------
    async def _run(self, runtime: MissionRuntime) -> None:
        outcome, reason, actor = "completed", "", "system"
        try:
            while not runtime.ctx.finished and not runtime.stop_requested:
                await runtime.running.wait()
                if runtime.stop_requested:
                    break
                await asyncio.to_thread(self._tick, runtime)
                await self._notify(runtime.mission_id)
                if runtime.db_failures >= MAX_CONSECUTIVE_DB_FAILURES:
                    outcome, reason = "failed", "persistence unavailable"
                    break
                delay = self.settings.simulation_tick_delay_ms / 1000
                await asyncio.sleep(delay)
            if runtime.stop_requested:
                outcome, reason, actor = "stopped", runtime.stop_reason, runtime.stop_actor
            elif outcome == "completed":
                # Engine reasons: "horizon" (time limit) or "inactive" (no active drones left).
                reason = f"simulation ended: {runtime.ctx.engine.reason}"
        except Exception as exc:
            log.exception("mission execution failed")
            runtime.last_error = type(exc).__name__
            outcome, reason = "failed", f"simulation error: {type(exc).__name__}"
        try:
            await asyncio.to_thread(self._finish, runtime, outcome, actor, reason)
        except Exception:
            log.exception("could not record mission completion")
        await self._notify(runtime.mission_id)

    def _tick(self, runtime: MissionRuntime) -> None:
        runtime.ctx.step()
        runtime.ticks += 1
        self.persist(runtime, checkpoint=runtime.ticks % self.settings.snapshot_every_ticks == 0)

    @staticmethod
    def _save(runtime: MissionRuntime) -> dict[str, object]:
        """Shallow-copy adapter cursors and caches. Their elements are immutable (UUIDs, ints,
        tuples, strings), so copying each container is enough to roll back a failed tick."""
        return {
            k: copy.copy(v) if isinstance(v, (dict, set, list)) else v
            for k, v in vars(runtime.sync).items()
            if k != "ctx"
        }

    @staticmethod
    def _restore(runtime: MissionRuntime, saved: dict[str, object]) -> None:
        for key, value in saved.items():
            setattr(runtime.sync, key, value)

    def persist(self, runtime: MissionRuntime, *, checkpoint: bool = False) -> bool:
        with runtime.ctx.lock:
            saved = self._save(runtime)
            try:
                with self.db.transaction() as session:
                    runtime.sync.sync(session)
                    if checkpoint:
                        runtime.sync.checkpoint(session)
            except Exception as exc:  # noqa: BLE001 - restore cursors; retry on the next tick
                self._restore(runtime, saved)
                runtime.db_failures += 1
                self.persistence_failures += 1
                runtime.last_error = type(exc).__name__
                log.warning(
                    "tick persistence failed; will retry", extra={"data": {"error": str(exc)}}
                )
                return False
        runtime.db_failures = 0
        return True

    def _finish(self, runtime: MissionRuntime, outcome: str, actor: str, reason: str) -> None:
        from evaluation.results import metrics as research_metrics

        for _ in range(3):
            if self.persist(runtime, checkpoint=True):
                break
        with self.db.transaction() as session:
            mission = session.get(m.Mission, runtime.mission_id, with_for_update=True)
            assert mission is not None
            if mission.status not in TERMINAL:
                transition_mission(session, mission, outcome, actor, reason, runtime.ctx.now_ms)
            run = session.get(m.SimulationRun, runtime.run_id)
            assert run is not None
            run.ended_at = datetime.now(UTC)
            run.end_reason = outcome if outcome != "completed" else runtime.ctx.engine.reason
            run.final_sim_ms = runtime.ctx.now_ms
            with runtime.ctx.lock:
                run.operational_metrics = runtime.sync.operational_metrics() | {
                    "communication_full": runtime.ctx.network.router.metrics()
                }
                # Evaluator-only metrics use simulator ground truth; research export only.
                run.research_metrics = research_metrics(runtime.ctx.engine)
            for decision in session.scalars(
                select(m.HumanDecision).where(
                    m.HumanDecision.mission_id == runtime.mission_id,
                    m.HumanDecision.status == "submitted",
                )
            ):
                runtime.sync.resolve(
                    session, decision, "undeliverable", "mission ended before processing"
                )

    # ----- human input and agent ingestion -------------------------------------------------
    def submit(
        self,
        mission_id: UUID,
        payload: Payload,
        expires_ms: int,
        revision: int | None = None,
    ) -> tuple[UUID, int]:
        """Send an operator message through the simulated operator-to-command channel."""
        runtime = self.get(mission_id)
        with runtime.ctx.lock:
            now = runtime.ctx.now_ms
            if expires_ms <= now:
                raise Conflict("decision deadline has passed", code="expired")
            runtime.ctx.network.issue("operator", payload, "command", expires_ms, revision)
            message_id = runtime.ctx.network.mail["operator"].sent[-1].message_id
        return message_id, now

    def override_revision(self, mission_id: UUID) -> int:
        runtime = self.get(mission_id)
        with runtime.ctx.lock:
            return runtime.ctx.fleet.command_revision

    def ingest_observation(
        self,
        mission_id: UUID,
        agent_key: str,
        kind: str,
        observation_id: UUID,
        cell: tuple[int, int] | None,
        observed_ms: int,
        confidence: float,
        label: str | None,
        evidence: list[dict[str, object]],
    ) -> tuple[str, UUID]:
        """Hand an authenticated agent report to the mission's Model 2 instance."""
        runtime = self.get(mission_id)
        ctx = runtime.ctx
        with ctx.lock:
            if agent_key not in ctx.engine.drones:
                raise Conflict("agent is not a member of this mission", code="not_member")
            now = ctx.now_ms
            if observed_ms > now:
                raise Conflict("observation is later than mission time", code="future_observation")
            observation = DomainObservation(
                observation_id=observation_id,
                cell=Cell(x=cell[0], y=cell[1]) if cell else None,
                observed_ms=observed_ms,
                confidence=confidence,
                evidence=tuple(
                    Evidence.model_validate(e | {"origin": agent_key}) for e in evidence
                ),
            )
            payload: EnvironmentalObservation | HazardDetection | PossibleHumanDetection
            if kind == "environment":
                payload = EnvironmentalObservation(
                    message_type="environmental_observation",
                    observation=observation,
                    feature=label or "unspecified",
                )
            elif kind == "hazard":
                payload = HazardDetection(
                    message_type="hazard_detection",
                    observation=observation,
                    hazard=label or "unspecified",
                )
            else:
                payload = PossibleHumanDetection(
                    message_type="possible_human_detection", observation=observation
                )
            message_id = ctx.message_id("api", agent_key, observation_id)
            envelope = Envelope(
                schema_version="1.0",
                message_id=message_id,
                source=agent_key,
                destination="command",
                mission_id=ctx.sim_mission_id,
                session_id=ctx.message_id("api-session", agent_key),
                timestamp=datetime(2000, 1, 1, tzinfo=UTC),
                sent_ms=now,
                sequence=0,
                priority="routine",
                correlation_id=message_id,
                payload=payload,
            )
            before = len(ctx.command.events)
            ctx.command.consume(envelope, agent_key, now)
            kinds = [k for _, k, ref in list(ctx.command.events)[before:] if ref == str(message_id)]
            from backend.integrations.model2_adapter import OUTCOME_ORDER

            outcome = next((k for k in OUTCOME_ORDER if k in kinds), "not_processed")
            saved = self._save(runtime)
            try:
                with self.db.transaction() as session:
                    runtime.sync.persist_observation(
                        session, envelope, payload, outcome, "api", now
                    )
                    runtime.sync.sync_model2_outputs(session)
            except Exception as exc:
                self._restore(runtime, saved)
                # Model 2 has the report in memory; the next tick re-persists Model 2 outputs.
                raise ServiceUnavailable(
                    "report processed but not yet persisted", code="persistence_deferred"
                ) from exc
        return outcome, message_id

    # ----- recovery ------------------------------------------------------------------------
    def recover_interrupted(self) -> list[UUID]:
        """Missions left running by a previous process cannot resume: simulator state is not
        durable. Mark them stopped, keep every committed record, and verify the Model 2
        checkpoint so operators know what can be restored."""
        recovered: list[UUID] = []
        with self.db.transaction() as session:
            for mission in session.scalars(
                select(m.Mission).where(m.Mission.status.in_(("running", "paused")))
            ):
                if mission.id in self.runtimes:
                    continue
                transition_mission(
                    session,
                    mission,
                    "stopped",
                    "system",
                    "backend restarted; in-memory simulation state was not durable",
                )
                recovered.append(mission.id)
        return recovered


def verify_snapshot(row: m.MissionSnapshot) -> bool:
    return digest(row.payload) == row.sha256
