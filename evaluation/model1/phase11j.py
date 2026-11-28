"""Phase 11J registry build, verification, inference profile and migration records.

    python -m evaluation.model1.phase11j registry
    python -m evaluation.model1.phase11j profile
    python -m evaluation.model1.phase11j migration
"""

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from evaluation.model1.data import fit_sensor_normalization
from evaluation.model1.perception import PerceptionRuntime
from evaluation.model1.phase11i_tasks import datasets
from evaluation.model1.registry import ModelEntry, ModelRegistry, Precision, file_sha256
from evaluation.process_memory import peak_rss_mib

DATA = Path("D:/SWARM-AID-DATA")
REPO = Path(__file__).resolve().parents[2]
RUNS = DATA / "runs/phase11j"
REGISTRY = RUNS / "runtime_model_registry.json"
FINAL = DATA / "saved-models/Phase11-Final"

# id: selection name, preserved folder, architecture, modality, release, preprocessing, limits
MODELS: dict[str, tuple[str, str, str, str, str, str, tuple[str, ...]]] = {
    "rescuenet": ("RescueNet", "RescueNet", "deeplabv3_mobilenet_v3_large", "image",
                  "phase11g6-rescuenet-v1",
                  "EXIF transpose, RGB, bilinear 512, recorded channel normalization",
                  ("site and flight independence unverified", "validation only",
                   "estimated scene categories, not verified damage assessment")),
    "floodnet": ("FloodNet", "FloodNet", "deeplabv3_mobilenet_v3_large", "image",
                 "phase11g4-floodnet-v1",
                 "EXIF transpose, RGB, bilinear 512, recorded channel normalization",
                 ("site and flight independence unverified", "validation only")),
    "flame": ("FLAME", "FLAME", "mobilenet_v3_small", "image", "phase11g5-flame-v1",
              "EXIF transpose, RGB, bilinear 224, recorded channel normalization",
              ("parent-video independence unverified", "validation only")),
    "esc50": ("ESC-50", "ESC-50", "mobilenet_v3_small_logmel", "audio", "phase11g-esc50-v1",
              "evaluation.data.preprocessing.audio log-mel, per-clip standardization",
              ("environmental sounds never establish human distress", "validation only",
               "no audio modality in the wire evidence contract")),
    "uci-co": ("UCI Air Quality", "UCI-Air-Quality", "gru_sensor_regression", "environment",
               "phase11g3-uci-air-quality-v1",
               "raw sensor window, -200 missing, training-only mean and scale",
               ("forecast is not a verified emergency measurement",
                "persistence using CO history is a stronger reference", "validation only")),
    "wisard-rgb": ("WiSARD RGB", "WiSARD-RGB", "fasterrcnn_mobilenet_v3_large_fpn", "image",
                   "phase11g8/prepared-v1/visual", "EXIF transpose, RGB, bilinear 512, [0,1]",
                   ("mAP50 about 0.105; low reliability", "no detection never means clear",
                    "never authorizes rescue decisions or physical action")),
    "environment-fusion-neural": (
        "EnvironmentalFusion", "EnvironmentalFusion", "EnvironmentalFusion", "environment", "",
        "symbolic [3,6] features with availability",
        ("research comparison only; deterministic fusion is the default",
         "no advantage over deterministic voting", "incorrect observations degrade it badly")),
}


def write(name: str, value: Any) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / name).write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf8")


def read(path: Path) -> Any:
    return json.loads(path.read_bytes())


def _release(name: str) -> Path:
    return DATA / ("runs" if "/" in name else "manifests") / name


