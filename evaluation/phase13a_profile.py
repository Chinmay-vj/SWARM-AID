"""Phase 13A bounded performance baseline. Synthetic inputs, development seeds, no training.

    python -u -m evaluation.phase13a_profile all        (about 5 minutes)
    python -u -m evaluation.phase13a_profile <environment|model1|model2|backend|simulator|report>

Every symbolic run is restricted to development seeds 12900-12999 by an engine guard.
Nothing here measures predictive accuracy or optimizes anything.
"""

import argparse
import cProfile
import csv
import json
import os
import platform
import pstats
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any
from uuid import UUID, uuid4

from evaluation.process_memory import peak_rss_mib

DATA = Path("D:/SWARM-AID-DATA")
OUT = DATA / "runs/phase13/phase13a"
TMP = DATA / "tmp/phase13a"
REGISTRY = DATA / "runs/phase11j/runtime_model_registry.json"
REPO = Path(__file__).resolve().parents[1]
SEEDS = range(12900, 13000)
SEED = 12990
WARMUP, REPEATS = 5, 40
MODELS = ("rescuenet", "floodnet", "flame", "esc50", "uci-co", "wisard-rgb",
          "environment-fusion-neural")


def require_profiling_seed(seed: int) -> int:
    if seed not in SEEDS:
        raise ValueError(f"profiling may only use development seeds 12900-12999, not {seed}")
    return seed


def guard_engine() -> None:
    """Refuse any engine reset outside the profiling seeds, including protected final seeds."""
    from simulation.core.engine import Engine

    original = Engine.reset
    if getattr(original, "profiling_guard", False):
        return

    def reset(self: Engine, seed: int) -> None:
        original(self, require_profiling_seed(seed))

    reset.profiling_guard = True  # type: ignore[attr-defined]
    Engine.reset = reset  # type: ignore[method-assign]


def stats(values: list[float]) -> dict[str, float | int | None]:
    """Milliseconds. P95 is omitted below 20 samples rather than reported as zero."""
    ordered = sorted(values)
    return {
        "samples": len(values), "mean_ms": mean(values), "median_ms": median(values),
        "p95_ms": ordered[max(0, int(0.95 * len(ordered) + 0.999) - 1)]
        if len(ordered) >= 20 else None,
        "sd_ms": stdev(values) if len(values) > 1 else None,
    }


def timed(call: Callable[[], Any], repeats: int = REPEATS, warmup: int = WARMUP) -> dict[str, Any]:
    for _ in range(warmup):
        call()
    values = []
    for _ in range(repeats):
        started = time.perf_counter()
        call()
        values.append((time.perf_counter() - started) * 1000)
    return stats(values)


def save(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2), encoding="utf8")


def command(*args: str) -> str:
    done = subprocess.run(args, capture_output=True, text=True, check=False, cwd=REPO)
    return done.stdout.strip()


# ---------------------------------------------------------------- environment
def environment() -> None:
    import torch

    cim = json.loads(command(
        "powershell", "-NoProfile", "-Command",
        "$c=Get-CimInstance Win32_Processor; $o=Get-CimInstance Win32_OperatingSystem; "
        "@{cpu=$c.Name; physical=$c.NumberOfCores; logical=$c.NumberOfLogicalProcessors; "
        "total_ram_GiB=$o.TotalVisibleMemorySize/1MB; free_ram_GiB=$o.FreePhysicalMemory/1MB; "
        "os=$o.Caption; os_build=$o.Version} | ConvertTo-Json"))
    smi = command("nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used,"
                  "driver_version", "--format=csv,noheader,nounits")
    checks: dict[str, Any] = {}
    for device in ("cpu", *(("cuda",) if torch.cuda.is_available() else ())):
        a = torch.eye(64, device=device)
        checks[device] = bool(torch.equal(a @ a, a))
    free = shutil.disk_usage("D:/")
    packages = ("torch", "torchvision", "numpy", "pillow", "pydantic", "fastapi", "sqlalchemy",
                "gymnasium", "pettingzoo", "mypy", "ruff", "pytest")
    record = {
        "measured": datetime.now(UTC).isoformat(), "host": cim, "gpu_nvidia_smi": smi,
        "cuda_available": torch.cuda.is_available(), "torch": torch.__version__,
        "torch_cuda": torch.version.cuda, "python": platform.python_version(),
        "torch_cpu_threads": torch.get_num_threads(), "minimal_execution": checks,
        "disk_D_free_GiB": free.free / 2**30, "disk_D_total_GiB": free.total / 2**30,
        "packages": {p: version(p) for p in packages},
        "git_commit": command("git", "rev-parse", "HEAD"),
        "git_dirty": bool(command("git", "status", "--porcelain")),
        "rtx2060": "not present and not measured",
    }
    save("hardware_environment.json", record)
    print(json.dumps(record, indent=1))


