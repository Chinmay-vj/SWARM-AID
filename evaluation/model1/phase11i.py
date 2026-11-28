"""Standalone, resumable, deadline-bounded Phase 11I orchestrator.

    python -m evaluation.model1.phase11i prepare
    python -m evaluation.model1.phase11i smoke
    python -m evaluation.model1.phase11i run --deadline 2026-11-27T14:00:00-08:00

Training experiments run only when the owner's decision file names the exact
experiment digest. This module never writes an approval.
"""

import argparse
import hashlib
import importlib.metadata
import json
import msvcrt
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from torch import nn
from torch.utils.data import DataLoader

from evaluation.model1.phase11i_tasks import DATA, RUNS, baseline, say, sha
from evaluation.model1.training import (
    ClassificationTask,
    SyntheticTaskDataset,
    TrainingConfig,
    fit,
    synthetic_training_context,
)

REPO = Path(__file__).resolve().parents[2]
MANIFESTS = DATA / "manifests"
DECISION = RUNS / "owner_decision.approved.json"
PROGRESS = RUNS / "optimization_progress.json"
FINAL = DATA / "saved-models/Phase11-Final"
LOWER_IS_BETTER = {"mae"}
RELEASE_DIGESTS = ("candidate.json", "operational.json", "targets.json",
                   "authorization_bundle.json", "registry.json")


def _common(**values: Any) -> dict[str, Any]:
    return {"seed": 2025, "gradient_clip_norm": 1.0, "gradient_accumulation": 1,
            "image_size": 224, **values}


def definitions() -> dict[str, dict[str, Any]]:
    """Order is execution order: authorized evaluations first, then training."""
    segmentation = {
        "type": "train", "kind": "semantic_segmentation", "metric": "macro_iou",
        "batch_candidates": [32, 24, 16], "jitter": 0.15,
        "initialization": "warm start from the recorded baseline best checkpoint",
        "training": _common(epochs=20, learning_rate=3e-4, weight_decay=0.01,
                            early_stopping_patience=6, image_size=512),
    }
    return {
        "wisard_rgb_eval": {
            "type": "eval", "budget_minutes": 35,
            "release": str(DATA / "runs/phase11g8/prepared-v1/visual"),
            "image_sizes": [512, 800, 1024], "samples": 256,
        },
        "uci_persistence": {
            "type": "eval", "budget_minutes": 3,
            "release": str(MANIFESTS / "phase11g3-uci-air-quality-v1"),
        },
        "environment_fusion_eval": {"type": "eval", "budget_minutes": 5},
        "rescuenet": {
            **segmentation, "budget_minutes": 30, "baseline": "RescueNet",
            "release": str(MANIFESTS / "phase11g6-rescuenet-v1"),
            "cache": str(DATA / "cache/phase11g6-rescuenet-v1"),
        },
        "floodnet": {
            **segmentation, "budget_minutes": 25, "baseline": "FloodNet",
            "release": str(MANIFESTS / "phase11g4-floodnet-v1"),
            "cache": str(DATA / "cache/phase11g4-floodnet-v1"),
        },
        "esc50": {
            "type": "train", "kind": "audio_classification", "metric": "macro_f1",
            "budget_minutes": 15, "baseline": "ESC-50", "batch_candidates": [32],
            "release": str(MANIFESTS / "phase11g-esc50-v1"),
            "label_smoothing": 0.1, "initialization": "random",
            "training": _common(epochs=80, learning_rate=1e-3, weight_decay=0.05,
                                early_stopping_patience=20),
        },
        "flame": {
            "type": "train", "kind": "image_classification", "metric": "macro_f1",
            "budget_minutes": 10, "baseline": "FLAME", "batch_candidates": [256],
            "release": str(MANIFESTS / "phase11g5-flame-v1"),
            "cache": str(DATA / "cache/phase11g5-flame-v1"),
            "label_smoothing": 0.05, "jitter": 0.2, "initialization": "random",
            "training": _common(epochs=15, learning_rate=3e-4, weight_decay=0.05,
                                early_stopping_patience=6),
        },
        "uci": {
            "type": "train", "kind": "sensor_regression", "metric": "mae",
            "budget_minutes": 5, "baseline": "UCI Air Quality", "batch_candidates": [64],
            "release": str(MANIFESTS / "phase11g3-uci-air-quality-v1"),
            "hidden_dim": 64, "dropout": 0.2, "huber_delta": 0.5, "initialization": "random",
            "training": _common(epochs=80, learning_rate=2e-3, weight_decay=0.01,
                                early_stopping_patience=15),
        },
    }