def build_registry() -> None:
    selection = read(DATA / "runs/phase11i/final_model_selection.json")
    preserved = {row["destination"]: row["sha256"] for row in
                 read(DATA / "runs/phase11i/checkpoint_preservation.json")["verified"]}
    entries = []
    for model_id, row in MODELS.items():
        name, folder, architecture, modality, release, preprocessing, limits = row
        path = FINAL / folder / "selected.pt"
        expected = preserved[str(path)]
        if file_sha256(path) != expected:
            raise ValueError(f"preserved checkpoint differs from its manifest: {path}")
        payload = torch.load(path, map_location="cpu", weights_only=True)
        chosen = selection[name]
        if abs(payload["best_validation_metric"] - (
                chosen["optimized"] if chosen["selected"] == "optimized" else chosen["baseline"]
        )) > 1e-9:
            raise ValueError(f"checkpoint metric differs from the selection record: {name}")
        config = {k: v for k, v in payload["model_config"].items()
                  if k not in ("taxonomy", "phase11i")}
        labels: tuple[str, ...] = ()
        if release and "/" not in release and model_id != "uci-co":
            registry = read(_release(release) / "registry.json")
            labels = tuple(sorted(registry["datasets"][0]["label_definitions"]))
        task = payload["model_config"].get("task", "audio_classification")
        units = ""
        if model_id == "environment-fusion-neural":
            task, labels = "environment_fusion", ("routine", "water", "fire", "damage")
        if model_id == "esc50":
            task = "audio_classification"
        if model_id == "wisard-rgb":
            labels = ("background", "person")
        if model_id == "uci-co":
            train = datasets(_release(release), "sensor_regression", ("train",))[0]
            mean, scale = fit_sensor_normalization(train)
            config.update(normalization_mean=mean.tolist(), normalization_scale=scale.tolist(),
                          window=len(train.rows[0].source_rows),
                          features=list(train.rows[0].sensor_feature_names))
            units = "mg/m^3 CO (UCI CO(GT)), next hour"
        entries.append(ModelEntry(
            model_id=model_id, task=task, architecture=architecture,
            state="EXPERIMENTAL" if model_id in ("wisard-rgb", "environment-fusion-neural")
            else "READY",
            checkpoint=path.relative_to(DATA).as_posix(), sha256=expected, config=config,
            modality=modality, preprocessing=preprocessing, labels=labels, units=units,
            metric=chosen["metric"], metric_value=payload["best_validation_metric"],
            authorization_id=payload["authorization_id"],
            release_manifest_sha256=payload["release_manifest_sha256"], limitations=limits,
        ))
        print(f"[registry] {model_id} verified metric={payload['best_validation_metric']:.6f}",
              flush=True)
    entries.append(ModelEntry(model_id="wisard-thermal", task="object_detection",
                              state="EXCLUDED", reason="owner decision; artifacts preserved",
                              modality="thermal"))
    for model_id in ("smoke-detection-iot", "usgs-water"):
        entries.append(ModelEntry(model_id=model_id, task="deferred", state="UNAVAILABLE",
                                  reason="deferred; no trained model exists"))
    write("runtime_model_registry.json", {
        "schema": "phase11j-runtime-registry-1", "data_root_relative_paths": True,
        "default_environment_fusion": "agents.drone_agent.evidence.fuse_environment",
        "models": [e.model_dump(mode="json") for e in entries],
    })
    runtime = PerceptionRuntime(ModelRegistry.from_file(REGISTRY, DATA, max_resident=1))
    for entry in entries:
        if entry.checkpoint:
            runtime.registry.get(entry.model_id)
            print(f"[registry] {entry.model_id} strict load ok", flush=True)


def synthetic_inputs(registry: ModelRegistry) -> dict[str, Any]:
    """Noise and neutral values: they exercise shapes and timing, not accuracy."""
    import io

    from PIL import Image

    rng = np.random.default_rng(0)
    buffer = io.BytesIO()
    Image.fromarray(rng.integers(0, 255, (512, 512, 3), dtype=np.uint8)).save(buffer, "PNG")
    image = buffer.getvalue()
    uci = registry.entries["uci-co"].config
    return {
        "rescuenet": image, "floodnet": image, "flame": image, "wisard-rgb": image,
        "esc50": rng.standard_normal((498, 40)).astype(np.float32),
        "uci-co": np.tile(np.asarray(uci["normalization_mean"], dtype=np.float32),
                          (int(uci["window"]), 1)),
        "environment-fusion-neural": ([[1, 0, 0, 0, 1, 1]] * 3, [True, True, True]),
    }


