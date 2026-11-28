"""python -m orchestration {check,run,matrix,experiment,serve,status}

check       validate configuration for an execution profile (exit 1 on any error)
run         headless integrated mission (simulator, Model 1, transport, coordination, Model 2)
matrix      Phase 9 integration matrix (configs/experiments/phase9_*.json)
experiment  dispatch to the Phase 5 coordination or Phase 6 command research runners
serve       owned backend process with graceful file-signalled shutdown (start/stop scripts)
status      read-only health, database and mission status
"""

import argparse
import json
import sys
from pathlib import Path
from typing import get_args


def _check(args: argparse.Namespace) -> int:
    from orchestration.checks import run_checks

    results = run_checks(args.profile)
    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2))
    else:
        marks = {"ok": "ok  ", "warning": "warn", "error": "FAIL", "skipped": "skip"}
        for r in results:
            print(f"[{marks[r.status]}] {r.name}: {r.detail}")
    errors = sum(r.status == "error" for r in results)
    warnings = sum(r.status == "warning" for r in results)
    print(f"{len(results)} checks, {errors} errors, {warnings} warnings ({args.profile} profile)")
    return 1 if errors else 0


def _run(args: argparse.Namespace) -> int:
    from pydantic import ValidationError

    from backend.integrations.simulation_adapter import MissionConfig
    from orchestration.headless import run_mission
    from orchestration.manifest import manifest

    try:
        config = MissionConfig(
            scenario_id=args.scenario,
            agents=args.agents,
            seed=args.seed,
            horizon=args.horizon,
            coordination=args.coordination,
            command_mode=args.command_mode,
        )
        config.validated()
    except (ValidationError, ValueError) as exc:
        print(f"configuration rejected: {exc}", file=sys.stderr)
        return 2
    result = run_mission(config, measure_memory=args.memory)
    record = {"manifest": manifest("phase9-headless", config.model_dump(mode="json"))} | result
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        path = args.output / f"headless-{config.scenario_id}-{config.agents}-{config.seed}.json"
        path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        print(path)
    op = result["operational"]
    print(
        json.dumps(
            {
                "end_reason": result["end_reason"],
                "sim_time_ms": result["sim_time_ms"],
                "model2_incidents": op["model2_incidents"],
                "model2_admitted_findings": op["model2_admitted_findings"],
                "delivery_ratio": op["communication"].get("delivery_ratio"),
                "step_ms": result["performance"]["step_ms"],
                "fingerprint": result["fingerprint"],
            },
            indent=2,
        )
    )
    return 0


def _matrix(args: argparse.Namespace) -> int:
    from orchestration.matrix import MatrixPlan, run_matrix

    plan = MatrixPlan.model_validate_json(args.config.read_bytes())
    folder = run_matrix(plan, args.output)
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    print(folder)
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "plan",
                    "runs",
                    "status_counts",
                    "determinism_checks",
                    "determinism_identical",
                )
            },
            indent=2,
        )
    )
    return 0 if summary["status_counts"].get("failed", 0) == 0 else 1


def _experiment(args: argparse.Namespace) -> int:
    if args.family == "coordination":
        from evaluation import experiment_runner as runner
    else:
        from evaluation import command_agent_experiments as runner  # type: ignore[no-redef]
    plan = runner.Experiment.model_validate_json(args.config.read_bytes())
    print(runner.run(plan, args.output))
    return 0


def _status(args: argparse.Namespace) -> int:
    from orchestration.status import system_status

    status = system_status()
    print(json.dumps(status, indent=2))
    return 0 if status["backend"]["live"].get("reachable") else 3


def main(argv: list[str] | None = None) -> int:
    from simulation.adapters.coordination import PolicyName

    parser = argparse.ArgumentParser(prog="python -m orchestration")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="validate configuration")
    check.add_argument(
        "--profile",
        choices=["development", "connected", "headless", "research", "testing"],
        default="development",
    )
    check.add_argument("--json", action="store_true")

    run = commands.add_parser("run", help="headless integrated mission")
    run.add_argument("--scenario", default="flood_basic")
    run.add_argument("--agents", type=int, default=6)
    run.add_argument("--seed", type=int, required=True, help="development seeds: 12000-12999")
    run.add_argument("--horizon", type=int)
    run.add_argument("--coordination", choices=get_args(PolicyName), default="shared_information")
    run.add_argument("--command-mode", choices=["direct", "rules", "fusion"], default="fusion")
    run.add_argument("--output", type=Path)
    run.add_argument("--memory", action="store_true", help="trace Python peak memory (slower)")

    matrix = commands.add_parser("matrix", help="Phase 9 integration matrix")
    matrix.add_argument(
        "--config", type=Path, default=Path("configs/experiments/phase9_smoke.json")
    )
    matrix.add_argument("--output", type=Path, default=Path("runs/phase9"))

    experiment = commands.add_parser("experiment", help="Phase 5/6 research runners")
    experiment.add_argument("--family", choices=["coordination", "command"], required=True)
    experiment.add_argument("--config", type=Path, required=True)
    experiment.add_argument("--output", type=Path, default=Path("runs/experiments"))

    serve_parser = commands.add_parser("serve", help="owned backend (used by start_system.ps1)")
    serve_parser.add_argument("--log", type=Path, help="write server output to this file")
    commands.add_parser("status", help="read-only system status")

    args = parser.parse_args(argv)
    if args.command == "serve":
        from orchestration.serve import serve

        return serve(log=args.log)
    handler = {
        "check": _check,
        "run": _run,
        "matrix": _matrix,
        "experiment": _experiment,
        "status": _status,
    }[args.command]
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
