"""Phase 8 dashboard catalogs: scenario configuration and stored experiment comparisons."""

import csv
import json
from pathlib import Path

from backend_support import Api, make_settings
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.core.permissions import GlobalRole

GROUND_TRUTH_FIELDS = {"terrain", "people", "hazards", "events", "sectors", "hidden_people"}


def test_scenarios_list_configuration_without_ground_truth(api: Api, coordinator: str) -> None:
    response = api.get("/api/v1/scenarios", coordinator)
    assert response.status_code == 200
    scenarios = {s["scenario_id"]: s for s in response.json()}
    assert {"flood_basic", "wildfire_basic", "earthquake_basic"} <= set(scenarios)
    flood = scenarios["flood_basic"]
    assert flood["disaster"] == "flood" and flood["default_agents"] >= 1
    assert flood["width"] > 0 and flood["height"] > 0 and flood["tick_ms"] > 0
    assert "communication_outage" in scenarios["flood_outage"]["faults"]
    for item in scenarios.values():
        assert not GROUND_TRUTH_FIELDS & set(item)
    assert api.get("/api/v1/scenarios", None).status_code == 401


def write_experiment(
    root: Path, collection: str, name: str, header: list[str], rows: list[list[object]]
) -> None:
    folder = root / collection / name
    folder.mkdir(parents=True)
    with (folder / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)
    (folder / "episode-0.json").write_text(
        json.dumps({"simulator_version": "0.2", "definitions": {"coverage": "fraction"}}),
        encoding="utf-8",
    )


def test_experiments_require_research_role_and_return_measured_rows(
    db_path: Path, tmp_path: Path
) -> None:
    root = tmp_path / "results"
    coord_id, command_id = "a" * 32, "b" * 32
    write_experiment(
        root,
        "phase5/baselines",
        coord_id,
        ["scenario", "agents", "seed", "policy", "coverage", "tasks_issued"],
        [
            ["flood_basic", 3, 42, "independent", 0.1, 0],
            ["flood_basic", 3, 43, "fixed_sector", 0.5, 15],
        ],
    )
    write_experiment(
        root,
        "phase6",
        command_id,
        [
            "scenario",
            "agents",
            "seed",
            "mode",
            "observations",
            "incidents",
            "operator_updates",
            "decisions_sent",
        ],
        [["flood_basic", 3, 42, "fusion", 87, 12, 40, 0]],
    )
    (root / "not-an-experiment").mkdir()
    (root / "not-an-experiment" / "comparison.csv").write_text("scenario\nx\n", encoding="utf-8")
    settings = make_settings(db_path, tmp_path, experiments_dir=root)
    with TestClient(create_app(settings)) as client:
        api = Api(client, settings)
        api.user("res", GlobalRole.RESEARCHER)
        api.user("coord", GlobalRole.COORDINATOR)
        api.login("res")
        api.login("coord")
        assert api.get("/api/v1/experiments", "coord").status_code == 403
        listed = api.get("/api/v1/experiments", "res").json()
        assert {e["experiment_id"]: e["family"] for e in listed} == {
            coord_id: "coordination",
            command_id: "command",
        }
        first = next(e for e in listed if e["experiment_id"] == coord_id)
        assert first["collection"] == "phase5/baselines" and first["rows"] == 2
        assert first["definitions"] == {"coverage": "fraction"}
        assert "path" not in json.dumps(first).lower()
        detail = api.get(f"/api/v1/experiments/{coord_id}", "res").json()
        assert detail["data"][0] == {
            "scenario": "flood_basic",
            "agents": 3,
            "seed": 42,
            "policy": "independent",
            "coverage": 0.1,
            "tasks_issued": 0,
        }
        assert api.get("/api/v1/experiments/..%2F..%2Fetc", "res").status_code == 404
        assert api.get(f"/api/v1/experiments/{'c' * 32}", "res").status_code == 404