# ---------------------------------------------------------------- Model 1
def model1_one(model_id: str, device: str, precision: str) -> None:
    """Runs in its own process so that load time and peak memory belong to one model."""
    import torch

    from evaluation.model1.perception import PerceptionRuntime
    from evaluation.model1.phase11j import synthetic_inputs
    from evaluation.model1.registry import ModelRegistry

    baseline_rss = peak_rss_mib()
    registry = ModelRegistry.from_file(REGISTRY, DATA, device=device, precision=precision)
    runtime = PerceptionRuntime(registry)
    entry = registry.entries[model_id]
    payload = synthetic_inputs(registry)[model_id]
    cuda = registry.device.type == "cuda"

    def sync() -> None:
        if cuda:
            torch.cuda.synchronize()

    if cuda:
        torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    model: Any = registry.get(model_id)
    sync()
    load_ms = (time.perf_counter() - started) * 1000
    loaded_rss = peak_rss_mib()
    started = time.perf_counter()
    first = runtime.infer(model_id, payload)
    sync()
    first_ms = (time.perf_counter() - started) * 1000
    kind = torch.float16 if precision == "fp16" else torch.bfloat16
    stages: dict[str, list[float]] = {k: [] for k in
                                      ("preprocess", "transfer", "inference", "postprocess")}
    shapes: list[list[int]] = []
    for i in range(WARMUP + REPEATS):
        marks = [time.perf_counter()]
        inputs = runtime._prepare(entry, payload)
        marks.append(time.perf_counter())
        moved = tuple(x.to(registry.device) for x in inputs)
        sync()
        marks.append(time.perf_counter())
        context = torch.autocast("cuda", dtype=kind) if precision != "fp32" else nullcontext()
        with torch.inference_mode(), context:
            output = (model([moved[0]]) if entry.task == "object_detection" else model(*moved))
        sync()
        marks.append(time.perf_counter())
        runtime._interpret(entry, output)
        sync()
        marks.append(time.perf_counter())
        if i >= WARMUP:
            for name, a, b in zip(stages, marks, marks[1:], strict=False):
                stages[name].append((b - a) * 1000)
        shapes = [list(x.shape) for x in inputs]

    def whole() -> None:
        runtime.infer(model_id, payload)
        sync()

    print(json.dumps({
        "model_id": model_id, "state": entry.state, "device": registry.device.type,
        "precision": registry.precision, "batch": 1, "input_shapes": shapes,
        "availability": first.availability, "load_ms": load_ms, "first_inference_ms": first_ms,
        "stages": {k: stats(v) for k, v in stages.items()}, "total": timed(whole),
        "import_peak_rss_MiB": baseline_rss, "loaded_peak_rss_MiB": loaded_rss,
        "peak_rss_MiB": peak_rss_mib(),
        "gpu_allocated_MiB": torch.cuda.memory_allocated() / 2**20 if cuda else None,
        "gpu_peak_allocated_MiB": torch.cuda.max_memory_allocated() / 2**20 if cuda else None,
        "gpu_peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20 if cuda else None,
    }))


