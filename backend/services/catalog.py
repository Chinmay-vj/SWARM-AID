"""Read-only catalogs for the Phase 8 dashboard: scenario configuration and stored experiments.

Scenario entries expose configuration only (grid size, defaults, modalities, fault settings).
Terrain, hazard placement and people counts are simulator ground truth and are never returned.

Experiment entries come from the comparison.csv files written by evaluation.experiment_runner
(Phase 5 coordination baselines) and evaluation.command_agent_experiments (Phase 6 Model 2
baselines). Values are returned exactly as measured; nothing is aggregated or invented here.
Filesystem paths are not exposed: an experiment is addressed by its generated folder name.
"""

import csv
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from backend.integrations.simulation_adapter import SCENARIO_DIR, available_scenarios

EXPERIMENT_ID = re.compile(r"^[0-9a-f]{32}$")
MAX_ROWS = 20_000
MAX_DEPTH = 4
Family = Literal["coordination", "command"]


class ScenarioInfo(BaseModel):
    scenario_id: str
    disaster: str
    width: int
    height: int
    default_agents: int
    default_seed: int
    horizon: int
    tick_ms: int
    modalities: list[str]
    faults: list[str]


class ExperimentInfo(BaseModel):
    experiment_id: str
    family: Family
    collection: str
    created_at: datetime
    episodes: int
    columns: list[str]
    rows: int
    simulator_version: str | None = None
    definitions: dict[str, str] | None = None


class ExperimentDetail(ExperimentInfo):
    data: list[dict[str, str | float | int]]


def scenario_catalog() -> list[ScenarioInfo]:
    from simulation.core.configuration import Scenario

    out = []
    for name in sorted(available_scenarios()):
        s = Scenario.model_validate_json((SCENARIO_DIR / f"{name}.json").read_bytes())
        faults = [
            label
            for label, active in (
                ("communication_outage", bool(s.outage_steps)),
                ("network_partition", s.partition),
                ("message_loss", s.loss > 0),
                ("sensor_dropout", s.dropout > 0),
                ("sensor_noise", s.noise > 0),
                ("false_positives", s.false_positive > 0),
                ("agents_unavailable", bool(s.unavailable)),
                ("latency", s.latency > 0),
            )
            if active
        ]
        out.append(
            ScenarioInfo(
                scenario_id=s.scenario_id,
                disaster=s.disaster,
                width=s.width,
                height=s.height,
                default_agents=s.agents,
                default_seed=s.seed,
                horizon=s.horizon,
                tick_ms=s.tick_ms,
                modalities=list(s.modalities),
                faults=faults,
            )
        )
    return out


def _number(value: str) -> str | float | int:
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


class ExperimentCatalog:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _folders(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        found = []
        for csv_path in self.root.rglob("comparison.csv"):
            folder = csv_path.parent
            depth = len(folder.relative_to(self.root).parts)
            if depth <= MAX_DEPTH and EXPERIMENT_ID.match(folder.name):
                found.append(folder)
        return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)

    def _info(self, folder: Path) -> tuple[ExperimentInfo, list[dict[str, Any]]] | None:
        with (folder / "comparison.csv").open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            columns = list(reader.fieldnames or [])
            data = []
            for i, row in enumerate(reader):
                if i >= MAX_ROWS:
                    break
                data.append({k: _number(v) for k, v in row.items() if k is not None})
        if "policy" in columns:
            family: Family = "coordination"
        elif "mode" in columns:
            family = "command"
        else:
            return None
        version: str | None = None
        definitions: dict[str, str] | None = None
        first = folder / "episode-0.json"
        if first.is_file():
            try:
                meta = json.loads(first.read_text(encoding="utf-8"))
                version = str(meta["simulator_version"]) if "simulator_version" in meta else None
                if isinstance(meta.get("definitions"), dict):
                    definitions = {str(k): str(v) for k, v in meta["definitions"].items()}
            except (OSError, ValueError):
                pass
        info = ExperimentInfo(
            experiment_id=folder.name,
            family=family,
            collection="/".join(folder.parent.relative_to(self.root).parts) or ".",
            created_at=datetime.fromtimestamp(folder.stat().st_mtime, UTC),
            episodes=sum(1 for _ in folder.glob("episode-*.json")),
            columns=columns,
            rows=len(data),
            simulator_version=version,
            definitions=definitions,
        )
        return info, data

    def list(self) -> list[ExperimentInfo]:
        out = []
        for folder in self._folders():
            parsed = self._info(folder)
            if parsed is not None:
                out.append(parsed[0])
        return out

    def get(self, experiment_id: str) -> ExperimentDetail | None:
        if not EXPERIMENT_ID.match(experiment_id):
            return None
        for folder in self._folders():
            if folder.name == experiment_id:
                parsed = self._info(folder)
                if parsed is None:
                    return None
                info, data = parsed
                return ExperimentDetail(**info.model_dump(), data=data)
        return None