def measure(device: str, precision: Precision, repeats: int) -> dict[str, Any]:
    registry = ModelRegistry.from_file(REGISTRY, DATA, device=device, precision=precision,
                                       max_resident=8)
    runtime = PerceptionRuntime(registry)
    cuda = registry.device.type == "cuda"
    result: dict[str, Any] = {"device": registry.device.type, "precision": registry.precision,
                              "models": {}}
    for model_id, payload in synthetic_inputs(registry).items():
        registry.release()
        if cuda:
            torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        registry.get(model_id)
        load = time.perf_counter() - started
        runtime.infer(model_id, payload)
        times = []
        for _ in range(repeats):
            tick = time.perf_counter()
            output = runtime.infer(model_id, payload)
            if cuda:
                torch.cuda.synchronize()
            times.append((time.perf_counter() - tick) * 1000)
        result["models"][model_id] = {
            "availability": output.availability, "load_seconds": load,
            "median_latency_ms": float(np.median(times)),
            "peak_allocated_MiB": torch.cuda.max_memory_allocated() / 2**20 if cuda else None,
            "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20 if cuda else None,
        }
        print(f"[profile] {device}/{precision} {model_id} {result['models'][model_id]}",
              flush=True)
    registry.release()
    if cuda:
        torch.cuda.reset_peak_memory_stats()
    inputs = synthetic_inputs(registry)
    for model_id, payload in inputs.items():
        runtime.infer(model_id, payload)
    tick = time.perf_counter()
    for model_id, payload in inputs.items():
        runtime.infer(model_id, payload)
    if cuda:
        torch.cuda.synchronize()
    result["all_resident"] = {
        "all_models_sequential_latency_ms": (time.perf_counter() - tick) * 1000,
        "allocated_MiB": torch.cuda.memory_allocated() / 2**20 if cuda else None,
        "peak_allocated_MiB": torch.cuda.max_memory_allocated() / 2**20 if cuda else None,
        "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20 if cuda else None,
    }
    registry.release()
    return result


def multi_agent(agents: int, ticks: int) -> dict[str, Any]:
    """End-to-end ticks: fixture image -> FLAME -> agent -> router -> Model 2."""
    from agents.command_agent.agent import Settings as CommandSettings
    from agents.drone_agent.evidence import EvidenceLedger
    from evaluation.model1.perception import MediaPerception
    from simulation.adapters.model1 import Fleet
    from simulation.core.configuration import Scenario, load
    from simulation.core.engine import Engine
    from simulation.sensors.mock import fixture_packet

    registry = ModelRegistry.from_file(REGISTRY, DATA, max_resident=1)
    runtime = PerceptionRuntime(registry)
    image = synthetic_inputs(registry)["flame"]

    class Resolver:
        def resolve(self, agent_id: str, evidence: Any) -> bytes:
            return bytes(image)

    engine = Engine(Scenario.model_validate(
        {**load("flood_basic").model_dump(), "agents": agents, "horizon": ticks + 1,
         "seed": 3500}))  # development seed; 42-46 are reserved
    fleet = Fleet(engine, command=CommandSettings())
    ledgers = {a: EvidenceLedger(a, engine.mission_id) for a in fleet.agents}
    for name, agent in fleet.agents.items():
        agent.perception = MediaPerception(runtime, Resolver(), ("flame",), ledgers[name],
                                           "synthetic_fixture")
    times = []
    for _ in range(ticks):
        for name in engine.active:
            engine.views[name] = fixture_packet(engine.views[name], ("image", "gps"))
        tick = time.perf_counter()
        fleet.advance(engine)
        times.append((time.perf_counter() - tick) * 1000)
    return {
        "agents": agents, "ticks": ticks, "median_tick_ms": float(np.median(times)),
        "model_loads": registry.loads, "resident_instances": len(registry.resident),
        "provider_errors": sum(a.health.provider_errors for a in fleet.agents.values()),
        "evidence_records": {a: len(v.items) for a, v in ledgers.items()},
    }


def profile() -> None:
    report: dict[str, Any] = {
        "generated": datetime.now(UTC).isoformat(), "inputs": "synthetic",
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "runs": [],
    }
    if torch.cuda.is_available():
        for precision in ("fp32", "fp16", "bf16"):
            report["runs"].append(measure("cuda", precision, 10))
    report["multi_agent"] = multi_agent(6, 4)
    report["runs"].append(measure("cpu", "fp32", 3))
    report["process_peak_rss_MiB"] = peak_rss_mib()
    write("inference_profile.json", report)
    print(f"[profile] multi_agent={report['multi_agent']}", flush=True)
    print(f"[profile] peak_rss_MiB={report['process_peak_rss_MiB']:.0f}", flush=True)
    write("rtx2060_runtime_requirements.json", {
        "status": "NOT VERIFIED on RTX 2060; 6 GiB VRAM is a planning assumption",
        "runtime_config": "configs/rtx2060_runtime.json",
        "device": "auto with CPU fallback", "precision": "fp16 (fp32 fallback); not bf16",
        "max_resident_models": 2,
        "inference_batch_size": "fixed at 1; batched inference is not implemented",
        "measured_on_current_gpu": {
            f"{r['precision']}": r["all_resident"] for r in report["runs"]
            if r["device"] == "cuda"},
        "training": "not required for migration",
    })


