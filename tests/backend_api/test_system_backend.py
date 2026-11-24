"""Phase 9 backend integration: conflicting evidence, traceability, evaluator isolation,
mission isolation, repeated lifecycles and graceful shutdown."""

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from backend_support import Api, decision_status, paused_with_review
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.core.config import BackendSettings
from backend.core.permissions import GlobalRole
from backend.database import models as m
from backend.database.session import Database, build_engine

EVALUATOR_KEYS = {
    "people_observed",
    "false_positive",
    "missed",
    "research_metrics",
    "evaluator_ground_truth",
    "first_person_capture_ms",
}


@pytest.fixture
def paced(slow_settings: BackendSettings) -> Any:
    with TestClient(create_app(slow_settings)) as client:
        api = Api(client, slow_settings)
        api.user("coord", GlobalRole.COORDINATOR)
        api.login("coord")
        yield api


def keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys(v)}
    return set()


def agent_token(api: Api, mid: str, agent: str) -> dict[str, str]:
    cred = api.post(
        f"/api/v1/missions/{mid}/agent-credentials", "coord", {"agent_key": agent}
    ).json()
    token = api.client.post(
        "/api/v1/auth/machine-token",
        json={"credential_id": cred["credential_id"], "secret": cred["secret"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def hazard(observed_ms: int, label: str, cell: tuple[int, int]) -> dict[str, Any]:
    return {
        "observation_id": str(uuid4()),
        "kind": "hazard",
        "label": label,
        "observed_ms": observed_ms,
        "confidence": 0.7,
        "cell": list(cell),
        "evidence": [
            {
                "evidence_id": str(uuid4()),
                "captured_ms": observed_ms,
                "modality": "image",
                "artifact_key": "synthetic/fixture-hazard",
            }
        ],
    }


def test_conflicting_reports_stay_visible_as_conflicting_evidence(paced: Api) -> None:
    """Regression: Model 2 flagged contradicting reports, but every persisted evidence link
    was "supporting", so operators always saw zero conflicting observations."""
    mid, _ = paused_with_review(paced, "coord")
    now = paced.get(f"/api/v1/missions/{mid}", "coord").json()["last_sim_ms"]
    cell = (11, 9)
    first = paced.client.post(
        f"/api/v1/missions/{mid}/observations",
        json=hazard(now, "water", cell),
        headers=agent_token(paced, mid, "d0"),
    )
    second_body = hazard(now, "fire", cell)  # same cell and time, different finding
    second = paced.client.post(
        f"/api/v1/missions/{mid}/observations",
        json=second_body,
        headers=agent_token(paced, mid, "d1"),
    )
    assert first.status_code == second.status_code == 202, (first.text, second.text)
    incidents = paced.get(
        f"/api/v1/missions/{mid}/incidents", "coord", params={"limit": 500}
    ).json()["items"]
    flagged = [i for i in incidents if i["conflicting_observations"] > 0]
    assert flagged, "contradicting report is not visible as conflicting evidence"
    observations = paced.get(
        f"/api/v1/missions/{mid}/observations", "coord", params={"limit": 500, "kind": "hazard"}
    ).json()["items"]
    pk = next(o["id"] for o in observations if o["observation_id"] == second_body["observation_id"])
    trace = paced.get(f"/api/v1/observations/{pk}/trace", "coord").json()
    assert [t["role"] for t in trace["incidents"]] == ["conflicting"]
    assert trace["observation"]["reporter"] == "d1"
    assert {e["origin"] for e in trace["evidence"]} == {"d1"}


def test_observation_trace_follows_report_to_human_decision(api: Api, coordinator: str) -> None:
    mid, item = paused_with_review(api, coordinator)
    rec = item["recommendation"]
    decision = api.post(
        f"/api/v1/recommendations/{rec['id']}/approve",
        coordinator,
        {"version": rec["version"], "reason": "trace check"},
    ).json()
    api.post(f"/api/v1/missions/{mid}/resume", coordinator)
    api.wait(lambda: decision_status(api, mid, coordinator, decision["id"]) != "submitted")
    group = api.get(f"/api/v1/incidents/{rec['incident_id']}/evidence", coordinator).json()
    observation = group["observations"][0]
    trace = api.get(f"/api/v1/observations/{observation['id']}/trace", coordinator).json()
    assert trace["observation"]["id"] == observation["id"]
    assert rec["incident_id"] in {t["incident"]["id"] for t in trace["incidents"]}
    assert rec["id"] in {r["id"] for r in trace["recommendations"]}
    assert decision["id"] in {d["id"] for d in trace["decisions"]}
    sequences = [e["sequence"] for e in trace["events"]]
    assert sequences == sorted(sequences) and not trace["events_truncated"]
    kinds = {e["event_type"] for e in trace["events"]}
    assert {"OBSERVATION_RECEIVED", "RECOMMENDATION_CREATED", "HUMAN_DECISION_RESOLVED"} <= kinds
    assert not EVALUATOR_KEYS & keys(trace)
    # Mission scope: a coordinator who is not a member cannot trace it.
    api.user("other", GlobalRole.COORDINATOR)
    api.login("other")
    assert api.get(f"/api/v1/observations/{observation['id']}/trace", "other").status_code == 404
    assert api.get(f"/api/v1/observations/{observation['id']}/trace", None).status_code == 401


def test_operational_views_never_contain_evaluator_ground_truth(api: Api, coordinator: str) -> None:
    mid = api.mission(coordinator, agents=6)["id"]
    api.post(f"/api/v1/missions/{mid}/start", coordinator)
    api.wait_status(mid, coordinator, {"completed"})
    paths = [
        f"/api/v1/missions/{mid}",
        f"/api/v1/missions/{mid}/summary",
        f"/api/v1/missions/{mid}/metrics",
        f"/api/v1/missions/{mid}/map",
        f"/api/v1/missions/{mid}/coverage",
        f"/api/v1/missions/{mid}/agents",
        f"/api/v1/missions/{mid}/incidents",
        f"/api/v1/missions/{mid}/observations",
        f"/api/v1/missions/{mid}/tasks",
        f"/api/v1/missions/{mid}/hazards",
        f"/api/v1/missions/{mid}/snapshots",
        f"/api/v1/missions/{mid}/exports/operational",
    ]
    for path in paths:
        response = api.get(path, coordinator, params={"limit": 500} if "?" not in path else None)
        assert response.status_code == 200, path
        leaked = EVALUATOR_KEYS & keys(response.json())
        assert not leaked, f"{path} exposes evaluator data: {leaked}"
    events = api.get(f"/api/v1/missions/{mid}/events", coordinator, params={"limit": 1000}).json()
    assert not EVALUATOR_KEYS & keys(events)


def test_stopping_one_mission_does_not_affect_another(paced: Api) -> None:
    a = paced.mission("coord", horizon=2000)["id"]
    b = paced.mission("coord", horizon=60)["id"]
    for mid in (a, b):
        assert paced.post(f"/api/v1/missions/{mid}/start", "coord").status_code == 200
    paced.wait(lambda: paced.get(f"/api/v1/missions/{b}", "coord").json()["last_sim_ms"] > 0)
    assert paced.post(
        f"/api/v1/missions/{a}/stop", "coord", {"reason": "isolation"}
    ).status_code in (
        200,
        202,
    )
    assert paced.wait_status(a, "coord", {"stopped"})["status"] == "stopped"
    finished = paced.wait_status(b, "coord", {"completed", "failed", "stopped"}, timeout=60)
    assert finished["status"] == "completed"
    history = [h["status"] for h in paced.get(f"/api/v1/missions/{b}/history", "coord").json()]
    assert "stopped" not in history
    events = paced.get(f"/api/v1/missions/{b}/events", "coord", params={"limit": 1000}).json()
    assert {e["mission_id"] for e in events} == {b}


def test_repeated_mission_lifecycles_release_runtime_resources(paced: Api) -> None:
    runtime = paced.client.app.state.container.runtime  # type: ignore[attr-defined]
    for _ in range(4):
        mid = paced.mission("coord", horizon=2000)["id"]
        assert paced.post(f"/api/v1/missions/{mid}/start", "coord").status_code == 200
        again = paced.post(f"/api/v1/missions/{mid}/start", "coord")
        assert again.status_code == 409
        paced.post(f"/api/v1/missions/{mid}/stop", "coord", {"reason": "cycle"})
        paced.wait_status(mid, "coord", {"stopped"})
        paced.wait(lambda: runtime.active_count() == 0)
        repeat_stop = paced.post(f"/api/v1/missions/{mid}/stop", "coord", {"reason": "again"})
        assert repeat_stop.status_code == 409
    assert all(r.task is not None and r.task.done() for r in runtime.runtimes.values())


def test_graceful_shutdown_stops_running_missions(
    slow_settings: BackendSettings, db_path: Path
) -> None:
    with TestClient(create_app(slow_settings)) as client:
        api = Api(client, slow_settings)
        api.user("coord", GlobalRole.COORDINATOR)
        api.login("coord")
        mid = api.mission("coord", horizon=5000)["id"]
        api.post(f"/api/v1/missions/{mid}/start", "coord")
        api.wait(lambda: api.get(f"/api/v1/missions/{mid}", "coord").json()["last_sim_ms"] > 0)
    # Leaving the context runs the lifespan shutdown, as uvicorn does on a stop request.
    db = Database(build_engine(slow_settings))
    try:
        with db.read() as session:
            mission = session.get(m.Mission, __import__("uuid").UUID(mid))
            assert mission is not None and mission.status == "stopped"
            reasons = [
                h.reason
                for h in session.query(m.MissionStatusHistory).filter_by(mission_id=mission.id)
            ]
            run = session.query(m.SimulationRun).filter_by(mission_id=mission.id).one()
            assert run.ended_at is not None and run.final_sim_ms and run.final_sim_ms > 0
    finally:
        db.dispose()
    assert "backend shutdown" in reasons
