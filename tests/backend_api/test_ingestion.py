"""Authenticated Model 1 report ingestion through Model 2, idempotency and evidence storage."""

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from backend_support import Api, paused_with_review
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.core.config import BackendSettings
from backend.core.errors import NotFound, Unprocessable
from backend.core.permissions import GlobalRole
from backend.persistence.evidence_store import LocalEvidenceStore


@pytest.fixture
def paced(slow_settings: BackendSettings) -> Any:
    with TestClient(create_app(slow_settings)) as client:
        api = Api(client, slow_settings)
        api.user("coord", GlobalRole.COORDINATOR)
        api.login("coord")
        yield api


def agent_headers(api: Api, mid: str, agent: str = "d0") -> dict[str, str]:
    cred = api.post(
        f"/api/v1/missions/{mid}/agent-credentials", "coord", {"agent_key": agent}
    ).json()
    token = api.client.post(
        "/api/v1/auth/machine-token",
        json={"credential_id": cred["credential_id"], "secret": cred["secret"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def report(observed_ms: int, kind: str = "possible_human", **extra: Any) -> dict[str, Any]:
    return {
        "observation_id": str(uuid4()),
        "kind": kind,
        "observed_ms": observed_ms,
        "confidence": 0.6,
        "cell": [9, 8],
        "evidence": [
            {
                "evidence_id": str(uuid4()),
                "captured_ms": observed_ms,
                "modality": "thermal",
                "artifact_key": "synthetic/fixture-1",
            }
        ],
        **extra,
    }


def test_agent_reports_flow_through_model2(paced: Api) -> None:
    mid, _ = paused_with_review(paced, "coord")
    headers = agent_headers(paced, mid)
    now = paced.get(f"/api/v1/missions/{mid}", "coord").json()["last_sim_ms"]
    body = report(now)
    first = paced.client.post(f"/api/v1/missions/{mid}/observations", json=body, headers=headers)
    assert first.status_code == 202, first.text
    assert first.json()["outcome"] == "admitted" and not first.json()["duplicate"]
    again = paced.client.post(f"/api/v1/missions/{mid}/observations", json=body, headers=headers)
    assert (
        again.status_code == 202
        and again.json()["duplicate"]
        and again.json()["message_id"] == first.json()["message_id"]
    )
    tampered = dict(body, confidence=0.99)
    assert (
        paced.client.post(
            f"/api/v1/missions/{mid}/observations", json=tampered, headers=headers
        ).status_code
        == 409
    )
    future = paced.client.post(
        f"/api/v1/missions/{mid}/observations", json=report(now + 10_000), headers=headers
    )
    assert future.status_code == 409 and future.json()["error"]["code"] == "future_observation"
    # Clients cannot submit incident classifications: unknown fields are rejected.
    classified = paced.client.post(
        f"/api/v1/missions/{mid}/observations",
        json=report(now, category="human_confirmed"),
        headers=headers,
    )
    assert classified.status_code == 422
    observations = paced.get(
        f"/api/v1/missions/{mid}/observations", "coord", params={"reporter": "d0", "limit": 500}
    ).json()
    stored = next(o for o in observations["items"] if o["observation_id"] == body["observation_id"])
    assert (
        stored["source"] == "api"
        and stored["reporter"] == "d0"
        and stored["location"]["crs"] == "swarm-aid:grid"
    )
    evidence = paced.get(f"/api/v1/observations/{stored['id']}/evidence", "coord").json()
    assert evidence[0]["origin"] == "d0"  # provenance from the credential, never the body
    incidents = paced.get(
        f"/api/v1/missions/{mid}/incidents", "coord", params={"limit": 500}
    ).json()["items"]
    at_cell = [
        i
        for i in incidents
        if i["location"] and (i["location"]["x"], i["location"]["y"]) == (9.0, 8.0)
    ]
    assert at_cell, "Model 2 opened an incident for the API-ingested sighting"
    group = paced.get(f"/api/v1/evidence-groups/{at_cell[0]['id']}", "coord").json()
    assert "d0" in group["distinct_reporters"]


def test_ingestion_requires_agent_identity_of_this_mission(paced: Api) -> None:
    mid, _ = paused_with_review(paced, "coord")
    other = paced.mission("coord")
    foreign = agent_headers(paced, other["id"])
    body = report(0)
    assert (
        paced.client.post(
            f"/api/v1/missions/{mid}/observations", json=body, headers=foreign
        ).status_code
        == 404
    )
    assert paced.post(f"/api/v1/missions/{mid}/observations", "coord", body).status_code == 422
    assert paced.client.post(f"/api/v1/missions/{mid}/observations", json=body).status_code == 401
    headers = agent_headers(paced, mid)
    assert paced.client.get(f"/api/v1/missions/{mid}/incidents", headers=headers).status_code == 404
    health = paced.client.post(
        f"/api/v1/missions/{mid}/agent-health",
        json={"battery_fraction": 0.7, "cell": [1, 1]},
        headers=headers,
    )
    assert health.status_code == 202 and health.json()["location"]["x"] == 1.0


def test_evidence_objects_are_content_addressed_and_contained(
    api: Api, coordinator: str, tmp_path: Path
) -> None:
    mission = api.mission(coordinator)
    mid = mission["id"]
    cred = api.post(
        f"/api/v1/missions/{mid}/agent-credentials", coordinator, {"agent_key": "d1"}
    ).json()
    token = api.client.post(
        "/api/v1/auth/machine-token",
        json={"credential_id": cred["credential_id"], "secret": cred["secret"]},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "text/plain"}
    stored = api.client.post(
        f"/api/v1/missions/{mid}/evidence-objects",
        content=b"synthetic thermal summary",
        headers=headers,
    )
    assert stored.status_code == 201, stored.text
    meta = stored.json()
    assert len(meta["sha256"]) == 64 and meta["size_bytes"] == 25 and "storage_key" not in meta
    dup = api.client.post(
        f"/api/v1/missions/{mid}/evidence-objects",
        content=b"synthetic thermal summary",
        headers=headers,
    )
    assert dup.json()["id"] == meta["id"]
    content = api.get(f"/api/v1/evidence-objects/{meta['id']}/content", coordinator)
    assert (
        content.content == b"synthetic thermal summary"
        and content.headers["x-content-type-options"] == "nosniff"
    )
    bad_type = api.client.post(
        f"/api/v1/missions/{mid}/evidence-objects",
        content=b"MZ",
        headers={**headers, "Content-Type": "application/x-msdownload"},
    )
    assert bad_type.status_code == 422
    store = LocalEvidenceStore(tmp_path / "ev", max_bytes=10, media_types=("text/plain",))
    with pytest.raises(Unprocessable):
        store.put(uuid4(), b"x" * 11, "text/plain")
    for key in (
        "../../etc/passwd",
        f"{uuid4()}/../../secret",
        "C:/Windows/win.ini",
        f"{uuid4()}/{'g' * 64}",
    ):
        with pytest.raises(NotFound):
            store.read(key)
