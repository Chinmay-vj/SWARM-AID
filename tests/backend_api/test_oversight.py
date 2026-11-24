"""Human decisions are recorded durably, validated by Model 2 and never silently overwritten."""

from typing import Any

import pytest
from backend_support import Api, decision_status, paused_with_review
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.core.config import BackendSettings
from backend.core.permissions import GlobalRole


@pytest.fixture
def paced(slow_settings: BackendSettings) -> Any:
    with TestClient(create_app(slow_settings)) as client:
        api = Api(client, slow_settings)
        api.user("coord", GlobalRole.COORDINATOR)
        api.login("coord")
        yield api


def resolve(api: Api, mid: str, decision_id: str) -> str:
    status = "submitted"

    def done() -> bool:
        nonlocal status
        status = decision_status(api, mid, "coord", decision_id)
        return status != "submitted"

    api.wait(done)
    return status


def test_approval_is_validated_by_model2_and_persisted(paced: Api) -> None:
    mid, item = paused_with_review(paced, "coord")
    rec = item["recommendation"]
    response = paced.post(
        f"/api/v1/recommendations/{rec['id']}/approve",
        "coord",
        {
            "version": rec["version"],
            "reason": "synthetic review",
            "idempotency_key": "approve-0001",
        },
    )
    assert response.status_code == 202, response.text
    decision = response.json()
    assert decision["status"] == "submitted" and decision["actor_role"] == "coordinator"
    # Idempotent replay returns the same decision; reusing the key for another action conflicts.
    again = paced.post(
        f"/api/v1/recommendations/{rec['id']}/approve",
        "coord",
        {
            "version": rec["version"],
            "reason": "synthetic review",
            "idempotency_key": "approve-0001",
        },
    )
    assert again.status_code == 202 and again.json()["id"] == decision["id"]
    clash = paced.post(
        f"/api/v1/recommendations/{rec['id']}/reject",
        "coord",
        {"version": rec["version"], "reason": "x", "idempotency_key": "approve-0001"},
    )
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "idempotency_conflict"
    assert paced.post(f"/api/v1/missions/{mid}/resume", "coord").status_code == 200
    assert resolve(paced, mid, decision["id"]) == "accepted"
    stored = paced.get(f"/api/v1/recommendations/{rec['id']}", "coord").json()
    assert stored["status"] == "approved"
    history = paced.get(f"/api/v1/incidents/{rec['incident_id']}/history", "coord").json()
    assert any(h["state"] == "acknowledged" and h["actor"] == "operator" for h in history)
    # Approved recommendations are immutable: a second decision on it is refused.
    late = paced.post(
        f"/api/v1/recommendations/{rec['id']}/reject",
        "coord",
        {"version": rec["version"], "reason": "x"},
    )
    assert late.status_code == 409
    audit = paced.get(
        f"/api/v1/missions/{mid}/audit", "coord", params={"action": "approval.approve_review"}
    ).json()
    assert audit["total"] == 1