def digest_of(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf8")
    temporary.replace(path)


def read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_bytes()) if path.is_file() else default


def experiment_spec(name: str) -> dict[str, Any]:
    path = RUNS / "experiments" / name / "spec.json"
    return dict(json.loads(path.read_bytes()))


def prepare() -> None:
    """Freeze experiment specs and write the single pending owner decision."""
    pending: dict[str, Any] = {}
    for name, spec in definitions().items():
        if spec["type"] == "train":
            release = Path(spec["release"])
            bundle = json.loads((release / "authorization_bundle.json").read_bytes())
            spec["release_sha256"] = {f: sha(release / f) for f in RELEASE_DIGESTS}
            spec["authorization_ids"] = [r["authorization_id"] for r in bundle["records"]]
            spec["owner_identity"] = bundle["records"][0]["authorizing_owner_identity"]
            spec["baseline_checkpoint_sha256"] = baseline(spec["baseline"])["sha256"]
            spec["task_code_sha256"] = sha(Path(__file__).with_name("phase11i_tasks.py"))
            pending[name] = {
                "config_sha256": digest_of(spec),
                "owner_identity": spec["owner_identity"],
                "authorization_ids": spec["authorization_ids"],
                "spec": str(RUNS / "experiments" / name / "spec.json"),
                "initialization": spec["initialization"],
            }
        write_json(RUNS / "experiments" / name / "spec.json", spec)
        say(f"[prepare] {name}")
    write_json(RUNS / "owner_decision.template.json", {
        "decision": "PENDING",
        "approved_at": None,
        "scope": "Phase 11I local training start (and stated initialization) on the unchanged "
                 "approved train/validation partitions; existing authorization restrictions "
                 "apply; reserved test remains prohibited. Remove any experiment not approved.",
        "experiments": pending,
    })
    say(f"[prepare] owner decision template: {RUNS / 'owner_decision.template.json'}")


def approval_problem(name: str, spec: dict[str, Any]) -> str | None:
    """None only for an explicit, current owner decision bound to this exact experiment."""
    if not DECISION.is_file():
        return f"owner decision file is absent: {DECISION}"
    decision = json.loads(DECISION.read_text(encoding="utf-8-sig"))
    if decision.get("decision") != "APPROVE_TRAINING_START":
        return "owner decision is not APPROVE_TRAINING_START"
    entry = decision.get("experiments", {}).get(name)
    if entry is None:
        return "experiment is not named in the owner decision"
    if entry.get("config_sha256") != digest_of(spec):
        return "approved digest differs from the current experiment spec"
    if entry.get("owner_identity") != spec["owner_identity"]:
        return "owner identity differs from the authorization record"
    try:
        when = datetime.fromisoformat(decision["approved_at"])
    except (KeyError, TypeError, ValueError):
        return "approved_at is missing or not ISO 8601"
    if when.tzinfo is None or when > datetime.now(UTC):
        return "approved_at needs a timezone and cannot be in the future"
    release = Path(spec["release"])
    if any(sha(release / f) != value for f, value in spec["release_sha256"].items()):
        return "release files changed since the experiment was prepared"
    if sha(Path(__file__).with_name("phase11i_tasks.py")) != spec["task_code_sha256"]:
        return "experiment code changed since preparation; run prepare and re-approve"
    return None


