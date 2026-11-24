"""Phase 9 orchestration: configuration validation, matrix runner and shutdown signalling."""

import asyncio
import csv
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.integrations.simulation_adapter import MissionConfig
from orchestration.checks import run_checks
from orchestration.headless import distribution
from orchestration.manifest import config_digest, manifest
from orchestration.matrix import Block, MatrixPlan, run_matrix
from orchestration.serve import RotatingStream, watch_stop

ROOT = Path(__file__).resolve().parents[2]


def test_repository_configuration_is_valid_for_headless_profile() -> None:
    results = run_checks("headless")
    errors = [r for r in results if r.status == "error"]
    assert not errors, errors
    names = {r.name for r in results}
    assert {"configs/model1.json", "configs/model2.json", "scenario flood_basic"} <= names
    assert any(r.name.startswith("experiment phase9_smoke") for r in results)


@pytest.mark.parametrize(
    "values",
    [
        {"scenario_id": "unknown_scenario"},
        {"scenario_id": "../configs/scenarios/flood_basic"},
        {"scenario_id": "flood_basic", "agents": 0},
        {"scenario_id": "flood_basic", "agents": 21},
        {"scenario_id": "flood_basic", "coordination": "learned"},
        {"scenario_id": "flood_basic", "command_mode": "llm"},
        {"scenario_id": "flood_basic", "extra": 1},
    ],
)
def test_invalid_mission_configuration_is_rejected_before_start(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MissionConfig.model_validate(values)


def test_geometry_that_cannot_hold_the_fleet_is_rejected() -> None:
    with pytest.raises(ValueError, match="rejected"):
        MissionConfig(scenario_id="flood_network_partition", agents=20).validated()


def test_matrix_plans_are_bounded_and_have_distinct_levels() -> None:
    block = {"name": "b", "scenarios": ["flood_basic"], "agents": [1], "seeds": [42]}
    with pytest.raises(ValidationError, match="duplicate"):
        Block.model_validate(block | {"seeds": [42, 42]})
    with pytest.raises(ValidationError, match="max_runs"):
        MatrixPlan.model_validate(
            {
                "name": "x",
                "profile": "smoke",
                "max_runs": 2,
                "blocks": [block | {"seeds": [1, 2, 3]}],
            }
        )
    for path in sorted((ROOT / "configs" / "experiments").glob("phase9_*.json")):
        MatrixPlan.model_validate_json(path.read_bytes())


def test_matrix_reports_completed_and_unsupported_runs(tmp_path: Path) -> None:
    plan = MatrixPlan(
        name="test",
        profile="smoke",
        blocks=(
            Block(name="ok", scenarios=("flood_basic",), agents=(2,), seeds=(42,)),
            Block(
                name="too-many", scenarios=("flood_network_partition",), agents=(20,), seeds=(42,)
            ),
        ),
    )
    folder = run_matrix(plan, tmp_path)
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["status_counts"] == {"completed": 1, "unsupported": 1}
    assert summary["determinism_checks"] == summary["determinism_identical"] == 1
    with (folder / "runs.csv").open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert [r["status"] for r in rows] == ["completed", "unsupported"]
    assert rows[1]["reason"] and not rows[1]["fingerprint"]
    record = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert record["configuration_sha256"] == config_digest(plan.model_dump(mode="json"))
    assert record["environment"]["python"].startswith("3.1")


def test_manifest_records_revision_without_secrets() -> None:
    record = manifest("unit", {"seed": 1})
    text = json.dumps(record)
    assert record["git_commit"] is None or len(record["git_commit"].split("-")[0]) == 40
    assert "SWARM_JWT_SECRET" not in text and "password" not in text.lower()


def test_distribution_uses_nearest_rank_percentiles() -> None:
    stats = distribution([float(v) for v in range(1, 101)])
    assert stats["n"] == 100 and stats["median"] == 50.5
    assert stats["p95"] == 95 and stats["p99"] == 99 and stats["max"] == 100
    assert distribution([])["mean"] is None


def test_stop_file_triggers_graceful_server_exit(tmp_path: Path) -> None:
    class Server:
        should_exit = False

    server = Server()
    stop = tmp_path / "backend.stop"

    async def scenario() -> None:
        watcher = asyncio.create_task(watch_stop(server, stop))
        await asyncio.sleep(0.1)
        assert not server.should_exit
        stop.write_text("stop", encoding="ascii")
        await asyncio.wait_for(watcher, timeout=5)

    asyncio.run(scenario())
    assert server.should_exit and not stop.exists()


def test_server_log_rotates_at_size_limit(tmp_path: Path) -> None:
    log = tmp_path / "backend.log"
    stream = RotatingStream(log, max_bytes=100)
    for i in range(30):
        stream.write(f"line {i:02d}\n")
    stream.flush()
    previous = log.with_name("backend.log.1")
    assert previous.exists() and log.stat().st_size < 100 and previous.stat().st_size >= 100
    assert "line 29" in log.read_text(encoding="utf-8")
