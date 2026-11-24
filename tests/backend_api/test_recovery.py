"""Restart, interrupted missions, Model 2 memory restoration, corruption and DB failures."""

from contextlib import contextmanager
from typing import Any
from uuid import UUID

from backend_support import PASSWORD, Api
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from backend.application import create_app
from backend.core.config import BackendSettings
from backend.core.errors import ServiceUnavailable
from backend.database import models as m


def test_committed_data_survives_application_restart(
    api: Api, coordinator: str, settings: BackendSettings
) -> None:
    mission = api.mission(coordinator)
    mid = mission["id"]
    api.post(f"/api/v1/missions/{mid}/start", coordinator)
    api.wait_status(mid, coordinator, {"completed"})
    before = api.get(f"/api/v1/missions/{mid}/summary", coordinator).json()
    events_before = api.get(
        f"/api/v1/missions/{mid}/events", coordinator, params={"limit": 1000}
    ).json()
    with TestClient(create_app(settings)) as restarted:
        token = restarted.post(
            "/api/v1/auth/login", json={"username": coordinator, "password": PASSWORD}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        after = restarted.get(f"/api/v1/missions/{mid}/summary", headers=headers).json()
        events_after = restarted.get(
            f"/api/v1/missions/{mid}/events", headers=headers, params={"limit": 1000}
        ).json()
    assert after == before
    assert [e["id"] for e in events_after] == [e["id"] for e in events_before]


def test_interrupted_missions_are_stopped_on_startup(
    api: Api, coordinator: str, settings: BackendSettings
) -> None:
    mission = api.mission(coordinator)
    mid = mission["id"]
    db = api.client.app.state.container.db  # type: ignore[attr-defined]
    with db.transaction() as session:  # simulate a crash that left the mission "running"
        session.execute(update(m.Mission).where(m.Mission.id == UUID(mid)).values(status="running"))
    with TestClient(create_app(settings)) as restarted:
        token = restarted.post(
            "/api/v1/auth/login", json={"username": coordinator, "password": PASSWORD}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        status = restarted.get(f"/api/v1/missions/{mid}", headers=headers).json()["status"]
        history = restarted.get(f"/api/v1/missions/{mid}/history", headers=headers).json()
    assert status == "stopped"
    assert "not durable" in history[-1]["reason"] and history[-1]["actor"] == "system"


def test_model2_memory_restores_and_detects_corruption(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator, agents=6)
    mid = mission["id"]
    api.post(f"/api/v1/missions/{mid}/start", coordinator)
    api.wait_status(mid, coordinator, {"completed"})
    snapshots = api.get(f"/api/v1/missions/{mid}/snapshots", coordinator).json()
    kinds = {s["kind"] for s in snapshots}
    assert {"model2_checkpoint", "model2_read_model", "coordination"} <= kinds
    report = api.post(f"/api/v1/missions/{mid}/model2/recovery", coordinator).json()
    assert (
        report["restored"]
        and report["integrity_ok"]
        and report["matches_persisted_read_model"] is True
    )
    persisted = api.get(
        f"/api/v1/missions/{mid}/incidents", coordinator, params={"limit": 500}
    ).json()["total"]
    assert report["restored_incidents"] == persisted
    db = api.client.app.state.container.db  # type: ignore[attr-defined]
    with db.transaction() as session:
        latest = session.scalar(
            select(m.MissionSnapshot)
            .where(
                m.MissionSnapshot.mission_id == m.MissionSnapshot.mission_id,
                m.MissionSnapshot.kind == "model2_checkpoint",
            )
            .order_by(m.MissionSnapshot.sim_time_ms.desc(), m.MissionSnapshot.created_at.desc())
        )
        assert latest is not None
        latest.payload = {**latest.payload, "last_tick": 999_999}  # tamper without updating digest
    corrupted = api.post(f"/api/v1/missions/{mid}/model2/recovery", coordinator).json()
    assert corrupted["restored"] is False and corrupted["integrity_ok"] is False
    assert "corrupted" in corrupted["detail"]
    audit = api.get(
        f"/api/v1/missions/{mid}/audit", coordinator, params={"action": "model2.recovery"}
    ).json()
    assert [a["outcome"] for a in audit["items"]] == ["failure", "success"]


def test_database_failure_during_tick_loses_nothing(api: Api, coordinator: str) -> None:
    """A failed tick transaction restores adapter cursors; the next tick persists the same data."""
    from uuid import uuid4

    from backend.integrations.model2_adapter import Model2Sync
    from backend.integrations.runtime import MissionRuntime, RuntimeManager
    from backend.integrations.simulation_adapter import MissionConfig, SimulationContext

    container = api.client.app.state.container  # type: ignore[attr-defined]
    mission = api.mission(coordinator)

    def run(fail_on: set[int]) -> tuple[int, int, int]:
        db = container.db
        manager = RuntimeManager(db, container.settings)
        ctx = SimulationContext(MissionConfig(scenario_id="flood_basic", agents=3))
        with db.transaction() as session:
            row = m.Mission(
                name="f",
                scenario_id="flood_basic",
                sim_mission_id=ctx.sim_mission_id,
                config={},
                created_by=api.ids[coordinator]
                if coordinator in api.ids
                else session.scalar(select(m.User.id)),
            )
            session.add(row)
            session.flush()
            session.add(m.MissionRuntime(mission_id=row.id))
            run_row = m.SimulationRun(
                mission_id=row.id,
                scenario_id="flood_basic",
                seed=42,
                agents=3,
                config={},
                software_version="t",
            )
            session.add(run_row)
            session.flush()
            sync = Model2Sync(ctx, row.id, run_row.id)
            sync.register_agents(session)
            mission_id = row.id
        runtime = MissionRuntime(mission_id, run_row.id, ctx, sync)
        real = db.transaction
        tick = 0

        @contextmanager
        def flaky() -> Any:
            if tick in fail_on:
                raise ServiceUnavailable("simulated outage", code="database_unavailable")
            with real() as session:
                yield session

        db.transaction = flaky
        try:
            failures = 0
            while not ctx.finished:
                ctx.step()
                tick += 1
                failures += not manager.persist(runtime)
        finally:
            db.transaction = real
        assert manager.persist(runtime)
        with db.read() as session:

            def count(model: Any) -> int:
                return int(
                    session.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(model.mission_id == mission_id)
                    )
                    or 0
                )

            return count(m.Observation), count(m.IncidentRevision), failures

    clean = run(set())
    flaky_run = run({3, 4, 5, 11})
    assert flaky_run[2] == 4 and clean[2] == 0
    assert flaky_run[:2] == clean[:2]
    _ = (mission, uuid4)


def test_model2_and_communication_outage_is_reported(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator, outage_steps=[4, 5, 6])
    mid = mission["id"]
    api.post(f"/api/v1/missions/{mid}/start", coordinator)
    api.wait_status(mid, coordinator, {"completed"})
    kinds = [
        e["event_type"]
        for e in api.get(
            f"/api/v1/missions/{mid}/events", coordinator, params={"limit": 1000}
        ).json()
    ]
    for expected in ("MODEL_2_UNAVAILABLE", "MODEL_2_RECOVERED", "COMMUNICATION_DEGRADED"):
        assert expected in kinds, expected
    assert kinds.index("MODEL_2_UNAVAILABLE") < kinds.index("MODEL_2_RECOVERED")
