import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from simulation.core.engine import Engine

DEFINITIONS = {
    "steps": "Completed transitions",
    "duration_ms": "Simulated elapsed milliseconds",
    "coverage": "Fraction of all map cells sampled by spatial modalities",
    "observations": "Captured symbolic readings including reset",
    "people_observed": "Unique visible truth IDs detected at capture",
    "false_positive": "Spurious modality-cell detections",
    "missed": "Visible person-modality opportunities missed",
    "battery_used": "Fleet battery percentage points spent",
    "invalid": "Rejected action proposals",
    "unavailable": "Inactive drones at final tick",
    "availability": "Connected active agent samples / active samples",
    "reason": "Running, horizon or inactive",
}


def metrics(e: Engine) -> dict[str, object]:
    return {
        "steps": e.t,
        "duration_ms": e.t * e.config.tick_ms,
        "coverage": len(e.covered) / len(e.world.tiles),
        "observations": e.count,
        "people_observed": len(e.seen),
        "false_positive": e.false,
        "missed": e.missed,
        "battery_used": sum(100 - d.battery for d in e.drones.values()),
        "invalid": e.invalid,
        "unavailable": len(e.drones) - len(e.active),
        "availability": e.connected / e.radio_samples if e.radio_samples else None,
        "reason": e.reason,
    }


def export(e: Engine, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    rid = uuid4().hex
    record = {
        "experiment_id": rid,
        "seed": e.seed,
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "0.2",
        "configuration": e.config.model_dump(mode="json"),
        "definitions": DEFINITIONS,
        "metrics": metrics(e),
    }
    path = folder / (rid + ".json")
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    with path.with_suffix(".csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["experiment_id", "metric", "definition", "value"])
        writer.writerows((rid, k, DEFINITIONS[k], v) for k, v in metrics(e).items())
    return path
