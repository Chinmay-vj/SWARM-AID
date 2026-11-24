"""End-to-end synthetic mission through the API: simulator, Model 1, Model 2, persistence."""

from backend_support import Api


def test_mission_runs_and_persists_model2_outputs(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator, agents=6)
    mid = mission["id"]
    assert mission["status"] == "draft" and mission["version"] == 1
    started = api.post(f"/api/v1/missions/{mid}/start", coordinator)
    assert started.status_code == 200, started.text
    final = api.wait_status(mid, coordinator, {"completed"})
    assert final["last_sim_ms"] == 3000

    summary = api.get(f"/api/v1/missions/{mid}/summary", coordinator).json()
    assert summary["agents"] == 6 and summary["observations"] > 0
    incidents = api.get(f"/api/v1/missions/{mid}/incidents", coordinator).json()
    assert incidents["total"] > 0
    first = incidents["items"][0]
    assert first["location"]["crs"] == "swarm-aid:grid" and first["location"]["units"] == "cell"
    history = api.get(f"/api/v1/incidents/{first['id']}/assessments", coordinator).json()
    assert history and history[0]["revision"] == 1
    recs = api.get(f"/api/v1/missions/{mid}/recommendations", coordinator).json()
    assert recs["total"] > 0
    events = api.get(f"/api/v1/missions/{mid}/events", coordinator, params={"limit": 1000}).json()
    sequences = [e["sequence"] for e in events]
    assert sequences == sorted(sequences) and len(set(sequences)) == len(sequences)
    kinds = {e["event_type"] for e in events}
    assert {"MISSION_CREATED", "MISSION_STARTED", "INCIDENT_CREATED", "MISSION_COMPLETED"} <= kinds


def test_identical_scenarios_stay_isolated(api: Api, coordinator: str) -> None:
    """Regression: simulator IDs are deterministic per scenario and seed. Two missions with the
    same configuration once collided on incident and recommendation keys and the second failed."""
    first, second = api.mission(coordinator), api.mission(coordinator)
    for mission in (first, second):
        assert api.post(f"/api/v1/missions/{mission['id']}/start", coordinator).status_code == 200
    for mission in (first, second):
        assert (
            api.wait_status(mission["id"], coordinator, {"completed", "failed"})["status"]
            == "completed"
        )
    ids = []
    for mission in (first, second):
        items = api.get(
            f"/api/v1/missions/{mission['id']}/incidents", coordinator, params={"limit": 500}
        ).json()["items"]
        assert items and {i["mission_id"] for i in items} == {mission["id"]}
        ids.append({i["id"] for i in items})
    assert ids[0].isdisjoint(ids[1])
    assert len(ids[0]) == len(ids[1])  # same seed, same Model 2 outcome


def test_concurrent_simulation_limit(api: Api, coordinator: str) -> None:
    from backend.core.config import BackendSettings

    settings: BackendSettings = api.client.app.state.container.settings  # type: ignore[attr-defined]
    missions = [
        api.mission(coordinator, horizon=2000)
        for _ in range(settings.max_concurrent_simulations + 1)
    ]
    for mission in missions[:-1]:
        assert api.post(f"/api/v1/missions/{mission['id']}/start", coordinator).status_code == 200
    refused = api.post(f"/api/v1/missions/{missions[-1]['id']}/start", coordinator)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "simulation_limit"
    for mission in missions[:-1]:
        stopped = api.post(
            f"/api/v1/missions/{mission['id']}/stop", coordinator, {"reason": "test complete"}
        )
        assert stopped.status_code == 200 and stopped.json()["status"] == "stopped"


def test_phase5_coordination_and_read_models(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator, agents=6, coordination="fixed_sector")
    mid = mission["id"]
    api.post(f"/api/v1/missions/{mid}/start", coordinator)
    api.wait_status(mid, coordinator, {"completed"})
    tasks = api.get(f"/api/v1/missions/{mid}/tasks", coordinator, params={"limit": 500}).json()
    assert tasks["total"] > 0
    task = tasks["items"][0]
    history = api.get(f"/api/v1/tasks/{task['id']}/history", coordinator).json()
    assert [h["state"] for h in history][:3] == ["created", "available", "assigned"]
    assert {t["knowledge"] for t in tasks["items"]} <= {
        "coordinator_known",
        "reported",
        "conflicting",
        "stale",
        "unknown",
    }
    sectors = api.get(f"/api/v1/missions/{mid}/sectors", coordinator).json()
    assert len(sectors) == 6 and all(s["cells"] for s in sectors)
    coverage = api.get(f"/api/v1/missions/{mid}/coverage", coordinator).json()
    assert 0 < coverage["reported_fraction"] <= 1 and coverage["note"].startswith("Reported")
    assert isinstance(
        api.get(f"/api/v1/missions/{mid}/coordination-conflicts", coordinator).json(), list
    )
    agents = api.get(f"/api/v1/missions/{mid}/agents", coordinator).json()
    assert len(agents) == 6 and all(a["location"] for a in agents)
    assert "ground_truth" not in str(agents) and "people" not in agents[0]
    hazards = api.get(f"/api/v1/missions/{mid}/hazards", coordinator).json()
    if hazards:
        assert api.get(f"/api/v1/hazards/{hazards[0]['id']}", coordinator).status_code == 200
    env = api.get(f"/api/v1/missions/{mid}/environment", coordinator).json()
    assert env["crs"] == "swarm-aid:grid" and env["cells"]
    layers = {
        layer["name"] for layer in api.get(f"/api/v1/missions/{mid}/map/layers", coordinator).json()
    }
    assert layers == {"agents", "incidents", "hazards", "stale_observations", "sectors", "coverage"}
    only = api.get(
        f"/api/v1/missions/{mid}/map", coordinator, params={"layers": "agents,hazards"}
    ).json()
    assert [layer["name"] for layer in only["layers"]] == ["agents", "hazards"] and only[
        "crs"
    ] == "swarm-aid:grid"
    metrics = api.get(f"/api/v1/missions/{mid}/metrics", coordinator).json()
    assert metrics["runs"][0]["operational_metrics"]["model2_counts"]
    assert "people_observed" not in str(metrics)  # evaluator ground truth stays out