def run_experiment(name: str, stop_at: float) -> None:
    from evaluation.model1 import phase11i_tasks as tasks

    spec = experiment_spec(name)
    say(f"[experiment] phase=11I name={name} type={spec['type']}")
    if spec["type"] == "train":
        problem = approval_problem(name, spec)
        if problem:
            raise PermissionError(problem)
        result = tasks.train(name, spec, stop_at)
    else:
        function = {"wisard_rgb_eval": tasks.wisard_rgb_eval,
                    "uci_persistence": tasks.uci_persistence,
                    "environment_fusion_eval": tasks.fusion_eval}[name]
        result = function(spec, stop_at)
    result["spec_sha256"] = digest_of(spec)
    write_json(RUNS / "experiments" / name / "result.json", result)
    say(f"[experiment] name={name} status={result['status']}")


def tee(command: list[str], log: Path, kill_at: float) -> tuple[int, bool]:
    """Stream a child to the terminal and a log; kill it if it overruns."""
    log.parent.mkdir(parents=True, exist_ok=True)
    killed = threading.Event()
    with log.open("a", encoding="utf8") as stream:
        process = subprocess.Popen(
            command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf8", errors="replace",
        )

        def stop() -> None:
            killed.set()
            process.kill()

        timer = threading.Timer(max(kill_at - time.time(), 1), stop)
        timer.start()
        try:
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                stream.write(line)
                stream.flush()
            return process.wait(), killed.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()


def resume_command(name: str, stop: float) -> str:
    local = datetime.fromtimestamp(stop).astimezone().isoformat(timespec="seconds")
    return (f".\\.venv\\Scripts\\python.exe -u -m evaluation.model1.phase11i run "
            f"--only {name} --deadline {local}")


def orchestrate(deadline: float, reserve_minutes: float, only: list[str] | None) -> None:
    stop = deadline - reserve_minutes * 60
    state = read_json(PROGRESS, {"experiments": {}})
    state["deadline"] = datetime.fromtimestamp(deadline).astimezone().isoformat()
    state["reserve_minutes"] = reserve_minutes
    records = state["experiments"]
    names = [n for n in definitions() if not only or n in only]

    def done(name: str) -> bool:
        result = read_json(RUNS / "experiments" / name / "result.json", {})
        return bool(result.get("status") == "completed"
                    and result.get("spec_sha256") == digest_of(experiment_spec(name)))

    # The second pass picks up an owner decision recorded while evaluations were running.
    for sweep in (1, 2):
        for position, name in enumerate(names):
            if done(name):
                records.setdefault(name, {}).update(status="completed")
                write_json(PROGRESS, state)
                continue
            if sweep == 2 and records.get(name, {}).get("status") != "blocked":
                continue
            spec = experiment_spec(name)
            record: dict[str, Any] = {"spec_sha256": digest_of(spec)}
            records[name] = record
            problem = approval_problem(name, spec) if spec["type"] == "train" else None
            available = stop - time.time()
            if problem:
                record.update(status="blocked", reason=problem)
            elif available < 120:
                record.update(status="not_started", reason="deadline",
                              resume_command=resume_command(name, deadline))
            else:
                waiting = sum(
                    experiment_spec(n)["budget_minutes"] for n in names[position:] if not done(n)
                )
                budget = spec["budget_minutes"]
                share = min(available, 60 * budget * min(1.5, available / (60 * waiting)))
                experiment_stop = time.time() + max(share, min(available, 120))
                say(f"[orchestrator] start={name} budget_s={experiment_stop - time.time():.0f} "
                    f"deadline_remaining_s={deadline - time.time():.0f}")
                record.update(status="running", started=datetime.now(UTC).isoformat())
                write_json(PROGRESS, state)
                result_path = RUNS / "experiments" / name / "result.json"
                result_path.unlink(missing_ok=True)
                started = time.time()
                log = RUNS / "logs" / f"{name}.log"
                code, killed = tee(
                    [sys.executable, "-u", "-m", "evaluation.model1.phase11i", "experiment",
                     name, "--stop-at", str(experiment_stop)],
                    log, min(stop, experiment_stop + 120),
                )
                record["seconds"] = record.get("seconds", 0) + time.time() - started
                record["log"] = str(log)
                result = read_json(result_path, None)
                if code == 0 and result:
                    record["status"] = result["status"]
                else:
                    record["status"] = "interrupted" if killed else "failed"
                    record["reason"] = "hard deadline stop" if killed else f"exit code {code}"
                if record["status"] != "completed":
                    record["resume_command"] = resume_command(name, deadline)
            say(f"[orchestrator] {name} status={record['status']} {record.get('reason', '')}")
            write_json(PROGRESS, state)
    finalize()