def model1() -> None:
    import torch

    configurations = [("cpu", "fp32")]
    if torch.cuda.is_available():
        configurations += [("cuda", "fp32"), ("cuda", "fp16")]
    rows: list[dict[str, Any]] = []
    for model_id in MODELS:
        for device, precision in configurations:
            done = subprocess.run(
                [sys.executable, "-m", "evaluation.phase13a_profile", "model1-one",
                 "--model", model_id, "--device", device, "--precision", precision],
                capture_output=True, text=True, check=False, cwd=REPO)
            if done.returncode:
                rows.append({"model_id": model_id, "device": device, "precision": precision,
                             "status": "FAILED", "error": done.stderr.strip()[-400:]})
                print(f"[model1] {model_id} {device}/{precision} FAILED", flush=True)
                continue
            rows.append(json.loads(done.stdout.strip().splitlines()[-1]))
            r = rows[-1]
            print(f"[model1] {model_id} {device}/{precision} load={r['load_ms']:.0f}ms "
                  f"total={r['total']['median_ms']:.2f}ms rss={r['peak_rss_MiB']:.0f}MiB "
                  f"vram={r['gpu_peak_reserved_MiB']}", flush=True)
    save("model1_baseline.json", {
        "inputs": "synthetic (random 512x512 PNG; constant sensor window); no accuracy measured",
        "isolation": "one process per model and configuration; checkpoint files may be in the "
                     "operating-system cache, so load is not a cold-disk time",
        "warmup": WARMUP, "measured": REPEATS, "excluded": ["wisard-thermal"], "rows": rows,
    })


