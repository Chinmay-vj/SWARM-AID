"""Phase 13 cluster 1 measurements (perception, Model 2, memory). Synthetic inputs only.

    python -u -m evaluation.phase13_cluster1 all --label before     (then --label after)
    python -u -m evaluation.phase13_cluster1 verify --label after   (outputs against "before")

Writes under D:/SWARM-AID-DATA/runs/phase13/cluster1/<label>. No training, no scenarios.
"""

import argparse
import ctypes
import hashlib
import io
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any
from uuid import UUID

from evaluation.process_memory import peak_rss_mib

DATA = Path("D:/SWARM-AID-DATA")
ROOT = DATA / "runs/phase13/cluster1"
REGISTRY = DATA / "runs/phase11j/runtime_model_registry.json"
REPO = Path(__file__).resolve().parents[1]
IMAGE_MODELS = ("rescuenet", "floodnet", "flame", "wisard-rgb")
MODELS = (*IMAGE_MODELS, "esc50", "uci-co", "environment-fusion-neural")
ROUNDS, WARMUP, MEASURED = 3, 5, 40
SIZES = (100, 500, 1000, 2000)
# Fixed before any optimized output was seen: CPU must be bit-identical; CUDA the same,
# and any difference above this absolute value is a failure.
CUDA_TOLERANCE = 1e-5


def rss_mib() -> float:
    """Current working set (peak_rss_mib reports the peak)."""

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in
            ("peak", "working", "qpp", "qp", "qpnp", "qnp", "page", "peak_page")]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return float(counters.working) / 2**20


