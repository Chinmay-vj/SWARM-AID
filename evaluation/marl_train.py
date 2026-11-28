"""Standalone IPPO/MAPPO launcher for symbolic simulation. Resumes at update boundaries.

    python -u -m evaluation.marl_train --algo mappo --run-dir D:/... --steps N --authorize-start
    python -u -m evaluation.marl_train --algo mappo --run-dir D:/... --smoke
"""

import argparse
import hashlib
import io
import json
import os
import signal
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import torch

from evaluation.marl_ppo import ActorCritic, Algorithm, make_batch, run_episode, update
from evaluation.process_memory import peak_rss_mib
from simulation.adapters import marl_contract as contract
from simulation.adapters.marl import SearchEnv
from simulation.core.configuration import Scenario, load

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO / "configs/marl/ppo-v1.json"
SOURCES = ("simulation/adapters/marl.py", "simulation/adapters/marl_contract.py",
           "evaluation/marl_ppo.py")
TRAIN_BASE, TRAIN_SPAN = 12000, 900  # 12900-12999 are kept for smoke and profiling
SMOKE_BASE, VALIDATION_BASE = 12900, 13000


def identity(algorithm: Algorithm, config: dict[str, Any], seed: int) -> dict[str, Any]:
    """Anything here that differs makes a checkpoint incompatible."""
    return {
        "algorithm": algorithm, "config": config, "seed": seed,
        "observation": contract.OBSERVATION_VERSION, "action": contract.ACTION_VERSION,
        "observation_size": contract.SIZE, "seed_protocol": contract.SEED_PROTOCOL_VERSION,
        "sources": {s: hashlib.sha256((REPO / s).read_bytes()).hexdigest() for s in SOURCES},
    }


def save(path: Path, payload: dict[str, Any]) -> str:
    buffer = io.BytesIO()
    torch.save(payload, buffer)
    data = buffer.getvalue()
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return hashlib.sha256(data).hexdigest()


def make_env(config: dict[str, Any], scenario: str) -> SearchEnv:
    values = load(scenario).model_dump() | {
        "agents": config["agents"], "horizon": config["horizon"]}
    return SearchEnv(Scenario.model_validate(values),
                     reward=contract.RewardConfig(version=config["reward_version"]))


def validate_policy(
    model: ActorCritic, config: dict[str, Any], episodes: int, device: torch.device
) -> dict[str, float]:
    rows = [
        run_episode(make_env(config, config["scenarios"][i % len(config["scenarios"])]), model,
                    VALIDATION_BASE + i, None, config["gamma"], config["gae_lambda"], device)[1]
        for i in range(episodes)
    ]
    return {k: mean(r[k] for r in rows) for k in ("coverage", "reward_total", "engine_invalid")}


