"""Mission-scoped, deny-by-default authorization and object-level access control."""

from backend_support import Api

from backend.core.permissions import (
    MISSION_MATRIX,
    GlobalRole,
    MissionRole,
    Permission,
    Principal,
)


def test_permission_matrix_is_deny_by_default() -> None:
    from uuid import uuid4

    mission, other = uuid4(), uuid4()
    observer = Principal(
        "o", "human", uuid4(), GlobalRole.OBSERVER, ((mission, MissionRole.OBSERVER),)
    )
    assert observer.can(Permission.MISSION_READ, mission)
    assert not observer.can(Permission.MISSION_READ, other)
    assert not observer.can(Permission.RECOMMENDATION_DECIDE, mission)
    admin = Principal("a", "human", uuid4(), GlobalRole.ADMINISTRATOR)
    assert admin.can(Permission.MISSION_READ, mission)
    assert not admin.can(Permission.RECOMMENDATION_DECIDE, mission)  # no decision authority
    assert not admin.can(Permission.MISSION_CONTROL, mission)
    agent = Principal("d0", "agent", machine_mission=mission)
    assert agent.can(Permission.OBSERVATION_INGEST, mission)
    assert not agent.can(Permission.OBSERVATION_INGEST, other)
    assert not agent.can(Permission.MISSION_READ, mission)
    assert Permission.INCIDENT_CLOSE not in MISSION_MATRIX[MissionRole.OPERATOR]
    assert Permission.EXPORT_RESEARCH not in MISSION_MATRIX[MissionRole.COORDINATOR]


def test_roles_and_cross_mission_isolation(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator)
    mid = mission["id"]
    for name, role in (
        ("obs", GlobalRole.OBSERVER),
        ("outsider", GlobalRole.COORDINATOR),
        ("root", GlobalRole.ADMINISTRATOR),
    ):
        api.user(name, role)
        api.login(name)
    api.post(
        f"/api/v1/missions/{mid}/members",
        coordinator,
        {"user_id": str(api.ids["obs"]), "role": "observer"},
    )
    assert api.get(f"/api/v1/missions/{mid}", "obs").status_code == 200
    # Observer: read only.
    assert api.post(f"/api/v1/missions/{mid}/start", "obs").status_code == 403
    assert (
        api.patch(f"/api/v1/missions/{mid}", "obs", {"version": 1, "name": "x"}).status_code == 403
    )
    assert (
        api.post(
            f"/api/v1/missions/{mid}/override", "obs", {"action": "pause", "reason": "x"}
        ).status_code
        == 403
    )
    assert api.get(f"/api/v1/missions/{mid}/exports/operational", "obs").status_code == 403
    # A coordinator of another mission sees nothing here: 404, not 403, to avoid disclosure.
    assert api.get(f"/api/v1/missions/{mid}", "outsider").status_code == 404
    assert api.get(f"/api/v1/missions/{mid}/incidents", "outsider").status_code == 404
    assert api.post(f"/api/v1/missions/{mid}/start", "outsider").status_code == 404
    listing = api.get("/api/v1/missions", "outsider").json()
    assert listing["total"] == 0
    # Administrators can read and manage membership but cannot control or decide.
    assert api.get(f"/api/v1/missions/{mid}", "root").status_code == 200
    assert api.post(f"/api/v1/missions/{mid}/start", "root").status_code == 403
    assert api.get("/api/v1/system/health", "root").status_code == 200
    assert api.get("/api/v1/system/health", coordinator).status_code == 403
    # Observers cannot create missions.
    created = api.post(
        "/api/v1/missions", "obs", {"name": "x", "config": {"scenario_id": "flood_basic"}}
    )
    assert created.status_code == 403
    # Denied requests are audited.
    audit = api.get(
        f"/api/v1/missions/{mid}/audit", coordinator, params={"action": "access.denied"}
    ).json()
    assert audit["total"] >= 3


def test_protected_fields_and_lifecycle_cannot_be_mass_assigned(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator)
    mid = mission["id"]
    for field, value in (
        ("status", "running"),
        ("created_by", "00000000-0000-0000-0000-000000000000"),
        ("config", {}),
    ):
        response = api.patch(f"/api/v1/missions/{mid}", coordinator, {"version": 1, field: value})
        assert response.status_code == 422, field
    ok = api.patch(f"/api/v1/missions/{mid}", coordinator, {"version": 1, "name": "renamed"})
    assert ok.status_code == 200 and ok.json()["version"] == 2 and ok.json()["status"] == "draft"
    stale = api.patch(f"/api/v1/missions/{mid}", coordinator, {"version": 1, "name": "lost update"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_version"
    assert stale.json()["error"]["details"]["current_version"] == 2
    # Mission creation also rejects unknown fields (e.g. a client-supplied status).
    bad = api.post(
        "/api/v1/missions",
        coordinator,
        {"name": "x", "status": "running", "config": {"scenario_id": "flood_basic"}},
    )
    assert bad.status_code == 422


def test_lifecycle_state_machine_and_limits(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator, agents=3)
    mid = mission["id"]
    assert (
        api.post(f"/api/v1/missions/{mid}/pause", coordinator).json()["error"]["code"]
        == "mission_not_running"
    )
    assert api.post(f"/api/v1/missions/{mid}/start", coordinator).status_code == 200
    duplicate = api.post(f"/api/v1/missions/{mid}/start", coordinator)
    assert duplicate.status_code == 409
    api.wait_status(mid, coordinator, {"completed"})
    rerun = api.post(f"/api/v1/missions/{mid}/start", coordinator)
    assert rerun.status_code == 409 and rerun.json()["error"]["code"] == "invalid_transition"
    history = [h["status"] for h in api.get(f"/api/v1/missions/{mid}/history", coordinator).json()]
    assert history == ["running", "completed"]
