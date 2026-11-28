"""In the development environment the API never invents a seed. Other environments are unchanged."""

from pathlib import Path

from backend_support import PASSWORD, create_user, make_settings
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.core.permissions import GlobalRole


def test_development_missions_need_an_explicit_unprotected_seed(
    db_path: Path, tmp_path: Path
) -> None:
    for environment, missing, reserved in (("development", 422, 422), ("testing", 201, 201)):
        settings = make_settings(db_path, tmp_path, environment=environment)
        create_user(settings, f"coord-{environment}", GlobalRole.COORDINATOR)
        with TestClient(create_app(settings)) as client:
            token = client.post("/api/v1/auth/login", json={
                "username": f"coord-{environment}", "password": PASSWORD}).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            def create(headers: dict[str, str] = headers, client: TestClient = client,
                       **config: object) -> int:
                body = {"name": "seed check", "config": {
                    "scenario_id": "flood_basic", "agents": 2, **config}}
                return int(client.post("/api/v1/missions", json=body, headers=headers).status_code)

            assert create() == missing
            assert create(seed=12900) == 201
            if environment == "development":
                assert create(seed=900000) == reserved
