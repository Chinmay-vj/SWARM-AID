"""Read-only system status for scripts/status_system.ps1.

Probes the public health endpoints, reads the database directly (read-only) for mission,
Model 2 and communication state persisted by the running backend, and checks the dashboard.
No credentials are needed and nothing is changed.
"""

import json
import urllib.error
import urllib.request
from typing import Any

from orchestration.serve import CONTROL_DIR, STATE_FILE

DASHBOARD_URL = "http://127.0.0.1:5173"


def probe(url: str, timeout: float = 2.0) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # localhost only
            return {"reachable": True, "status": response.status}
    except urllib.error.HTTPError as exc:
        return {"reachable": True, "status": exc.code}
    except (urllib.error.URLError, OSError) as exc:
        return {"reachable": False, "error": type(exc).__name__}


def database_status() -> dict[str, Any]:
    from sqlalchemy import select

    from backend.api.v1.system import HEAD_REVISION
    from backend.core.config import ConfigurationError, load_settings
    from backend.database import models as m
    from backend.database.session import Database, build_engine

    try:
        settings = load_settings()
    except ConfigurationError as exc:
        return {"ready": False, "error": str(exc)}
    db = Database(build_engine(settings))
    try:
        if not db.ping():
            return {"ready": False, "dialect": db.engine.dialect.name, "error": "unreachable"}
        revision = db.migration_revision()
        missions: list[dict[str, Any]] = []
        if revision == HEAD_REVISION:
            with db.read() as session:
                rows = session.execute(
                    select(m.Mission, m.MissionRuntime)
                    .join(m.MissionRuntime, m.MissionRuntime.mission_id == m.Mission.id)
                    .where(m.Mission.status.in_(("running", "paused")))
                ).all()
                missions = [
                    {
                        "mission_id": str(mission.id),
                        "name": mission.name,
                        "status": mission.status,
                        "model2_state": runtime.model2_state,
                        "communication_state": runtime.communication_state,
                        "last_sim_ms": runtime.last_sim_ms,
                    }
                    for mission, runtime in rows
                ]
        return {
            "ready": revision == HEAD_REVISION,
            "dialect": db.engine.dialect.name,
            "migration_revision": revision,
            "expected_revision": HEAD_REVISION,
            "active_missions": missions,
        }
    finally:
        db.dispose()


def system_status() -> dict[str, Any]:
    from backend.core.config import ConfigurationError, load_settings

    try:
        settings = load_settings()
        base = f"http://{settings.host}:{settings.port}"
    except ConfigurationError:
        base = "http://127.0.0.1:8000"
    state_path = CONTROL_DIR / STATE_FILE
    owned = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else None
    return {
        "backend": {
            "url": base,
            "live": probe(f"{base}/health/live"),
            "ready": probe(f"{base}/health/ready"),
            "managed_process": owned,
        },
        "database": database_status(),
        "dashboard": {"url": DASHBOARD_URL, "probe": probe(DASHBOARD_URL)},
        "event_stream": {
            "endpoint": base.replace("http", "ws", 1) + "/ws/v1/missions/{mission_id}",
            "note": "Connection counts and queue depth: GET /api/v1/system/health (admin).",
        },
    }
