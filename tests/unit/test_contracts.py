from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from agents.shared.domain import Action, Finding, Incident, Observation, SensorFrame
from communication.messages import Envelope
from configs.settings import load_settings

REF = str(UUID(int=1))
BASE = {
    "schema_version": "1.0",
    "message_id": REF,
    "source": "d1",
    "destination": "command",
    "mission_id": REF,
    "session_id": REF,
    "timestamp": "2000-01-01T00:00:00Z",
    "sent_ms": 10,
    "sequence": 0,
    "priority": "routine",
    "correlation_id": REF,
    "expires_ms": 20,
}
EVIDENCE = {
    "evidence_id": REF,
    "origin": "d1",
    "captured_ms": 5,
    "modality": "thermal",
    "artifact_key": "synthetic-1",
}
OBS = {"observation_id": REF, "observed_ms": 5, "confidence": 0.5, "evidence": [EVIDENCE]}
INC = {
    "incident_id": REF,
    "revision": 1,
    "category": "possible_human",
    "reports": [REF],
    "uncertainties": ["location unknown"],
}
CASES: dict[str, dict[str, object]] = {
    "registration": {"role": "drone", "session_id": REF},
    "heartbeat": {"state": "active"},
    "environmental_observation": {"observation": OBS, "feature": "rain"},
    "possible_human_detection": {"observation": OBS},
    "hazard_detection": {"observation": OBS, "hazard": "blocked_cell"},
    "incident_update": {"incident": INC},
    "evidence_reference": {"evidence": EVIDENCE},
    "mission_instruction": {"task_id": REF, "action": {"intent": "hold"}},
    "task_status": {"task_id": REF, "status": "accepted"},
    "agent_health": {"battery_fraction": 0.7, "degraded_sensors": []},
    "acknowledgement": {"acknowledged_id": REF, "outcome": "accepted"},
    "connection_loss": {"peer": "command", "last_seen_ms": 8},
    "reconnection": {"peer": "command", "session_id": REF, "last_contiguous_sequence": None},
    "human_approval": {
        "recommendation_id": REF,
        "incident_id": REF,
        "revision": 1,
        "decision": "reject",
        "reason": "ambiguous",
    },
    "human_override": {"action": "pause", "reason": "manual review"},
    "error_report": {"code": "unsupported_version", "retryable": False},
}


@pytest.mark.parametrize("kind", CASES)
def test_wire_round_trip(kind: str) -> None:
    msg = Envelope.model_validate({**BASE, "payload": {"message_type": kind, **CASES[kind]}})
    assert Envelope.model_validate_json(msg.model_dump_json()) == msg


@pytest.mark.parametrize(
    "patch",
    [
        {"schema_version": "2.0"},
        {"priority": "immediate"},
        {"sequence": -1},
        {"timestamp": "2000-01-01T00:00:00"},
        {"expires_ms": 10},
        {"expires_ms": None},
        {"payload": {"message_type": "unknown"}},
        {"ground_truth": {}},
    ],
)
def test_reject_invalid_envelope(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Envelope.model_validate(
            {
                **BASE,
                "payload": {"message_type": "human_override", **CASES["human_override"]},
                **patch,
            }
        )


def test_evidence_and_authority_contracts() -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate({**OBS, "evidence": []})
    with pytest.raises(ValidationError):
        Incident.model_validate({**INC, "category": "human_confirmed"})
    with pytest.raises(ValidationError):
        Action.model_validate({"intent": "survey"})


def test_config(tmp_path: Path) -> None:
    default = Path(__file__).resolve().parents[2] / "configs" / "default.toml"
    assert load_settings(default).schema_version == "1.0"
    invalid = tmp_path / "invalid.toml"
    invalid.write_text(default.read_text() + "\nunknown = 0\n")
    with pytest.raises(ValidationError):
        load_settings(invalid)


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": True},
        {"source": "   "},
        {"sent_ms": "10"},
    ],
)
def test_invalid_wire_scalars(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Envelope.model_validate(
            {**BASE, **changes, "payload": {"message_type": "heartbeat", "state": "ready"}}
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"confidence": True},
        {"evidence": [EVIDENCE, EVIDENCE]},
        {"observed_ms": 4},
    ],
)
def test_observation_lineage(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate({**OBS, **changes})


@pytest.mark.parametrize(
    "payload",
    [
        {"message_type": "possible_human_detection", "observation": {**OBS, "observed_ms": 11}},
        {"message_type": "evidence_reference", "evidence": {**EVIDENCE, "captured_ms": 11}},
        {"message_type": "connection_loss", "peer": "command", "last_seen_ms": 11},
        {"message_type": "registration", "role": "operator", "session_id": str(UUID(int=2))},
        {"message_type": "error_report", "code": "test", "retryable": "yes"},
    ],
)
def test_inconsistent_payload(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Envelope.model_validate({**BASE, "payload": payload})


@pytest.mark.parametrize(
    ("revision", "expiry", "valid"), [(1, 11, True), (2, 11, False), (1, 10, False)]
)
def test_proposal_publication(revision: int, expiry: int, valid: bool) -> None:
    proposal = {
        "incident_id": REF,
        "incident_revision": revision,
        "recommendation_id": REF,
        "evidence_ids": [REF],
        "request": "inspect_evidence",
        "unknowns": [],
        "expires_ms": expiry,
    }
    envelope = {
        **BASE,
        "payload": {"message_type": "incident_update", "incident": INC, "recommendation": proposal},
    }
    if valid:
        assert Envelope.model_validate(envelope).payload.message_type == "incident_update"
    else:
        with pytest.raises(ValidationError):
            Envelope.model_validate(envelope)


def test_scoped_sensor_frame() -> None:
    frame = {
        "agent_id": "d1",
        "tick_ms": 5,
        "cell": None,
        "battery_fraction": 1,
        "samples": [EVIDENCE],
    }
    assert SensorFrame.model_validate(frame).samples[0].origin == "d1"
    invalid_frames: tuple[dict[str, object], ...] = (
        {"agent_id": "d2"},
        {"tick_ms": 4},
        {"hidden_victims": []},
    )
    for changes in invalid_frames:
        with pytest.raises(ValidationError):
            SensorFrame.model_validate({**frame, **changes})


def test_classified_findings() -> None:
    assert (
        Finding.model_validate({"observation": OBS, "kind": "hazard", "label": "blocked"}).label
        == "blocked"
    )
    with pytest.raises(ValidationError):
        Finding.model_validate({"observation": OBS, "kind": "hazard"})
    with pytest.raises(ValidationError):
        Finding.model_validate({"observation": OBS, "kind": "possible_human", "label": "confirmed"})


def test_toml_typed_limits(tmp_path: Path) -> None:
    settings = (Path(__file__).resolve().parents[2] / "configs" / "default.toml").read_text(
        encoding="utf-8"
    )
    path = tmp_path / "scenario.toml"
    for field, invalid in (
        ("tick_ms = 100", "tick_ms = true"),
        ("seed = 42", "seed = -1"),
        ('schema_version = "1.0"', 'schema_version = "9"'),
        ("battery_reserve = 0.20", "battery_reserve = 1.5"),
    ):
        path.write_text(settings.replace(field, invalid), encoding="utf-8")
        with pytest.raises(ValidationError):
            load_settings(path)
