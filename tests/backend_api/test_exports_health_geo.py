"""Research exports, health probes, geospatial validation and optional PostGIS verification."""

import os
from pathlib import Path

import pytest
from backend_support import Api, migrate
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.application import create_app
from backend.core.config import BackendSettings
from backend.core.permissions import GlobalRole
from backend.schemas import Location


def test_exports_separate_ground_truth_and_are_audited(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator)
    mid = mission["id"]
    api.post(f"/api/v1/missions/{mid}/start", coordinator)
    api.wait_status(mid, coordinator, {"completed"})
    operational = api.get(f"/api/v1/missions/{mid}/exports/operational", coordinator).json()
    assert "evaluator_ground_truth" not in operational
    repro = operational["reproducibility"]
    assert repro["seed"] == 42 and repro["agents"] == 3 and repro["scenario_id"] == "flood_basic"
    assert (
        repro["runs"][0]["software_version"]
        and repro["runs"][0]["model2_settings"]["mode"] == "fusion"
    )
    assert api.get(f"/api/v1/missions/{mid}/exports/research", coordinator).status_code == 403
    api.user("res", GlobalRole.RESEARCHER)
    api.login("res")
    api.post(
        f"/api/v1/missions/{mid}/members",
        coordinator,
        {"user_id": str(api.ids["res"]), "role": "researcher"},
    )
    research = api.get(f"/api/v1/missions/{mid}/exports/research", "res").json()
    truth = research["evaluator_ground_truth"]["runs"][0]
    assert {"people_observed", "missed", "coverage"} <= set(truth)
    csv = api.get(f"/api/v1/missions/{mid}/exports/operational", "res", params={"format": "csv"})
    assert csv.headers["content-type"].startswith("text/csv") and csv.text.startswith(
        "section,key,value"
    )
    audit = api.get(f"/api/v1/missions/{mid}/audit", coordinator, params={"limit": 200}).json()[
        "items"
    ]
    assert {"export.operational", "export.research"} <= {a["action"] for a in audit}


def test_health_probes(
    api: Api, coordinator: str, tmp_path: Path, settings: BackendSettings
) -> None:
    assert api.client.get("/health/live").json() == {"status": "ok"}
    ready = api.client.get("/health/ready")
    assert ready.status_code == 200 and ready.json() == {"status": "ready"}
    unmigrated = settings.model_copy(
        update={"database_url": f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"}
    )
    with TestClient(create_app(unmigrated)) as client:
        assert client.get("/health/ready").status_code == 503
        assert client.get("/health/live").status_code == 200
    api.user("root", GlobalRole.ADMINISTRATOR)
    api.login("root")
    detail = api.get("/api/v1/system/health", "root").json()
    assert detail["database"]["migration_revision"] == "0001" and detail["status"] == "ok"
    metrics = api.get("/api/v1/system/metrics", "root").json()
    assert metrics["api"]["requests_total"] > 0 and "p95" in metrics["api"]["latency_ms"]
    docs = api.client.get("/openapi.json").json()
    assert "/api/v1/recommendations/{rec_id}/approve" in docs["paths"]
    assert len(docs["paths"]) > 60


def test_location_reference_systems() -> None:
    local = Location(crs="swarm-aid:grid", x=3, y=4, units="cell", uncertainty=0.5)
    assert local.units == "cell"
    Location(crs="EPSG:4326", x=-122.4, y=37.8, units="degree")
    for x, y in ((200, 10), (10, 95)):
        with pytest.raises(ValidationError, match="EPSG:4326"):
            Location(crs="EPSG:4326", x=x, y=y, units="degree")
    with pytest.raises(ValidationError):
        Location(crs="swarm-aid:grid", x=1, y=1, units="cell", uncertainty=-1)


def test_bounding_box_query_uses_local_grid(api: Api, coordinator: str) -> None:
    mission = api.mission(coordinator)
    mid = mission["id"]
    api.post(f"/api/v1/missions/{mid}/start", coordinator)
    api.wait_status(mid, coordinator, {"completed"})
    everything = api.get(
        f"/api/v1/missions/{mid}/observations", coordinator, params={"limit": 500}
    ).json()
    box = api.get(
        f"/api/v1/missions/{mid}/observations",
        coordinator,
        params={"bbox": "0,0,3,3", "limit": 500},
    ).json()
    assert 0 < box["total"] < everything["total"]
    assert all(0 <= o["location"]["x"] <= 3 and 0 <= o["location"]["y"] <= 3 for o in box["items"])
    assert (
        api.get(
            f"/api/v1/missions/{mid}/observations", coordinator, params={"bbox": "a,b"}
        ).status_code
        == 422
    )


POSTGRES_URL = os.environ.get("SWARM_TEST_POSTGRES_URL")


@pytest.mark.skipif(
    not POSTGRES_URL, reason="SWARM_TEST_POSTGRES_URL not set; PostgreSQL/PostGIS unverified"
)
def test_postgis_migration_geometry_and_spatial_query() -> None:  # pragma: no cover - needs PostGIS
    from sqlalchemy import create_engine, text

    assert POSTGRES_URL is not None
    migrate(POSTGRES_URL)
    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        indexes = {
            r[0]
            for r in connection.execute(
                text("SELECT indexname FROM pg_indexes WHERE indexname LIKE '%_geom'")
            )
        }
        assert {
            "ix_observations_geom",
            "ix_incidents_geom",
            "ix_hazards_geom",
            "ix_agents_geom",
        } <= indexes
        srid = connection.execute(
            text("SELECT Find_SRID('public', 'observations', 'geom')")
        ).scalar()
        assert srid == 0
        within = connection.execute(
            text(
                "SELECT ST_DWithin(ST_SetSRID(ST_MakePoint(1, 1), 0), ST_SetSRID(ST_MakePoint(2, 1), 0), 1.0)"
            )
        ).scalar()
        assert within is True
    engine.dispose()