def train(
    algorithm: Algorithm, config: dict[str, Any], run_dir: Path, *, steps: int, seed: int,
    device_name: str, resume: bool, deadline: float | None, smoke: bool,
    stop_after_updates: int | None = None,
) -> dict[str, Any]:
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    device = torch.device(device_name)
    torch.set_num_threads(config["torch_threads"])
    torch.manual_seed(seed)
    model = ActorCritic(algorithm, config["hidden"]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config["learning_rate"], eps=1e-5)
    generator = torch.Generator().manual_seed(seed + 1)
    who = identity(algorithm, config, seed) | {"smoke": smoke}
    latest = run_dir / "latest.pt"
    progress: dict[str, Any] = {"env_steps": 0, "episodes": 0, "updates": 0, "best": None,
                                "seconds": 0.0}
    if resume:
        saved = torch.load(latest, map_location="cpu", weights_only=True)
        if saved["identity"] != who:
            differing = [k for k in who if saved["identity"].get(k) != who[k]]
            raise ValueError(f"incompatible checkpoint; differs in {differing}")
        model.load_state_dict(saved["model"])
        optimizer.load_state_dict(saved["optimizer"])
        generator.set_state(saved["generator"])
        progress = saved["progress"]
    elif latest.exists():
        raise FileExistsError(f"{latest} exists; pass --resume or choose another run directory")
    run_dir.mkdir(parents=True, exist_ok=True)
    interrupted = False

    def request_stop(*_: object) -> None:
        nonlocal interrupted
        if interrupted:
            raise KeyboardInterrupt
        interrupted = True
        print("[signal] stopping after this update; press again to abort", flush=True)

    previous = signal.signal(signal.SIGINT, request_stop)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()
    started, this_run, done_updates = time.perf_counter(), 0, 0
    reason, last = "budget_reached", 0.0
    timings = {"rollout_seconds": 0.0, "update_seconds": 0.0}
    try:
        while progress["env_steps"] < steps:
            if interrupted:
                reason = "interrupted"
                break
            if stop_after_updates is not None and done_updates >= stop_after_updates:
                reason = "requested_boundary"
                break
            if deadline is not None and time.time() + 1.5 * last > deadline:
                reason = "deadline"
                break
            tick = time.perf_counter()
            rows: list[tuple[Any, ...]] = []
            episodes = []
            for _ in range(config["episodes_per_update"]):
                index = progress["episodes"]
                episode_seed = (SMOKE_BASE + index % 100 if smoke
                                else TRAIN_BASE + (seed * 97 + index) % TRAIN_SPAN)
                scenario = config["scenarios"][index % len(config["scenarios"])]
                transitions, metrics = run_episode(
                    make_env(config, scenario), model, episode_seed, generator,
                    config["gamma"], config["gae_lambda"], device)
                rows += transitions
                episodes.append(metrics)
                progress["episodes"] += 1
                progress["env_steps"] += metrics["steps"]
                this_run += metrics["steps"]
            rollout = time.perf_counter() - tick
            tick_update = time.perf_counter()
            diagnostics = update(model, optimizer, make_batch(rows, device), config, generator)
            updating = time.perf_counter() - tick_update
            timings["rollout_seconds"] += rollout
            timings["update_seconds"] += updating
            progress["updates"] += 1
            done_updates += 1
            record: dict[str, Any] = {
                "update": progress["updates"], "env_steps": progress["env_steps"],
                "episodes": progress["episodes"], "transitions": len(rows),
                "reward": mean(e["reward_total"] for e in episodes),
                "coverage": mean(e["coverage"] for e in episodes),
                "engine_invalid": mean(e["engine_invalid"] for e in episodes),
                "rollout_seconds": rollout, "update_seconds": updating, **diagnostics,
            }
            improved = False
            if (progress["updates"] % config["validate_every"] == 0
                    or progress["env_steps"] >= steps):
                record["validation"] = validate_policy(
                    model, config, config["validation_episodes"], device)
                score = record["validation"]["coverage"]
                improved = progress["best"] is None or score > progress["best"]
                if improved:
                    progress["best"] = score
            last = time.perf_counter() - tick
            progress["seconds"] += last
            payload = {"identity": who, "model": model.state_dict(),
                       "optimizer": optimizer.state_dict(), "generator": generator.get_state(),
                       "progress": progress}
            record["checkpoint_sha256"] = save(latest, payload)
            if improved:
                save(run_dir / "best.pt", payload)
            with (run_dir / "metrics.jsonl").open("a", encoding="utf8") as stream:
                stream.write(json.dumps(record) + "\n")
            elapsed = time.perf_counter() - started
            eta = elapsed / this_run * max(steps - progress["env_steps"], 0)
            memory = f"rss_MiB={peak_rss_mib():.0f}"
            if device.type == "cuda":
                memory += f" gpu_peak_MiB={torch.cuda.max_memory_allocated() / 2**20:.0f}"
            print(
                f"[{algorithm}] steps={progress['env_steps']}/{steps} "
                f"({100 * progress['env_steps'] / steps:.1f}%) episodes={progress['episodes']} "
                f"reward={record['reward']:.2f} coverage={record['coverage']:.3f} "
                f"pi_loss={diagnostics['policy_loss']:.4f} "
                f"v_loss={diagnostics['value_loss']:.3f} entropy={diagnostics['entropy']:.3f} "
                f"kl={diagnostics['approx_kl']:.4f} "
                + (f"val_coverage={record['validation']['coverage']:.3f} "
                   if "validation" in record else "")
                + f"elapsed_s={elapsed:.1f} eta_s={eta:.0f} {memory} "
                f"checkpoint=saved{' best_updated' if improved else ''}",
                flush=True,
            )
    finally:
        signal.signal(signal.SIGINT, previous)
    elapsed = time.perf_counter() - started
    result = {
        "algorithm": algorithm, "device": device.type, "reason": reason, **progress,
        "env_steps_this_run": this_run, "elapsed_seconds": elapsed,
        "env_steps_per_second": this_run / elapsed if elapsed else 0.0, **timings,
        "rollout_steps_per_second":
            this_run / timings["rollout_seconds"] if timings["rollout_seconds"] else 0.0,
        "parameters": sum(p.numel() for p in model.parameters()),
        "checkpoint_bytes": latest.stat().st_size if latest.exists() else 0,
        "peak_rss_MiB": peak_rss_mib(),
        "gpu_peak_allocated_MiB":
            torch.cuda.max_memory_allocated() / 2**20 if device.type == "cuda" else None,
        "gpu_peak_reserved_MiB":
            torch.cuda.max_memory_reserved() / 2**20 if device.type == "cuda" else None,
        "finished_at": datetime.now(UTC).isoformat(),
    }
    (run_dir / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf8")
    print(f"[done] reason={reason} steps={progress['env_steps']} run_dir={run_dir}", flush=True)
    return result


def load_config(path: Path, smoke: bool) -> dict[str, Any]:
    config: dict[str, Any] = json.loads(path.read_bytes())
    if smoke:
        config |= {"horizon": 10, "episodes_per_update": 2, "epochs": 2, "minibatch": 64,
                   "validate_every": 1000, "validation_episodes": 1}
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--algo", choices=("ippo", "mappo"), required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--steps", type=int, default=300_000, help="environment steps, total")
    parser.add_argument("--seed", type=int, default=1, help="learner seed, not a scenario seed")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--deadline", help="ISO 8601 time to stop before")
    parser.add_argument("--smoke", action="store_true", help="two short updates")
    parser.add_argument("--authorize-start", action="store_true",
                        help="owner authorizes Phase 12G training with the policy-lease design")
    args = parser.parse_args()
    if not args.smoke and not args.authorize_start:
        parser.error("training needs --authorize-start from the owner (or use --smoke)")
    if os.name == "nt" and args.run_dir.resolve().drive.upper() != "D:":
        parser.error("run directory must be on D:")
    config = load_config(args.config, args.smoke)
    deadline = (datetime.fromisoformat(args.deadline).astimezone().timestamp()
                if args.deadline else None)
    steps = 4 * config["horizon"] if args.smoke else args.steps
    print(f"[start] algo={args.algo} device={args.device} steps={steps} seed={args.seed} "
          f"smoke={args.smoke} precision=fp32", flush=True)
    train(args.algo, config, args.run_dir, steps=steps, seed=args.seed,
          device_name=args.device, resume=args.resume, deadline=deadline, smoke=args.smoke)


if __name__ == "__main__":
    main()