def test_outdated_version_and_unauthorized_decisions_are_refused(paced: Api) -> None:
    mid, item = paused_with_review(paced, "coord")
    rec = item["recommendation"]
    stale = paced.post(
        f"/api/v1/recommendations/{rec['id']}/approve",
        "coord",
        {"version": rec["version"] + 1, "reason": "x"},
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_version"
    paced.user("watcher", GlobalRole.OBSERVER)
    paced.login("watcher")
    paced.post(
        f"/api/v1/missions/{mid}/members",
        "coord",
        {"user_id": str(paced.ids["watcher"]), "role": "observer"},
    )
    denied = paced.post(
        f"/api/v1/recommendations/{rec['id']}/approve",
        "watcher",
        {"version": rec["version"], "reason": "x"},
    )
    assert denied.status_code == 403
    paced.user("field", GlobalRole.OPERATOR)
    paced.login("field")
    paced.post(
        f"/api/v1/missions/{mid}/members",
        "coord",
        {"user_id": str(paced.ids["field"]), "role": "operator"},
    )
    assert (
        paced.post(
            f"/api/v1/recommendations/{rec['id']}/approve",
            "field",
            {"version": rec["version"], "reason": "x"},
        ).status_code
        == 403
    )
    close = paced.post(
        f"/api/v1/incidents/{rec['incident_id']}/close",
        "field",
        {"revision": rec["version"], "reason": "x"},
    )
    assert close.status_code == 403
    paced.user("boss", GlobalRole.ADMINISTRATOR)
    paced.login("boss")
    assert (
        paced.post(
            f"/api/v1/recommendations/{rec['id']}/approve",
            "boss",
            {"version": rec["version"], "reason": "x"},
        ).status_code
        == 403
    )
    # Closure without a prior resolution report is refused even for a coordinator.
    early = paced.post(
        f"/api/v1/incidents/{rec['incident_id']}/close",
        "coord",
        {"revision": rec["version"], "reason": "x"},
    )
    assert early.status_code == 409 and early.json()["error"]["code"] == "resolution_required"


def review_until_accepted(
    paced: Api, mid: str, incident_id: str, action: str, attempts: int = 25
) -> int:
    """Behave like a correct client: submit against the current revision; on a Model 2 revision
    mismatch, re-read and retry. Every rejection must be a genuine revision mismatch."""
    for rejections in range(attempts):
        paced.post(f"/api/v1/missions/{mid}/pause", "coord")
        incident = paced.get(f"/api/v1/incidents/{incident_id}", "coord").json()
        if action == "close" and incident["disposition"] != "resolution_reported":
            return -1
        response = paced.post(
            f"/api/v1/incidents/{incident_id}/{'resolution-report' if action == 'resolve' else 'close'}",
            "coord",
            {"revision": incident["revision"], "reason": f"synthetic {action}"},
        )
        assert response.status_code == 202, response.text
        paced.post(f"/api/v1/missions/{mid}/resume", "coord")
        status = resolve(paced, mid, response.json()["id"])
        if status == "accepted":
            return rejections
        decisions = paced.get(
            f"/api/v1/missions/{mid}/human-decisions", "coord", params={"limit": 500}
        ).json()
        record = next(d for d in decisions["items"] if d["id"] == response.json()["id"])
        assert record["status"] == "rejected" and record["outcome_reason"] == "rejected_amendment"
        current = paced.get(f"/api/v1/incidents/{incident_id}", "coord").json()
        assert current["revision"] > incident["revision"], "rejection must follow a newer revision"
    raise AssertionError(f"{action} never matched the current revision in {attempts} attempts")


def test_rejection_resolution_and_closure_flow(paced: Api) -> None:
    # One moving drone: once it leaves the cell, no new evidence re-opens the incident.
    mid, item = paused_with_review(paced, "coord", horizon=400, agents=1)
    rec = item["recommendation"]
    rejected = paced.post(
        f"/api/v1/recommendations/{rec['id']}/reject",
        "coord",
        {"version": rec["version"], "reason": "not credible"},
    )
    assert rejected.status_code == 202
    paced.post(f"/api/v1/missions/{mid}/resume", "coord")
    assert resolve(paced, mid, rejected.json()["id"]) == "accepted"
    incident_id = rec["incident_id"]
    closed = -1
    for _ in range(10):
        review_until_accepted(paced, mid, incident_id, "resolve")
        closed = review_until_accepted(paced, mid, incident_id, "close")
        if closed >= 0:
            break
    assert closed >= 0, "closure was never reachable"
    states = [
        h["state"] for h in paced.get(f"/api/v1/incidents/{incident_id}/history", "coord").json()
    ]
    assert "rejected" in states and "resolution_reported" in states and "closed" in states
    assert paced.get(f"/api/v1/incidents/{incident_id}", "coord").json()["disposition"] == "closed"
    # Closing records a human disposition only; it asserts nothing about physical rescue.


def test_override_and_alert_acknowledgement(paced: Api) -> None:
    mid, _ = paused_with_review(paced, "coord")
    override = paced.post(
        f"/api/v1/missions/{mid}/override",
        "coord",
        {"action": "pause", "reason": "hold assignments"},
    )
    assert override.status_code == 202
    paced.post(f"/api/v1/missions/{mid}/resume", "coord")
    assert resolve(paced, mid, override.json()["id"]) == "accepted"
    events = paced.get(
        f"/api/v1/missions/{mid}/events", "coord", params={"event_type": "HUMAN_OVERRIDE_RECORDED"}
    ).json()
    assert len(events) == 1
    alerts = paced.get(f"/api/v1/missions/{mid}/alerts", "coord").json()
    assert alerts["total"] > 0
    alert = alerts["items"][0]
    ack = paced.post(f"/api/v1/alerts/{alert['id']}/acknowledge", "coord", {"reason": "seen"})
    assert ack.status_code == 200 and ack.json()["acknowledged_at"] is not None
    again = paced.post(f"/api/v1/alerts/{alert['id']}/acknowledge", "coord")
    assert again.json()["acknowledged_at"] == ack.json()["acknowledged_at"]


def test_decisions_require_a_running_mission(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator)
    response = api.post(
        f"/api/v1/missions/{mission['id']}/override",
        coordinator,
        {"action": "pause", "reason": "x"},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "mission_not_running"