def migration() -> None:
    """Checksummed list of what to copy. Large datasets and caches are listed, not copied."""
    files: list[dict[str, Any]] = []

    def add(path: Path, root: str, essential: bool, base: Path) -> None:
        if path.is_file():
            files.append({"root": root, "path": path.relative_to(base).as_posix(),
                          "essential": essential, "bytes": path.stat().st_size,
                          "sha256": file_sha256(path)})

    listing = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"], cwd=REPO,
        capture_output=True, text=True, check=True).stdout.splitlines()
    for relative in listing:
        add(REPO / relative, "repo", True, REPO)
    for path in sorted(FINAL.rglob("*")):
        add(path, "data", not path.name.startswith("resume"), DATA)
    for folder in ("runs/phase11i", "runs/phase11j", "runs/phase12",
                   "runs/phase11h/training-preparation"):
        for path in sorted((DATA / folder).rglob("*")):
            if path.suffix in (".json", ".jsonl", ".csv", ".txt", ".log") and path.name != "migration_manifest.json":
                add(path, "data", True, DATA)
    for row in MODELS.values():
        if row[4]:
            for path in sorted(_release(row[4]).glob("*.json*")):
                add(path, "data", True, DATA)
    prepared = Path(read(DATA / "runs/phase11h/training-preparation/training_config.json")
                    ["release"])
    for path in sorted(prepared.rglob("*")):
        add(path, "data", True, DATA)
    inventory = read(DATA / "runs/phase11i/baseline_inventory.json")["models"]
    for row in inventory:
        checkpoint = Path(row["checkpoint"])
        for path in (checkpoint, checkpoint.with_suffix(".json")):
            add(path, "data", False, DATA)
    # Git history travels as a bundle; uncommitted work is in the repo file list above.
    bundle = DATA / "migration/swarm-aid.bundle"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "bundle", "create", str(bundle), "--all"], cwd=REPO,
                   capture_output=True, check=True)
    add(bundle, "data", True, DATA)
    for path in sorted((DATA / "checkpoints/phase12").rglob("*")):
        add(path, "data", False, DATA)
    packages = subprocess.run([sys.executable, "-m", "pip", "freeze", "--exclude-editable"],
                              capture_output=True, text=True, check=True).stdout.splitlines()

    def size(folder: Path) -> int:
        return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())

    unique = {(f["root"], f["path"]): f for f in files}
    files = list(unique.values())
    write("migration_manifest.json", {
        "generated": datetime.now(UTC).isoformat(),
        "status": "PREPARED; not copied until the script reports verification",
        "files": files,
        "essential_bytes": sum(f["bytes"] for f in files if f["essential"]),
        "optional_bytes": sum(f["bytes"] for f in files if not f["essential"]),
        "not_copied_by_default": {
            name: {"path": str(DATA / name), "bytes": size(DATA / name),
                   "needed_for": purpose}
            for name, purpose in (("raw", "retraining or re-evaluation only"),
                                  ("cache", "rebuildable preprocessing"),
                                  ("checkpoints", "training history"))},
        "python": platform.python_version(),
        "packages": packages,
        "environment": [
            "Install the same Python minor version and create .venv in the repository",
            ("Install torch, torchvision and torchaudio at the listed versions from the "
             "PyTorch CUDA index matching their local version tag"),
            "pip install the remaining listed packages, then pip install -e .",
            "Copy data to <destination>/data and pass that folder as the data root",
        ],
        "rights": "Dataset licences restrict redistribution; copy only to owner-controlled media.",
    })
    manifest = read(RUNS / "migration_manifest.json")
    print(f"[migration] files={len(files)} essential_MiB={manifest['essential_bytes'] / 2**20:.0f} "
          f"optional_MiB={manifest['optional_bytes'] / 2**20:.0f}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("registry", "profile", "migration"))
    command = parser.parse_args().command
    {"registry": build_registry, "profile": profile, "migration": migration}[command]()


if __name__ == "__main__":
    main()