def stats(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {"samples": len(values), "mean_ms": mean(values), "median_ms": median(values),
            "p95_ms": ordered[max(0, int(0.95 * len(ordered) + 0.999) - 1)],
            "sd_ms": stdev(values) if len(values) > 1 else 0.0}


def timed(call: Any, measured: int = MEASURED, warmup: int = WARMUP) -> dict[str, float | int]:
    for _ in range(warmup):
        call()
    values = []
    for _ in range(measured):
        started = time.perf_counter()
        call()
        values.append((time.perf_counter() - started) * 1000)
    return stats(values)


def child(*args: str) -> Any:
    done = subprocess.run([sys.executable, "-m", "evaluation.phase13_cluster1", *args],
                          capture_output=True, text=True, check=False, cwd=REPO)
    if done.returncode:
        raise RuntimeError(done.stderr[-1500:])
    return json.loads(done.stdout.strip().splitlines()[-1])


def save(label: str, name: str, value: Any) -> None:
    (ROOT / label).mkdir(parents=True, exist_ok=True)
    (ROOT / label / name).write_text(json.dumps(value, indent=2), encoding="utf8")


def registry_for(device: str, **options: Any) -> Any:
    from evaluation.model1.registry import ModelRegistry

    return ModelRegistry.from_file(REGISTRY, DATA, device=device,
                                   **({"max_resident": 8} | options))


def inputs(registry: Any) -> dict[str, list[Any]]:
    """Several synthetic inputs per model, including EXIF rotation, grayscale and odd sizes."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(13)

    def encode(array: Any, kind: str, orientation: int | None = None) -> bytes:
        image = Image.fromarray(array)
        buffer = io.BytesIO()
        exif = Image.Exif()
        if orientation:
            exif[274] = orientation
        image.save(buffer, kind, exif=exif)
        return buffer.getvalue()

    noise = rng.integers(0, 255, (512, 512, 3), dtype=np.uint8)
    ramp = np.dstack([np.tile(np.arange(640, dtype=np.uint16) % 256, (360, 1))] * 3).astype(
        np.uint8)
    images = [encode(noise, "PNG"), encode(ramp, "JPEG"), encode(ramp, "JPEG", 6),
              encode(noise[..., 0], "PNG"), encode(noise[:37, :91], "PNG"),
              encode(np.zeros((300, 500, 3), dtype=np.uint8), "PNG")]
    uci = registry.entries["uci-co"].config
    window = np.tile(np.asarray(uci["normalization_mean"], dtype=np.float32),
                     (int(uci["window"]), 1))
    gap = window.copy()
    gap[::3, 1] = -200
    return {
        **{m: images for m in IMAGE_MODELS},
        "esc50": [rng.standard_normal((498, 40)).astype(np.float32) for _ in range(3)],
        "uci-co": [window, window * 1.1, gap],
        "environment-fusion-neural": [
            ([[1, 0, 0, 0, 1, 1]] * 3, [True, True, True]),
            ([[0, 1, 0, 0, 1, 1]] * 3, [True, False, True]),
            ([[0, 0, 0, 0, 0, 0]] * 3, [False, False, False])],
    }


def sync(registry: Any) -> None:
    import torch

    if registry.device.type == "cuda":
        torch.cuda.synchronize()


def raw_output(runtime: Any, model_id: str, payload: Any) -> Any:
    import torch

    registry = runtime.registry
    entry = registry.entries[model_id]
    model = registry.get(model_id)
    moved = tuple(x.to(registry.device) for x in runtime._prepare(entry, payload))
    with torch.inference_mode():
        out = model([moved[0]]) if entry.task == "object_detection" else model(*moved)
    if entry.task == "semantic_segmentation":
        out = {"logits": out["out"]}
    elif entry.task == "object_detection":
        out = out[0]
    elif not isinstance(out, tuple):
        out = (out,)
    if isinstance(out, tuple):
        out = {str(i): v for i, v in enumerate(out)}
    return {"inputs": [x.cpu() for x in moved], **{k: v.cpu() for k, v in out.items()}}


def frame_perception(registry: Any, image: bytes) -> tuple[Any, Any]:
    """One agent frame consumed by every image model, as MediaPerception does it."""
    from agents.drone_agent.evidence import EvidenceLedger
    from agents.shared.domain import Cell, Evidence, SensorFrame
    from evaluation.model1.perception import MediaPerception, PerceptionRuntime

    samples = tuple(
        Evidence(evidence_id=UUID(int=n), origin="d0", captured_ms=5, modality=m,
                 artifact_key="synthetic")
        for n, m in ((1, "image"), (2, "thermal")))
    frame = SensorFrame(agent_id="d0", tick_ms=5, samples=samples, cell=Cell(x=1, y=1),
                        battery_fraction=1)

    class Resolver:
        def resolve(self, agent_id: str, evidence: Any) -> bytes:
            return image

    ledger = EvidenceLedger("d0", UUID(int=7))
    return MediaPerception(PerceptionRuntime(registry), Resolver(), IMAGE_MODELS, ledger,
                           "synthetic_fixture"), frame


def references(device: str, folder: Path) -> dict[str, Any]:
    import torch

    from evaluation.model1.perception import PerceptionRuntime

    registry = registry_for(device)
    runtime = PerceptionRuntime(registry)
    tensors, records = {}, {}
    for model_id, payloads in inputs(registry).items():
        for i, payload in enumerate(payloads):
            tensors[f"{model_id}/{i}"] = raw_output(runtime, model_id, payload)
            records[f"{model_id}/{i}"] = runtime.infer(model_id, payload).model_dump(mode="json")
    for name, bad in {"empty": b"", "garbage": b"not-an-image", "missing": None,
                      "excluded": b"x"}.items():
        model_id = "wisard-thermal" if name == "excluded" else "flame"
        records[f"invalid/{name}"] = runtime.infer(model_id, bad).model_dump(mode="json")
    for i, image in enumerate((*inputs(registry)["flame"], b"not-an-image")):
        perception, frame = frame_perception(registry, image)
        found = perception.perceive(frame)
        records[f"frame/{i}"] = {
            "findings": [f.model_dump(mode="json") for f in found],
            "ledger": [x.model_dump(mode="json") for x in perception.ledger.items]}
    folder.mkdir(parents=True, exist_ok=True)
    torch.save(tensors, folder / f"reference_{device}.pt")
    (folder / f"reference_{device}.json").write_text(json.dumps(records, indent=1), "utf8")
    return {"device": device, "tensor_cases": len(tensors), "record_cases": len(records)}


def compare(device: str) -> dict[str, Any]:
    import torch

    old = torch.load(ROOT / "before" / f"reference_{device}.pt", weights_only=True)
    new = torch.load(ROOT / "after" / f"reference_{device}.pt", weights_only=True)
    worst_absolute = worst_relative = 0.0
    different: list[str] = []
    if old.keys() != new.keys():
        different.append("case set")
    for case, values in old.items():
        for key, expected in values.items():
            actual = new[case][key]
            pairs = (zip(expected, actual, strict=True) if isinstance(expected, list)
                     else [(expected, actual)])
            for a, b in pairs:
                if a.shape != b.shape or a.dtype != b.dtype:
                    different.append(f"{case}/{key} shape")
                    continue
                if torch.equal(a, b):
                    continue
                delta = (a.double() - b.double()).abs()
                worst_absolute = max(worst_absolute, float(delta.max()))
                worst_relative = max(worst_relative,
                                     float((delta / a.double().abs().clamp_min(1e-12)).max()))
                different.append(f"{case}/{key}")
    before = json.loads((ROOT / "before" / f"reference_{device}.json").read_bytes())
    after = json.loads((ROOT / "after" / f"reference_{device}.json").read_bytes())
    changed = [k for k in before if before[k] != after.get(k)]
    limit = 0.0 if device == "cpu" else CUDA_TOLERANCE
    return {"device": device, "tensor_cases": len(old), "record_cases": len(before),
            "bit_identical_tensors": not different, "different": different[:20],
            "max_absolute": worst_absolute, "max_relative": worst_relative,
            "records_identical": not changed and before.keys() == after.keys(),
            "records_changed": changed[:20],
            "passed": not changed and worst_absolute <= limit
            and not any("shape" in d or d == "case set" for d in different)}


# ---------------------------------------------------------------- measurements
def load_one(model_id: str, device: str) -> dict[str, Any]:
    started = time.perf_counter()
    import torch  # noqa: F401

    registry = registry_for(device)
    imports = (time.perf_counter() - started) * 1000
    base = peak_rss_mib()
    started = time.perf_counter()
    registry.get(model_id)
    sync(registry)
    first = (time.perf_counter() - started) * 1000
    loaded_peak, loaded_now = peak_rss_mib(), rss_mib()
    repeat = []
    for _ in range(3):  # reload after release: library imports are already paid
        registry.release()
        started = time.perf_counter()
        registry.get(model_id)
        sync(registry)
        repeat.append((time.perf_counter() - started) * 1000)
    return {"model_id": model_id, "device": device, "imports_ms": imports, "first_load_ms": first,
            "reload_ms": median(repeat), "rss_before_load_MiB": base,
            "peak_rss_after_first_load_MiB": loaded_peak, "rss_after_first_load_MiB": loaded_now}


def latency(device: str) -> dict[str, Any]:
    import torch

    from evaluation.model1.perception import PerceptionRuntime

    registry = registry_for(device)
    runtime = PerceptionRuntime(registry)
    cases = inputs(registry)
    result: dict[str, Any] = {"device": device, "models": {}}

    def one(model_id: str) -> None:
        runtime.infer(model_id, cases[model_id][0])
        sync(registry)

    for model_id in MODELS:
        registry.get(model_id)
        result["models"][model_id] = timed(lambda m=model_id: one(m))
    perception, frame = frame_perception(registry, cases["flame"][0])

    def whole_frame() -> None:
        perception.perceive(frame)
        sync(registry)
        perception.ledger.items.clear()  # keep the measurement independent of ledger size

    result["frame_four_image_models"] = timed(whole_frame)
    segmentation = registry.get("rescuenet")
    with torch.inference_mode():
        output = segmentation(runtime._prepare(
            registry.entries["rescuenet"], cases["rescuenet"][0])[0].to(registry.device))

    def post() -> None:
        runtime._interpret(registry.entries["rescuenet"], output)
        sync(registry)

    result["segmentation_postprocess"] = timed(post)
    return result


def allocation(name: str) -> dict[str, Any]:
    """One pass over all seven models, per placement."""
    import torch

    from evaluation.model1.perception import PerceptionRuntime

    cuda_models = {"all_cpu": (), "all_cuda": MODELS, "mixed": ("rescuenet", "floodnet",
                                                              "wisard-rgb"),
                   "rtx2060_config": MODELS}[name]
    extra: dict[str, Any] = ({"precision": "fp16", "max_resident": 2}
                             if name == "rtx2060_config" else {})
    runtimes = {d: PerceptionRuntime(registry_for(d, **extra)) for d in ("cpu", "cuda")}
    cases = inputs(runtimes["cpu"].registry)

    def one_pass() -> None:
        for model_id in MODELS:
            runtime = runtimes["cuda" if model_id in cuda_models else "cpu"]
            runtime.infer(model_id, cases[model_id][0])
        torch.cuda.synchronize()

    measured = timed(one_pass, 6 if extra else 30, 2)
    module: Any = torch
    cuda = module.cuda.is_initialized()
    loads = {k: sum(r.registry.loads.values()) for k, r in runtimes.items()}
    return {"placement": name, "pass": measured, "model_loads": loads,
            "peak_rss_MiB": peak_rss_mib(), "rss_MiB": rss_mib(),
            "gpu_peak_allocated_MiB": torch.cuda.max_memory_allocated() / 2**20 if cuda else None,
            "gpu_peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20 if cuda else None}


def device_used_mib() -> float:
    done = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                          capture_output=True, text=True, check=True)
    return float(done.stdout.split()[0])


def resources(device: str) -> dict[str, Any]:
    import torch

    from evaluation.model1.perception import PerceptionRuntime

    cuda = device == "cuda"

    def sample(stage: str) -> dict[str, Any]:
        return {"stage": stage, "rss_MiB": rss_mib(), "peak_rss_MiB": peak_rss_mib(),
                "allocated_MiB": torch.cuda.memory_allocated() / 2**20 if cuda else None,
                "reserved_MiB": torch.cuda.memory_reserved() / 2**20 if cuda else None,
                "peak_allocated_MiB": torch.cuda.max_memory_allocated() / 2**20 if cuda else None,
                "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20 if cuda else None,
                "device_total_used_MiB": device_used_mib() if cuda else None}

    stages = [sample("before_cuda_use")] if cuda else []
    registry = registry_for(device)
    runtime = PerceptionRuntime(registry)
    cases = inputs(registry)
    stages.append(sample("before_model_loading"))
    parameters = {}
    for model_id in MODELS:
        model = registry.get(model_id)
        parameters[model_id] = sum(t.numel() * t.element_size()
                                   for t in (*model.parameters(), *model.buffers())) / 2**20
    stages.append(sample("after_loading"))

    def one_pass() -> None:
        for model_id in MODELS:
            runtime.infer(model_id, cases[model_id][0])
        sync(registry)

    for _ in range(3):
        one_pass()
    stages.append(sample("after_warmup"))
    windows = []
    for window in range(5):
        for _ in range(40):
            one_pass()
        windows.append(sample(f"window_{window + 1}_after_{40 * (window + 1)}_passes"))
        print(f"[stability] {device} window {window + 1}/5 rss={windows[-1]['rss_MiB']:.0f}",
              file=sys.stderr, flush=True)
    loads = dict(registry.loads)
    registry.release()
    stages.append(sample("after_release"))
    return {"device": device, "stages": stages, "windows": windows, "model_loads": loads,
            "parameter_and_buffer_MiB": parameters}


def model2(size: int) -> dict[str, Any]:
    from agents.command_agent.agent import CommandAgent, Settings
    from evaluation.phase13a_profile import reports

    mission = UUID(int=13)
    messages = reports(size, mission)
    base = rss_mib()
    values: dict[str, list[float]] = {"environment": [], "hazard": []}
    total = 0.0
    for repeat in range(3 + 1):
        agent = CommandAgent(mission, frozenset(("d0", "d1")), Settings())
        for owner, message in messages:
            started = time.perf_counter()
            agent.consume(message, owner, 5)
            elapsed = (time.perf_counter() - started) * 1000
            if repeat:  # first pass is warm-up
                kind = ("hazard" if message.payload.message_type == "hazard_detection"
                        else "environment")
                values[kind].append(elapsed)
                total += elapsed
    per_pass = len(values["hazard"]) // 3
    last = [v for i, v in enumerate(values["hazard"]) if i % per_pass >= per_pass * 4 // 5]
    digest = hashlib.sha256(json.dumps(
        [agent.snapshot(), agent.checkpoint().model_dump(mode="json")],
        sort_keys=True, default=str).encode()).hexdigest()
    return {"size": size, "hazard": stats(values["hazard"]),
            "hazard_last_fifth": stats(last), "environment": stats(values["environment"]),
            "consume_all_ms": total / 3, "findings": len(agent.findings),
            "incidents": len(agent.incidents), "rss_growth_MiB": rss_mib() - base,
            "peak_rss_MiB": peak_rss_mib(), "state_sha256": digest}


def run(label: str, areas: tuple[str, ...]) -> None:
    import torch

    started = time.perf_counter()
    devices = ("cpu", "cuda") if torch.cuda.is_available() else ("cpu",)

    def note(text: str) -> None:
        print(f"[{label}] {text} elapsed={time.perf_counter() - started:.0f}s", flush=True)

    if "model1" in areas:
        for device in devices:
            note(f"reference outputs {child('references', '--label', label, '--device', device)}")
        loading, speed = [], []
        for round_ in range(ROUNDS):
            for device in devices:
                for model_id in MODELS:
                    loading.append(child("load-one", "--model", model_id, "--device", device)
                                   | {"round": round_})
                note(f"loading round {round_ + 1}/{ROUNDS} {device}")
                speed.append(child("latency", "--device", device) | {"round": round_})
                note(f"latency round {round_ + 1}/{ROUNDS} {device} frame="
                     f"{speed[-1]['frame_four_image_models']['median_ms']:.1f}ms")
        save(label, "loading.json", loading)
        save(label, "latency.json", speed)
    if "allocation" in areas:
        rows = []
        for name in ("all_cpu", "all_cuda", "mixed", "rtx2060_config"):
            rows.append(child("allocation-one", "--model", name))
            note(f"allocation {name} pass={rows[-1]['pass']['median_ms']:.1f}ms")
        save(label, "allocation.json", rows)
    if "resources" in areas:
        rows = []
        for device in devices:
            rows.append(child("resources-one", "--device", device))
            note(f"resources {device} peak_rss={rows[-1]['stages'][-1]['peak_rss_MiB']:.0f}MiB")
        save(label, "resources.json", rows)
    if "model2" in areas:
        rows = []
        for round_ in range(ROUNDS):
            for size in SIZES:
                rows.append(child("model2", "--size", str(size)) | {"round": round_})
            note(f"model2 round {round_ + 1}/{ROUNDS} hazard_2000="
                 f"{rows[-1]['hazard']['median_ms']:.3f}ms")
        save(label, "model2.json", rows)
    note("done")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "all", "model1", "allocation", "resources", "model2-run", "verify",
        "references", "load-one", "latency", "allocation-one", "resources-one", "model2"))
    parser.add_argument("--label", default="after", choices=("before", "after"))
    parser.add_argument("--model", default="")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--size", type=int, default=100)
    args = parser.parse_args()
    command = args.command
    if command == "all":
        run(args.label, ("model1", "allocation", "resources", "model2"))
    elif command in ("model1", "allocation", "resources", "model2-run"):
        run(args.label, (command.removesuffix("-run"),))
    elif command == "verify":
        import torch

        rows = [compare(d) for d in
                (("cpu", "cuda") if torch.cuda.is_available() else ("cpu",))]
        save("13b", "numerical_consistency_results.json",
             {"tolerance": {"cpu": 0.0, "cuda_absolute": CUDA_TOLERANCE}, "results": rows})
        print(json.dumps(rows, indent=1))
    else:
        result = (references(args.device, ROOT / args.label) if command == "references"
                  else load_one(args.model, args.device) if command == "load-one"
                  else latency(args.device) if command == "latency"
                  else allocation(args.model) if command == "allocation-one"
                  else resources(args.device) if command == "resources-one"
                  else model2(args.size))
        print(json.dumps(result))


if __name__ == "__main__":
    main()