# ---------------------------------------------------------------- Model 2
def reports(count: int, mission: UUID) -> list[Any]:
    """Synthetic drone reports: alternating environment and hazard findings over a grid."""
    from agents.drone_agent.reporting import Mailbox
    from agents.shared.domain import Cell, Evidence, Observation
    from communication.messages import EnvironmentalObservation, HazardDetection

    boxes = {a: Mailbox(a, mission, count) for a in ("d0", "d1")}
    out = []
    for n in range(count):
        owner = "d0" if n % 4 < 2 else "d1"
        observation = Observation(
            observation_id=UUID(int=n + 1), cell=Cell(x=n % 12, y=(n // 12) % 10),
            observed_ms=5, confidence=0.6,
            evidence=(Evidence(evidence_id=UUID(int=10**9 + n), origin=owner, captured_ms=5,
                               modality="image", artifact_key="synthetic-profile"),))
        payload = (HazardDetection(message_type="hazard_detection", observation=observation,
                                   hazard="water")
                   if n % 2 else EnvironmentalObservation(
                       message_type="environmental_observation", observation=observation,
                       feature="water"))
        boxes[owner].publish(payload, 5)
        out.append((owner, boxes[owner].sent[-1]))
    return out


def model2() -> None:
    from agents.command_agent.agent import CommandAgent, Settings
    from agents.drone_agent.evidence import fuse_environment
    from agents.shared.domain import Finding

    mission = UUID(int=13)
    settings = Settings()
    rows: dict[str, Any] = {}
    for count in (100, 500, 2000):
        messages = reports(count, mission)
        agent = CommandAgent(mission, frozenset(("d0", "d1")), settings)
        parts: dict[str, list[float]] = {"recommend": [], "assess": [], "priority": []}

        def wrap(owner: Any, name: str, key: str, parts: dict[str, list[float]] = parts) -> None:
            original = getattr(owner, name)

            def call(*args: Any) -> Any:
                started = time.perf_counter()
                result = original(*args)
                parts[key].append((time.perf_counter() - started) * 1000)
                return result

            setattr(owner, name, call)

        wrap(agent.review, "recommend", "recommend")
        wrap(agent.assessment, "assess", "assess")
        wrap(agent.urgency, "assess_priority", "priority")
        latencies: dict[str, list[float]] = {"environment_ingest": [], "hazard_process": []}
        for owner, message in messages:
            started = time.perf_counter()
            agent.consume(message, owner, 5)
            elapsed = (time.perf_counter() - started) * 1000
            kind = ("hazard_process" if message.payload.message_type == "hazard_detection"
                    else "environment_ingest")
            latencies[kind].append(elapsed)
        tail = len(latencies["hazard_process"]) // 5
        findings: list[Finding] = [r.finding for r in agent.findings.values()]

        def fuse(items: list[Finding] = findings) -> Any:
            return fuse_environment(items)

        def serialize_checkpoint(current: CommandAgent = agent) -> str:
            return current.checkpoint().model_dump_json()

        rows[str(count)] = {
            "findings_admitted": len(agent.findings), "incidents": len(agent.incidents),
            **{k: stats(v) for k, v in latencies.items()},
            "hazard_process_last_fifth": stats(latencies["hazard_process"][-tail:]),
            "hazard_process_first_fifth": stats(latencies["hazard_process"][:tail]),
            **{f"{k}_step": stats(v) for k, v in parts.items() if v},
            "deterministic_fusion": timed(fuse, 20, 2),
            "checkpoint_serialize": timed(serialize_checkpoint, 10, 1),
            "peak_rss_MiB": peak_rss_mib(),
        }
        print(f"[model2] findings={count} hazard_median="
              f"{rows[str(count)]['hazard_process']['median_ms']:.3f}ms "
              f"first={rows[str(count)]['hazard_process_first_fifth']['median_ms']:.3f} "
              f"last={rows[str(count)]['hazard_process_last_fifth']['median_ms']:.3f}", flush=True)
    save("model2_baseline.json", {
        "inputs": "synthetic reports, one mission tick, 12x10 grid, fusion mode",
        "note": "behaviour unchanged; step timers wrap existing methods", "by_report_count": rows,
    })


# ---------------------------------------------------------------- communication and backend
def sqlite_commits(target: str) -> dict[str, Any]:
    connection = sqlite3.connect(target)
    if target != ":memory:":  # the same settings the backend uses
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("create table if not exists t(id text, body text)")
    connection.commit()

    def one() -> None:
        connection.execute("insert into t values(?,?)", (uuid4().hex, "x" * 512))
        connection.commit()

    result = timed(one, 100, 10)
    connection.close()
    return result


def backend() -> None:
    guard_engine()
    sys.path.insert(0, str(REPO / "tests"))
    from backend_support import Api, make_settings, migrate  # reuse existing fixtures
    from fastapi.testclient import TestClient

    from backend.application import create_app
    from backend.core.permissions import GlobalRole
    from communication.messages import Envelope

    message = reports(2, UUID(int=13))[1][1]
    raw = message.model_dump_json().encode()
    serialization = {
        "bytes": len(raw),
        "serialize": timed(lambda: message.model_dump_json(), 500, 20),
        "deserialize_validate": timed(lambda: Envelope.model_validate_json(raw), 500, 20),
    }
    TMP.mkdir(parents=True, exist_ok=True)
    database = TMP / f"{uuid4().hex}.db"
    migrate(f"sqlite:///{database.as_posix()}")
    settings = make_settings(database, TMP, simulation_tick_delay_ms=0)
    persist: list[float] = []
    steps: list[float] = []
    with TestClient(create_app(settings)) as client:
        api = Api(client, settings)
        api.user("coord", GlobalRole.COORDINATOR)
        api.login("coord")
        manager = client.app.state.container.runtime  # type: ignore[attr-defined]
        original_persist = manager.persist

        def persist_timed(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            result = original_persist(*args, **kwargs)
            persist.append((time.perf_counter() - started) * 1000)
            return result

        def tick_timed(runtime: Any) -> None:
            started = time.perf_counter()
            runtime.ctx.step()
            steps.append((time.perf_counter() - started) * 1000)
            runtime.ticks += 1
            manager.persist(runtime, checkpoint=runtime.ticks % settings.snapshot_every_ticks == 0)

        manager.persist, manager._tick = persist_timed, tick_timed
        mid = api.mission("coord", agents=6, seed=require_profiling_seed(SEED), horizon=60)["id"]
        wall = time.perf_counter()
        assert api.post(f"/api/v1/missions/{mid}/start", "coord").status_code == 200
        api.wait_status(mid, "coord", {"completed", "failed"}, timeout=600)
        mission_seconds = time.perf_counter() - wall
        status = api.get(f"/api/v1/missions/{mid}", "coord").json()["status"]
        endpoints = {}
        for name, path in (("health", "/api/v1/health"), ("mission", f"/api/v1/missions/{mid}"),
                           ("events", f"/api/v1/missions/{mid}/events"),
                           ("summary", f"/api/v1/missions/{mid}/summary")):
            code = api.get(path, "coord").status_code
            def request(url: str = path) -> Any:
                return api.get(url, "coord")

            endpoints[name] = (timed(request, 40, 3)
                               if code == 200 else {"status": "NOT TESTED", "http": code})
    database_bytes = database.stat().st_size
    commits = {"file_on_D": sqlite_commits(str(TMP / f"{uuid4().hex}.db")),
               "in_memory": sqlite_commits(":memory:")}
    result: dict[str, Any] = {
        "scope": "in-process TestClient and mission loop; no network; SQLite only; "
                 "PostgreSQL NOT TESTED",
        "serialization": serialization,
        "mission": {"agents": 6, "horizon": 60, "seed": SEED, "status": status,
                    "seconds": mission_seconds, "database_bytes": database_bytes,
                    "step": stats(steps), "persist_transaction": stats(persist)},
        "api_in_process": endpoints, "raw_sqlite_commit": commits,
        "peak_rss_MiB": peak_rss_mib(),
    }
    save("communication_backend_baseline.json", result)
    print(f"[backend] mission={status} step_median={result['mission']['step']['median_ms']:.1f}ms "
          f"persist_median={result['mission']['persist_transaction']['median_ms']:.1f}ms "
          f"commit_D={commits['file_on_D']['median_ms']:.2f}ms", flush=True)


# ---------------------------------------------------------------- simulator
def simulator() -> None:
    guard_engine()
    import agents.drone_agent.agent as drone
    from agents.command_agent.agent import Settings as CommandSettings
    from simulation.adapters.model1 import Fleet
    from simulation.core.configuration import Scenario, load
    from simulation.core.engine import Engine

    def build(agents: int, with_command: bool) -> tuple[Engine, Fleet]:
        config = Scenario.model_validate(load("flood_basic").model_dump() | {
            "agents": agents, "horizon": 30, "seed": require_profiling_seed(SEED)})
        engine = Engine(config)
        return engine, Fleet(engine, coordination="shared_information",
                             command=CommandSettings() if with_command else None)

    rows: list[dict[str, Any]] = []
    gate: list[float] = []
    module: Any = drone  # timing wrapper around the existing check; behaviour unchanged
    original = module.authorize

    def authorize(*args: Any) -> Any:
        started = time.perf_counter()
        result = original(*args)
        gate.append((time.perf_counter() - started) * 1000)
        return result

    module.authorize = authorize
    for agents in (3, 6, 20):
        for with_command in (False, True):
            gate.clear()
            inits, ticks = [], []
            cpu, wall = time.process_time(), time.perf_counter()
            for episode in range(4):
                started = time.perf_counter()
                engine, fleet = build(agents, with_command)
                init = (time.perf_counter() - started) * 1000
                inside = []
                while engine.reason == "running":
                    started = time.perf_counter()
                    fleet.advance(engine)
                    inside.append((time.perf_counter() - started) * 1000)
                if episode:  # the first episode is warm-up
                    inits.append(init)
                    ticks += inside
                else:
                    gate.clear()
            rows.append({
                "agents": agents, "command_agent": with_command, "init": stats(inits),
                "tick": stats(ticks), "safety_check": stats(gate),
                "safety_share_of_tick": sum(gate) / sum(ticks),
                "cpu_to_wall": (time.process_time() - cpu) / (time.perf_counter() - wall),
                "peak_rss_MiB": peak_rss_mib(),
            })
            print(f"[simulator] agents={agents} command={with_command} "
                  f"tick_median={rows[-1]['tick']['median_ms']:.2f}ms "
                  f"p95={rows[-1]['tick']['p95_ms']:.2f}", flush=True)
    module.authorize = original
    profiler = cProfile.Profile()
    engine, fleet = build(6, True)
    profiler.enable()
    while engine.reason == "running":
        fleet.advance(engine)
    profiler.disable()
    table: dict[Any, Any] = pstats.Stats(profiler).stats  # type: ignore[attr-defined]
    total = sum(v[2] for v in table.values())

    def label(key: tuple[str, int, str]) -> str:
        path = Path(key[0])
        where = (path.relative_to(REPO).as_posix() if path.is_absolute()
                 and path.is_relative_to(REPO) else path.name)
        return f"{where}:{key[1]}:{key[2]}"

    own = sorted(table.items(), key=lambda kv: -kv[1][2])[:12]
    cumulative = sorted(((k, v) for k, v in table.items() if str(REPO) in k[0]),
                        key=lambda kv: -kv[1][3])[:15]
    save("simulator_baseline.json", {
        "scenario": "flood_basic, shared_information, horizon 30", "seed": SEED,
        "episodes_measured": 3, "rows": rows,
        "cprofile_6_agents_command": {
            "note": "profiler overhead inflates absolute times; use shares",
            "total_seconds": total,
            "top_own_time": [{"function": label(k), "calls": v[1], "share": v[2] / total}
                             for k, v in own],
            "top_cumulative_repository": [
                {"function": label(k), "calls": v[1], "seconds": v[3]} for k, v in cumulative],
        },
    })
    for k, v in own[:8]:
        print(f"[cprofile] {v[2] / total:.1%} {label(k)}", flush=True)
    for k, v in cumulative[:10]:
        print(f"[cprofile-cum] {v[3]:.3f}s {label(k)}", flush=True)


# ---------------------------------------------------------------- figures and CSV
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"


def bars(name: str, title: str, unit: str, labels: list[str],
         series: list[tuple[str, str, list[float]]], stacked: bool = False) -> None:
    group = 14 if stacked else 14 * len(series)
    height = 90 + len(labels) * (group + 12)
    left, width = 230, 620
    top_value = max((sum(s[2][i] for s in series) if stacked else
                     max(s[2][i] for s in series)) for i in range(len(labels))) or 1
    svg = [(f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" '
            'font-family="system-ui,sans-serif" font-size="12">'),
           f'<rect width="960" height="{height}" fill="#fcfcfb"/>',
           f'<text x="20" y="24" font-size="15" fill="#0b0b0b">{title}</text>']
    for i, (label, color, _) in enumerate(series):
        key_x = 20 + 190 * i
        svg.append(f'<rect x="{key_x}" y="38" width="12" height="12" fill="{color}"/>'
                   f'<text x="{key_x + 18}" y="48" fill="#52514e">{label}</text>')
    y = 70.0
    for i, label in enumerate(labels):
        svg.append(f'<text x="{left - 8}" y="{y + group / 2 + 4}" text-anchor="end" '
                   f'fill="#0b0b0b">{label}</text>')
        x = float(left)
        for j, (_, color, values) in enumerate(series):
            size = width * values[i] / top_value
            row = y if stacked else y + 14 * j
            start = x if stacked else float(left)
            svg.append(f'<rect x="{start:.1f}" y="{row}" width="{max(size, 0.5):.1f}" '
                       f'height="12" fill="{color}"/>')
            if not stacked:
                svg.append(f'<text x="{left + size + 6:.1f}" y="{row + 10}" fill="#52514e">'
                           f'{values[i]:,.1f} {unit}</text>')
            x += size
        if stacked:
            svg.append(f'<text x="{x + 6:.1f}" y="{y + 10}" fill="#52514e">'
                       f'{x_total(series, i):,.1f} {unit}</text>')
        y += group + 12
    svg.append("</svg>")
    (OUT / name).write_text("\n".join(svg), encoding="utf8")


def x_total(series: list[tuple[str, str, list[float]]], index: int) -> float:
    return sum(s[2][index] for s in series)


def report() -> None:
    def read(name: str) -> Any:
        return json.loads((OUT / name).read_bytes())

    models = read("model1_baseline.json")["rows"]
    comms, sim = read("communication_backend_baseline.json"), read("simulator_baseline.json")
    command_agent = read("model2_baseline.json")["by_report_count"]
    rows: list[dict[str, Any]] = []

    def add(area: str, name: str, config: str, metric: str, values: dict[str, Any]) -> None:
        if "mean_ms" in values:
            rows.append({"area": area, "item": name, "configuration": config,
                         "metric": metric, **values})

    for r in models:
        config = f"{r['device']}/{r['precision']}"
        for stage, values in r["stages"].items():
            add("model1", r["model_id"], config, stage, values)
        add("model1", r["model_id"], config, "total", r["total"])
    for count, values in command_agent.items():
        for metric, entry in values.items():
            if isinstance(entry, dict):
                add("model2", count, "cpu", metric, entry)
    for metric in ("serialize", "deserialize_validate"):
        add("communication", "envelope", "cpu", metric, comms["serialization"][metric])
    for metric in ("step", "persist_transaction"):
        add("backend", "mission_6_agents", "sqlite", metric, comms["mission"][metric])
    for name, values in comms["api_in_process"].items():
        add("backend", name, "sqlite", "api", values)
    for name, values in comms["raw_sqlite_commit"].items():
        add("backend", name, "sqlite", "raw_commit", values)
    for r in sim["rows"]:
        config = f"{r['agents']} agents, command={r['command_agent']}"
        for metric in ("init", "tick", "safety_check"):
            add("simulator", "flood_basic", config, metric, r[metric])
    with (OUT / "performance_measurements.csv").open("w", newline="", encoding="utf8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    find = {(r["model_id"], r["device"], r["precision"]): r for r in models}
    names = [m for m in MODELS if (m, "cpu", "fp32") in find]
    configs = [("CPU FP32", BLUE, "cpu", "fp32"), ("CUDA FP32", ORANGE, "cuda", "fp32"),
               ("CUDA FP16", AQUA, "cuda", "fp16")]
    present = [c for c in configs if all((m, c[2], c[3]) in find for m in names)]
    bars("fig_latency.svg", "Median end-to-end perception latency, batch 1, synthetic input",
         "ms", names,
         [(c[0], c[1], [find[m, c[2], c[3]]["total"]["median_ms"] for m in names])
          for c in present])
    gpu = "cuda" if (names[0], "cuda", "fp32") in find else "cpu"
    parts = (("preprocess", BLUE), ("transfer", AQUA), ("inference", ORANGE),
             ("postprocess", YELLOW))
    bars("fig_stages.svg", f"Median stage time on {gpu} FP32 (stacked)", "ms", names,
         [(p, c, [find[m, gpu, "fp32"]["stages"][p]["median_ms"] for m in names])
          for p, c in parts], stacked=True)
    bars("fig_loading.svg", "Model load time in a fresh process (files possibly cached)", "ms",
         names, [(c[0], c[1], [find[m, c[2], c[3]]["load_ms"] for m in names])
                 for c in present[:2]])
    memory = [("Process RSS, CPU run", BLUE, [find[m, "cpu", "fp32"]["peak_rss_MiB"]
                                              for m in names])]
    if gpu == "cuda":
        memory += [
            ("Process RSS, CUDA run", ORANGE,
             [find[m, "cuda", "fp32"]["peak_rss_MiB"] for m in names]),
            ("VRAM reserved, FP32", AQUA,
             [find[m, "cuda", "fp32"]["gpu_peak_reserved_MiB"] for m in names])]
    bars("fig_memory.svg", "Peak memory, one model per process", "MiB", names, memory)
    six = next(r for r in sim["rows"] if r["agents"] == 6 and r["command_agent"])
    costs = [("backend persist per tick", comms["mission"]["persist_transaction"]["median_ms"]),
             ("backend simulation step", comms["mission"]["step"]["median_ms"]),
             ("simulator tick, 6 agents", six["tick"]["median_ms"]),
             ("Model 2 hazard report, 2000", command_agent["2000"]["hazard_process"]["median_ms"]),
             ("raw SQLite commit on D:", comms["raw_sqlite_commit"]["file_on_D"]["median_ms"])]
    bars("fig_system_costs.svg", "Median system costs (different units of work)", "ms",
         [c[0] for c in costs], [("median", BLUE, [c[1] for c in costs])])
    print(f"[report] rows={len(rows)} figures=5", flush=True)


def main() -> None:
    steps = {"environment": environment, "model1": model1, "model2": model2,
             "backend": backend, "simulator": simulator, "report": report}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(*steps, "all", "model1-one"))
    parser.add_argument("--model")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--precision", default="fp32")
    args = parser.parse_args()
    if args.command == "model1-one":
        model1_one(args.model, args.device, args.precision)
        return
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    if args.command == "all":
        for name in steps:  # each area in a fresh process so memory figures do not accumulate
            print(f"[phase13a] {name}", flush=True)
            subprocess.run([sys.executable, "-u", "-m", "evaluation.phase13a_profile", name],
                           check=True, cwd=REPO)
        return
    steps[args.command]()


if __name__ == "__main__":
    main()
