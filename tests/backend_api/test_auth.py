"""Authentication: passwords, token validation, rotation, revocation and identity separation."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest
from backend_support import PASSWORD, SECRET, Api, make_settings
from pydantic import ValidationError

from backend.core.config import BackendSettings
from backend.core.permissions import GlobalRole
from backend.core.security import HUMAN_AUDIENCE, MACHINE_AUDIENCE, TokenService


def test_login_success_failure_and_me(api: Api) -> None:
    api.user("alice", GlobalRole.OBSERVER)
    bad = api.client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "wrong-password!"}
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_credentials"
    assert "request_id" in bad.json()["error"]
    unknown = api.client.post(
        "/api/v1/auth/login", json={"username": "nobody", "password": PASSWORD}
    )
    assert unknown.status_code == 401
    tokens = api.login("alice")
    assert tokens["token_type"] == "bearer"
    me = api.get("/api/v1/auth/me", "alice").json()
    assert me["subject"] == "alice" and me["kind"] == "human" and me["global_role"] == "observer"
    assert api.client.get("/api/v1/auth/me").status_code == 401


def test_invalid_expired_and_wrong_purpose_tokens(api: Api, settings: BackendSettings) -> None:
    uid = api.user("bob")
    tokens = api.login("bob")
    service = TokenService(settings)

    def me(token: str) -> Any:
        return api.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    expired, _ = service.issue(str(uid), HUMAN_AUDIENCE, "access", timedelta(seconds=-5))
    assert me(expired).json()["error"]["code"] == "token_expired"
    assert me(tokens["refresh_token"]).status_code == 401  # refresh token used as access
    forged = jwt.encode(
        {"sub": str(uid), "aud": HUMAN_AUDIENCE, "iss": settings.jwt_issuer, "pur": "access"},
        "attacker-secret-attacker-secret-0000",
        algorithm="HS256",
    )
    assert me(forged).status_code == 401
    unsigned = jwt.encode(
        {"sub": str(uid), "aud": HUMAN_AUDIENCE, "pur": "access"}, None, algorithm="none"
    )
    assert me(unsigned).status_code == 401
    wrong_issuer = TokenService(settings.model_copy(update={"jwt_issuer": "elsewhere"}))
    other, _ = wrong_issuer.issue(str(uid), HUMAN_AUDIENCE, "access", timedelta(minutes=5))
    assert me(other).status_code == 401
    machine_aud, _ = service.issue(str(uid), MACHINE_AUDIENCE, "access", timedelta(minutes=5))
    assert me(machine_aud).status_code == 401  # human subject in machine audience
    assert me("not-a-jwt").status_code == 401


def test_refresh_rotation_reuse_detection_and_logout(api: Api) -> None:
    api.user("carol")
    first = api.login("carol")
    rotated = api.client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    reuse = api.client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401 and reuse.json()["error"]["code"] == "token_reused"
    # Reuse revoked the whole family, including the newest token.
    assert (
        api.client.post(
            "/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}
        ).status_code
        == 401
    )
    third = api.login("carol")
    logout = api.post("/api/v1/auth/logout", "carol", {"refresh_token": third["refresh_token"]})
    assert logout.status_code == 204
    assert (
        api.client.post(
            "/api/v1/auth/refresh", json={"refresh_token": third["refresh_token"]}
        ).status_code
        == 401
    )


def test_deactivated_account_and_admin_user_management(api: Api) -> None:
    api.user("root", GlobalRole.ADMINISTRATOR)
    api.login("root")
    created = api.post(
        "/api/v1/users",
        "root",
        {"username": "dave", "password": PASSWORD, "global_role": "operator"},
    )
    assert created.status_code == 201 and "password" not in created.text
    api.login("dave")
    assert (
        api.post(
            "/api/v1/users",
            "dave",
            {"username": "eve", "password": PASSWORD, "global_role": "administrator"},
        ).status_code
        == 403
    )
    dup = api.post(
        "/api/v1/users",
        "root",
        {"username": "dave", "password": PASSWORD, "global_role": "observer"},
    )
    assert dup.status_code == 409
    weak = api.post(
        "/api/v1/users",
        "root",
        {"username": "weak", "password": "short", "global_role": "observer"},
    )
    assert weak.status_code == 422
    assert api.post(f"/api/v1/users/{created.json()['id']}/deactivate", "root").status_code == 200
    assert api.get("/api/v1/auth/me", "dave").json()["error"]["code"] == "account_inactive"
    assert (
        api.client.post(
            "/api/v1/auth/login", json={"username": "dave", "password": PASSWORD}
        ).status_code
        == 401
    )


def test_machine_identity_is_separate_and_revocable(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator)
    cred = api.post(
        f"/api/v1/missions/{mission['id']}/agent-credentials", coordinator, {"agent_key": "d0"}
    )
    assert cred.status_code == 201
    body = cred.json()
    bad = api.client.post(
        "/api/v1/auth/machine-token",
        json={"credential_id": body["credential_id"], "secret": "nope"},
    )
    assert bad.status_code == 401
    token = api.client.post(
        "/api/v1/auth/machine-token",
        json={"credential_id": body["credential_id"], "secret": body["secret"]},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = api.client.get("/api/v1/auth/me", headers=headers).json()
    assert me["kind"] == "agent" and me["subject"] == "d0" and me["global_role"] is None
    # A machine identity cannot use human-only endpoints or log out a human session.
    assert api.client.post(
        f"/api/v1/alerts/{mission['id']}/acknowledge", headers=headers
    ).status_code in (403, 404)
    assert (
        api.client.post(
            "/api/v1/missions",
            headers=headers,
            json={"name": "x", "config": {"scenario_id": "flood_basic"}},
        ).status_code
        == 403
    )
    unknown_agent = api.post(
        f"/api/v1/missions/{mission['id']}/agent-credentials", coordinator, {"agent_key": "d99"}
    )
    assert unknown_agent.status_code == 422
    from sqlalchemy import update

    from backend.database import models as m

    with api.client.app.state.container.db.transaction() as session:  # type: ignore[attr-defined]
        session.execute(update(m.MachineCredential).values(is_active=False))
    revoked = api.client.get("/api/v1/auth/me", headers=headers)
    assert revoked.status_code == 401 and revoked.json()["error"]["code"] == "credential_revoked"


def test_login_rate_limit(tmp_path: Path, db_path: Path) -> None:
    from fastapi.testclient import TestClient

    from backend.application import create_app

    settings = make_settings(db_path, tmp_path, login_attempts_per_minute=3)
    with TestClient(create_app(settings)) as client:
        codes = [
            client.post("/api/v1/auth/login", json={"username": "x", "password": "y"}).status_code
            for _ in range(5)
        ]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]


def test_settings_require_strong_secret_and_production_rules(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="SWARM_JWT_SECRET"):
        BackendSettings(_env_file=None, jwt_secret="short")
    with pytest.raises(ValidationError):
        BackendSettings(_env_file=None)
    with pytest.raises(ValidationError, match="PostgreSQL"):
        BackendSettings(_env_file=None, jwt_secret=SECRET, environment="production")
    with pytest.raises(ValidationError, match="debug"):
        BackendSettings(
            _env_file=None,
            jwt_secret=SECRET,
            environment="production",
            debug=True,
            database_url="postgresql+psycopg://u@localhost/db",
        )
    ok = BackendSettings(
        _env_file=None,
        jwt_secret=SECRET,
        environment="production",
        database_url="postgresql+psycopg://u@localhost/db",
    )
    assert "test-only" not in repr(ok)  # SecretStr never prints the secret
