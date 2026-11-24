"""Input hardening, injection resistance, redaction, error hygiene and request limits."""

import json
import logging
from pathlib import Path

import pytest
from backend_support import PASSWORD, Api, make_settings
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.core.logging import JsonFormatter, redact


def test_sql_injection_strings_are_treated_as_data(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator)
    mid = mission["id"]
    for payload in ("' OR 1=1 --", "d0'; DROP TABLE missions; --", '" OR ""="'):
        response = api.get(
            f"/api/v1/missions/{mid}/observations", coordinator, params={"reporter": payload}
        )
        assert response.status_code == 200 and response.json()["total"] == 0
    login = api.client.post(
        "/api/v1/auth/login", json={"username": "' OR '1'='1", "password": "' OR '1'='1"}
    )
    assert login.status_code == 401
    assert api.get(f"/api/v1/missions/{mid}", coordinator).status_code == 200  # table intact


def test_scenario_identifiers_cannot_reach_the_filesystem(api: Api, coordinator: str) -> None:
    for scenario in (
        "../../alembic",
        "C:/Windows/win.ini",
        "flood_basic.json",
        "..\\configs\\model2",
        "does_not_exist",
    ):
        response = api.post(
            "/api/v1/missions", coordinator, {"name": "x", "config": {"scenario_id": scenario}}
        )
        assert response.status_code == 422, scenario
    too_many = api.post(
        "/api/v1/missions",
        coordinator,
        {"name": "x", "config": {"scenario_id": "flood_basic", "agents": 500}},
    )
    assert too_many.status_code == 422


def test_errors_are_structured_and_leak_nothing(api: Api, coordinator: str) -> None:
    missing = api.get("/api/v1/missions/not-a-uuid", coordinator)
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "validation_error"
    unknown = api.get("/api/v1/nope", coordinator)
    assert unknown.status_code == 404 and set(unknown.json()["error"]) == {
        "code",
        "message",
        "request_id",
        "details",
    }
    no_token = api.client.get("/api/v1/missions")
    assert no_token.status_code == 401 and no_token.headers["www-authenticate"] == "Bearer"
    echoed = api.client.get("/health/live", headers={"X-Request-ID": "client-request-0001"})
    assert echoed.headers["x-request-id"] == "client-request-0001"
    rejected_id = api.client.get("/health/live", headers={"X-Request-ID": "bad id\nwith newline"})
    assert rejected_id.headers["x-request-id"] != "bad id\nwith newline"
    for response in (missing, unknown, no_token):
        assert "Traceback" not in response.text and "sqlalchemy" not in response.text.lower()


def test_request_body_limit(tmp_path: Path, db_path: Path) -> None:
    settings = make_settings(db_path, tmp_path, max_request_bytes=2_000)
    with TestClient(create_app(settings)) as client:
        big = client.post(
            "/api/v1/auth/login",
            content=b"{" + b" " * 5_000 + b"}",
            headers={"Content-Type": "application/json"},
        )
        assert big.status_code == 413 and big.json()["error"]["code"] == "payload_too_large"


def test_credentials_are_redacted_from_logs_and_audit(api: Api, coordinator: str) -> None:
    secret = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl"
    record = logging.LogRecord(
        "backend", logging.INFO, __file__, 1, f"Authorization: Bearer {secret}", None, None
    )
    record.data = {"password": PASSWORD, "nested": {"refresh_token": "abc"}, "safe": 1}
    line = json.loads(JsonFormatter().format(record))
    assert secret not in json.dumps(line) and PASSWORD not in json.dumps(line)
    assert line["data"] == {
        "password": "[REDACTED]",
        "nested": {"refresh_token": "[REDACTED]"},
        "safe": 1,
    }
    assert redact({"api_key": "k", "items": [{"secret": "s"}]}) == {
        "api_key": "[REDACTED]",
        "items": [{"secret": "[REDACTED]"}],
    }
    api.client.post(
        "/api/v1/auth/login", json={"username": coordinator, "password": "wrong-but-sensitive-1"}
    )
    api.user(
        "root",
        __import__("backend.core.permissions", fromlist=["GlobalRole"]).GlobalRole.ADMINISTRATOR,
    )
    api.login("root")
    audit = api.get("/api/v1/audit", "root", params={"limit": 500}).json()
    dumped = json.dumps(audit)
    assert "wrong-but-sensitive-1" not in dumped and PASSWORD not in dumped
    assert api.tokens[coordinator] not in dumped
    assert any(a["action"] == "auth.login" and a["outcome"] == "failure" for a in audit["items"])


def test_configuration_errors_never_echo_values(monkeypatch: pytest.MonkeyPatch) -> None:

    from backend.core.config import ConfigurationError, load_settings

    monkeypatch.setenv("SWARM_DATABASE_URL", "postgresql+psycopg://u:LeakyPassword123@h/db")
    monkeypatch.delenv("SWARM_JWT_SECRET", raising=False)
    monkeypatch.chdir(Path(__file__).parent)  # no .env here
    with pytest.raises(ConfigurationError) as missing:
        load_settings()
    assert "SWARM_JWT_SECRET" in str(missing.value) and "LeakyPassword123" not in str(missing.value)
    monkeypatch.setenv("SWARM_JWT_SECRET", "short")
    with pytest.raises(ConfigurationError) as weak:
        load_settings()
    assert "32 characters" in str(weak.value) and "LeakyPassword123" not in str(weak.value)
