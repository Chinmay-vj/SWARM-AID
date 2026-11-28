"""Backend fixtures. Every test gets a fresh SQLite file built by the real Alembic migration
(or, opt-in, an emptied PostgreSQL database)."""

import os
import shutil
import tempfile
import time
from collections.abc import Callable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.core.config import BackendSettings
from backend.core.permissions import GlobalRole
from backend.database.session import Database, build_engine

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "synthetic-test-password"
SECRET = "test-only-signing-secret-0123456789abcdef"


def migrate(url: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.cmd_opts = None
    config.attributes["url"] = url
    from sqlalchemy import create_engine

    engine = create_engine(url)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    engine.dispose()


@pytest.fixture(scope="session")
def sqlite_dir() -> Iterator[Path]:
    """SQLite files live in the system temp directory: on some Windows hosts the repository
    drive makes each journaled write ~25x slower, which would dominate test time."""
    with tempfile.TemporaryDirectory(
        prefix="swarm-aid-db-", ignore_cleanup_errors=True
    ) as directory:
        yield Path(directory)


@pytest.fixture(scope="session")
def template_db(sqlite_dir: Path) -> Path:
    path = sqlite_dir / "template.db"
    migrate(f"sqlite:///{path.as_posix()}")
    return path


# Opt-in: run the backend API tests against a disposable PostgreSQL database instead of SQLite.
# Both variables are required; every application table is emptied before each test.
POSTGRES_BACKEND = (
    os.environ.get("SWARM_TEST_POSTGRES_URL")
    if os.environ.get("SWARM_TEST_BACKEND_ON_POSTGRES") == "1"
    else None
)


@lru_cache(maxsize=1)
def _migrated_postgres(url: str) -> str:
    migrate(url)
    return url


def reset_postgres(url: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(_migrated_postgres(url))
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '20s'"))
        tables = [
            row[0]
            for row in connection.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename NOT IN ('alembic_version', 'spatial_ref_sys')"
                )
            )
        ]
        names = ", ".join(f'"{table}"' for table in tables)
        connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    engine.dispose()


def make_settings(db_path: Path, tmp_path: Path, **overrides: Any) -> BackendSettings:
    values: dict[str, Any] = {
        "environment": "testing",
        "database_url": POSTGRES_BACKEND or f"sqlite:///{db_path.as_posix()}",
        "jwt_secret": SECRET,
        "simulation_tick_delay_ms": 0,
        "evidence_dir": tmp_path / "evidence",
        "websocket_heartbeat_seconds": 0.2,
        "websocket_auth_timeout_seconds": 1.0,
        "login_attempts_per_minute": 50,
        "snapshot_every_ticks": 5,
    }
    values.update(overrides)
    return BackendSettings(_env_file=None, **values)


@pytest.fixture
def db_path(template_db: Path, sqlite_dir: Path) -> Iterator[Path]:
    if POSTGRES_BACKEND:
        reset_postgres(POSTGRES_BACKEND)
    target = sqlite_dir / f"{uuid4().hex}.db"
    shutil.copyfile(template_db, target)
    yield target
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(f"{target}{suffix}").unlink(missing_ok=True)
        except PermissionError:  # still open on Windows; the session directory is removed later
            pass


@pytest.fixture
def settings(db_path: Path, tmp_path: Path) -> BackendSettings:
    return make_settings(db_path, tmp_path)


@pytest.fixture
def app(settings: BackendSettings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def create_user(settings: BackendSettings, username: str, role: GlobalRole) -> UUID:
    from backend.services.auth import AuthService

    db = Database(build_engine(settings))
    try:
        with db.transaction() as session:
            user = AuthService(db, settings).create_user(session, username, PASSWORD, role)
            return user.id
    finally:
        db.dispose()


class Api:
    """Small helper around TestClient with per-user bearer tokens."""

    def __init__(self, client: TestClient, settings: BackendSettings) -> None:
        self.client = client
        self.settings = settings
        self.tokens: dict[str, str] = {}
        self.ids: dict[str, UUID] = {}

    def user(self, username: str, role: GlobalRole = GlobalRole.OBSERVER) -> UUID:
        self.ids[username] = create_user(self.settings, username, role)
        return self.ids[username]

    def login(self, username: str) -> dict[str, Any]:
        response = self.client.post(
            "/api/v1/auth/login", json={"username": username, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        self.tokens[username] = body["access_token"]
        return body

    def headers(self, username: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[username]}"} if username else {}

    def get(self, path: str, as_: str | None, **kwargs: Any) -> Any:
        return self.client.get(path, headers=self.headers(as_), **kwargs)

    def post(self, path: str, as_: str | None, json: Any = None, **kwargs: Any) -> Any:
        return self.client.post(path, headers=self.headers(as_), json=json, **kwargs)

    def patch(self, path: str, as_: str | None, json: Any = None) -> Any:
        return self.client.patch(path, headers=self.headers(as_), json=json)

    def mission(self, as_: str, **config: Any) -> dict[str, Any]:
        body = {
            "name": "synthetic flood",
            "config": {"scenario_id": "flood_basic", "agents": 3, "seed": 42, **config},
        }
        response = self.post("/api/v1/missions", as_, body)
        assert response.status_code == 201, response.text
        result: dict[str, Any] = response.json()
        return result

    def wait(self, predicate: Callable[[], bool], timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.1)
        raise AssertionError("condition not reached before timeout")

    def wait_status(
        self, mission_id: str, as_: str, statuses: set[str], timeout: float = 30.0
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}

        def done() -> bool:
            nonlocal result
            result = self.get(f"/api/v1/missions/{mission_id}", as_).json()
            return result["status"] in statuses

        self.wait(done, timeout)
        return result


@pytest.fixture
def api(client: TestClient, settings: BackendSettings) -> Api:
    return Api(client, settings)


@pytest.fixture
def coordinator(api: Api) -> str:
    api.user("coord", GlobalRole.COORDINATOR)
    api.login("coord")
    return "coord"


def paused_with_review(api: Api, user: str, **config: Any) -> tuple[str, dict[str, Any]]:
    """Start a mission, wait for a recommendation awaiting review, then pause the simulation."""
    mission = api.mission(user, **({"agents": 6} | config))
    mid = mission["id"]
    assert api.post(f"/api/v1/missions/{mid}/start", user).status_code == 200
    queue: list[dict[str, Any]] = []

    def has_review() -> bool:
        nonlocal queue
        queue = api.get(f"/api/v1/missions/{mid}/review-queue", user).json()
        return bool(queue)

    api.wait(has_review)
    assert api.post(f"/api/v1/missions/{mid}/pause", user).status_code == 200
    queue = api.get(f"/api/v1/missions/{mid}/review-queue", user).json()
    assert queue, "review expired before pause"
    return mid, queue[0]


def decision_status(api: Api, mission_id: str, user: str, decision_id: str) -> str:
    page = api.get(f"/api/v1/missions/{mission_id}/human-decisions", user, params={"limit": 500})
    for item in page.json()["items"]:
        if item["id"] == decision_id:
            return str(item["status"])
    raise AssertionError("decision not found")


@pytest.fixture
def slow_settings(db_path: Path, tmp_path: Path) -> BackendSettings:
    """Ticks paced at 40 ms so tests can act while a mission runs."""
    return make_settings(db_path, tmp_path, simulation_tick_delay_ms=40)