def _copy(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = sha(source)
    if not destination.is_file() or sha(destination) != expected:
        shutil.copy2(source, destination)
    if sha(destination) != expected:
        raise ValueError(f"copy verification failed: {destination}")
    return {"source": str(source), "destination": str(destination), "sha256": expected,
            "bytes": destination.stat().st_size}


def finalize() -> None:
    """Select by comparable validation evidence, preserve checkpoints, write records."""
    records = read_json(PROGRESS, {"experiments": {}})["experiments"]
    results = {
        name: result for name in definitions()
        if (result := read_json(RUNS / "experiments" / name / "result.json", None))
    }
    write_json(RUNS / "experiment_results.json", results)
    selection: dict[str, Any] = {}
    copies: list[dict[str, Any]] = []
    models = {"RescueNet": "rescuenet", "FloodNet": "floodnet", "ESC-50": "esc50",
              "FLAME": "flame", "UCI Air Quality": "uci", "WiSARD RGB": None,
              "EnvironmentalFusion": None}
    for model, name in models.items():
        say(f"[finalize] {model}")
        base = baseline(model)
        metric = {"WiSARD RGB": "map50", "EnvironmentalFusion": "macro_f1"}.get(
            model, definitions()[name]["metric"] if name else ""
        )
        entry: dict[str, Any] = {
            "metric": metric, "baseline": base["metrics"][metric], "selected": "baseline",
            "checkpoint": str(base["path"]), "model_config_source": str(base["path"]),
        }
        latest = base["path"]
        result = results.get(name) if name else None
        if result and "value" in result:
            gain = result["value"] - base["metrics"][metric]
            if metric in LOWER_IS_BETTER:
                gain = -gain
            entry.update(optimized=result["value"], improvement=gain,
                         optimization_status=result["status"],
                         epochs=result["epochs_completed"], batch_size=result["batch_size"],
                         peak_gpu_MiB=result["peak_gpu_MiB"],
                         training_seconds=records.get(name, {}).get("seconds"),
                         spec=str(RUNS / "experiments" / str(name) / "spec.json"))
            latest = Path(result["latest_checkpoint"])
            if gain > 0:
                entry.update(selected="optimized", checkpoint=result["best_checkpoint"],
                             model_config_source=result["best_checkpoint"])
        elif name:
            entry["optimization_status"] = records.get(name, {}).get("status", "not_started")
        selection[model] = entry
        folder = FINAL / model.replace(" ", "-")
        for label, source in (("selected.pt", Path(entry["checkpoint"])), ("resume.pt", latest)):
            copies.append(_copy(source, folder / label))
            if source.with_suffix(".json").is_file():
                copies.append(_copy(source.with_suffix(".json"),
                                    (folder / label).with_suffix(".json")))
        entry["preserved"] = str(folder / "selected.pt")
    selection["WiSARD Thermal"] = {"selected": "excluded",
                                   "reason": "owner decision; historical artifacts preserved"}
    releases = {n: Path(s["release"]) for n, s in definitions().items() if "release" in s}
    for name, release in releases.items():
        for filename in (*RELEASE_DIGESTS, "training_config.json", "training_start.approved.json"):
            if (release / filename).is_file():
                copies.append(_copy(release / filename, FINAL / "authorization" / name / filename))
    for path in (DECISION, RUNS / "thermal_exclusion_decision.json"):
        if path.is_file():
            copies.append(_copy(path, FINAL / "authorization" / path.name))
    for path in sorted(Path(__file__).parent.glob("*.py")):
        copies.append(_copy(path, FINAL / "source/evaluation/model1" / path.name))
    write_json(RUNS / "final_model_selection.json", selection)
    write_json(RUNS / "checkpoint_preservation.json", {
        "verified": copies,
        "warning": "Same-drive copies are not independent backups.",
    })
    write_json(RUNS / "hardware_migration_manifest.json", migration(releases))
    report(records, results, selection)
    say(f"[finalize] verified_files={len(copies)} records={RUNS}")


def migration(releases: dict[str, Path]) -> dict[str, Any]:
    packages = ("torch", "torchvision", "torchaudio", "numpy", "pillow", "pydantic")
    return {
        "target": "RTX 2060 (Turing, 6 or 12 GB). Nothing here has been run on it.",
        "precision": "Use FP32 or FP16 inference. Training needs amp_dtype=float16 with the "
                     "existing GradScaler, not BF16; that is a new config needing a new decision. "
                     "BF16 checkpoints hold FP32 weights.",
        "suggested_batch_sizes_unmeasured": {
            "segmentation_512": 4, "detection_512": 4, "flame_224": 64, "esc50": 32, "uci": 64},
        "resume": "Strict resume requires identical torch major.minor, training config and "
                  "checkpoint paths, and CUDA RNG state from the same device count.",
        "paths": {"data_root": str(DATA), "source": str(REPO), "preserved": str(FINAL),
                  "datasets": str(DATA / "raw"), "caches": str(DATA / "cache")},
        "releases": {name: str(path) for name, path in releases.items()},
        "preprocessing": "Segmentation: EXIF-transposed RGB 512 cache, nearest masks, recorded "
                         "normalization. FLAME: 224 uint8 cache. ESC-50: log-mel from "
                         "evaluation.data.preprocessing. UCI: training-only normalization.",
        "python": sys.version,
        "packages": {p: importlib.metadata.version(p) for p in packages
                     if _installed(p)},
    }


def _installed(package: str) -> bool:
    try:
        importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def report(records: dict[str, Any], results: dict[str, Any], selection: dict[str, Any]) -> None:
    records = {n: records.get(n) or results.get(n, {}) for n in definitions()}
    incomplete = [n for n in definitions() if records[n].get("status") != "completed"]
    lines = [
        "# SWARM-AID Phase 11I Completion Report", "",
        f"Generated {datetime.now(UTC).isoformat()} by the orchestrator from saved results.", "",
        "**Status: " + ("COMPLETE" if not incomplete else
                        "PARTIAL; not completed: " + ", ".join(incomplete)) + "**", "",
        "## Experiments", "", "| Experiment | Status | Minutes | Reason |", "|---|---|---:|---|",
    ]
    for name in definitions():
        record = records.get(name, {})
        lines.append(f"| {name} | {record.get('status', 'not_started')} | "
                     f"{record.get('seconds', 0) / 60:.1f} | {record.get('reason', '')} |")
    lines += ["", "## Selection (validation only)", "",
              "| Model | Metric | Baseline | Optimized | Selected | Peak GPU MiB |",
              "|---|---|---:|---:|---|---:|"]
    for model, entry in selection.items():
        optimized = entry.get("optimized")
        lines.append(
            f"| {model} | {entry.get('metric', '')} | {entry.get('baseline', float('nan')):.6f} | "
            f"{'-' if optimized is None else f'{optimized:.6f}'} | {entry['selected']} | "
            f"{entry.get('peak_gpu_MiB', 0):.0f} |"
        )
    for name in ("wisard_rgb_eval", "uci_persistence", "environment_fusion_eval"):
        if name in results:
            lines += ["", f"## {name}", "", "```json", json.dumps(results[name], indent=2), "```"]
    lines += [
        "", "## Limitations", "",
        "- Validation was used for early stopping and selection; reserved test not accessed.",
        "- Segmentation optimizations are warm-started, so they include the baseline training.",
        "- FLAME partitions are temporal; parent-video independence is unverified.",
        "- Publisher segmentation partitions do not establish site or flight independence.",
        "- ESC-50 environmental classes do not establish human distress.",
        "- WiSARD RGB reliability is low; no physical deployment or autonomous control use.",
        "- UCI persistence uses CO history that the model does not receive.",
        "- Preserved copies share one drive and are not independent backups.",
        "- Phase 11J was not started. Final test evaluation needs separate owner authorization.",
        "",
    ]
    lines += [f"Configurations, checkpoints and digests are recorded under `{RUNS}`.", ""]
    (REPO / "docs/PHASE_11I_COMPLETION_REPORT.md").write_text("\n".join(lines), encoding="utf8")


def smoke(stop_at: float) -> None:
    """Synthetic fit proving live logging, checkpointing and the deadline path."""
    generator = torch.Generator().manual_seed(1)
    examples = tuple((torch.randn(3, 16, 16, generator=generator), torch.tensor(i % 2))
                     for i in range(96))
    data = SyntheticTaskDataset(examples, fixture_id="phase11i-smoke", fixture_sha256="0" * 64)
    config = TrainingConfig(
        epochs=2, batch_size=4, progress=True, checkpoint_every=1,
        device="cuda:0" if torch.cuda.is_available() else "cpu",
        mixed_precision=torch.cuda.is_available(),
        checkpoint_root=DATA / "checkpoints/phase11i/smoke" / str(int(time.time())),
        profile_output_root=RUNS,
    )
    model = nn.Sequential(nn.Flatten(), nn.Linear(768, 2))
    fit(model, DataLoader(data, batch_size=4), DataLoader(data, batch_size=4),
        ClassificationTask(), config=config,
        context=synthetic_training_context("phase11i-smoke", data),
        model_config={"smoke": True}, deadline=stop_at)


def parse_deadline(args: argparse.Namespace) -> float:
    stored = read_json(RUNS / "deadline.json", None)
    if args.minutes is not None:
        deadline = time.time() + float(args.minutes) * 60
    elif args.deadline:
        deadline = datetime.fromisoformat(args.deadline).astimezone().timestamp()
    elif stored:
        return float(stored["deadline_epoch"])
    else:
        raise SystemExit("supply --deadline or --minutes")
    # The access window is never silently restarted.
    if stored and deadline > stored["deadline_epoch"] + 60 and not args.extend:
        raise SystemExit("deadline is later than the recorded one; pass --extend if correct")
    write_json(RUNS / "deadline.json", {"deadline_epoch": deadline})
    return deadline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")
    commands.add_parser("finalize")
    commands.add_parser("smoke")
    commands.add_parser("smoke-child")
    child = commands.add_parser("experiment")
    child.add_argument("name", choices=list(definitions()))
    child.add_argument("--stop-at", type=float, required=True)
    run = commands.add_parser("run")
    run.add_argument("--deadline", help="absolute ISO 8601 GPU access expiry")
    run.add_argument("--minutes", type=float, help="remaining GPU minutes from now")
    run.add_argument("--reserve-minutes", type=float, default=30,
                     help="kept for Phase 11J and artifact migration")
    run.add_argument("--only", nargs="+", choices=list(definitions()))
    run.add_argument("--extend", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "finalize":
        finalize()
    elif args.command == "experiment":
        run_experiment(args.name, args.stop_at)
    elif args.command == "smoke-child":
        smoke(time.time() + 120)
    elif args.command == "smoke":
        code, _ = tee([sys.executable, "-u", "-m", "evaluation.model1.phase11i", "smoke-child"],
                      RUNS / "logs/smoke.log", time.time() + 180)
        raise SystemExit(code)
    else:
        deadline = parse_deadline(args)
        RUNS.mkdir(parents=True, exist_ok=True)
        with (RUNS / "orchestrator.lock").open("a") as lock:
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise SystemExit("another Phase 11I orchestrator is running") from None
            try:
                orchestrate(deadline, args.reserve_minutes, args.only)
            except Exception:
                traceback.print_exc()
                raise


if __name__ == "__main__":
    main()
