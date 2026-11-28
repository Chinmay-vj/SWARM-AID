"""Phase 13 cluster 2: backend persistence measurements on disposable SQLite databases.

    python -u -m evaluation.phase13_cluster2 compare     (before/after, alternating order)

Drives the real RuntimeManager tick in one thread (no mission task, no network), so every
statement and serialization belongs to persistence. Development seed 12990 only. "before"
loads the persistence adapter saved before cluster 2 changes.
"""

import argparse
import cProfile
import importlib.util
import json
import os
import pstats
import re
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any
from uuid import UUID, uuid4

from evaluation import phase13a_profile as profile
from evaluation.process_memory import peak_rss_mib

ROOT = profile.DATA / "runs/phase13/cluster2"
TMP = profile.DATA / "tmp/phase13c2"
BEFORE = ROOT / "before/model2_adapter.py"
SEED, AGENTS, TICKS, ROUNDS = 12990, 6, 60, 3
ADAPTER = "backend.integrations.model2_adapter"


def use(implementation: str) -> None:
    """Install the saved adapter before anything imports the current one."""
    if implementation != "before":
        return
    if ADAPTER in sys.modules:
        raise RuntimeError("the current adapter is already imported")
    import backend.integrations

    spec = importlib.util.spec_from_file_location(ADAPTER, BEFORE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[ADAPTER] = module
    spec.loader.exec_module(module)
    backend.integrations.model2_adapter = module


def stats(values: list[float]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    return {"samples": len(values), "mean_ms": mean(values), "median_ms": median(values),
            "p95_ms": ordered[max(0, int(0.95 * len(ordered) + 0.999) - 1)],
            "sd_ms": stdev(values) if len(values) > 1 else 0.0, "max_ms": ordered[-1]}


def canonical(database: Path) -> dict[str, list[str]]:
    """Every row, with run-specific identifiers and wall-clock stamps replaced consistently."""
    seen: dict[str, str] = {}
    identifier = re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\b[0-9a-f]{32}\b")
    stamp = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)?")

    def clean(value: Any) -> str:
        text = stamp.sub("<time>", str(value))
        return identifier.sub(lambda g: seen.setdefault(g.group(), f"<id{len(seen)}>"), text)

    connection = sqlite3.connect(database)
    out = {}
    for (name,) in connection.execute(
            "select name from sqlite_master where type='table' order by name").fetchall():
        if name in ("users", "refresh_tokens", "audit_records", "alembic_version"):
            continue
        out[name] = [clean("|".join(map(str, row)))
                     for row in connection.execute(f'select * from "{name}" order by rowid')]
    connection.close()
    return out


def storage(database: Path) -> dict[str, Any]:
    files = {s or "database": Path(f"{database}{s}").stat().st_size
             for s in ("", "-wal", "-shm") if Path(f"{database}{s}").exists()}
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    logical = {}
    for (name,) in connection.execute("select name from sqlite_master where type='table'"):
        columns = [r[1] for r in connection.execute(f'pragma table_info("{name}")')]
        total = "+".join(f'coalesce(length(cast("{c}" as blob)),0)' for c in columns)
        logical[name] = connection.execute(
            f'select coalesce(sum({total}),0) from "{name}"').fetchone()[0]
    snapshots = {
        kind: {"rows": rows, "payload_bytes": size, "largest_bytes": largest}
        for kind, rows, size, largest in connection.execute(
            "select kind, count(*), sum(length(cast(payload as blob))), "
            "max(length(cast(payload as blob))) from mission_snapshots group by kind")}
    connection.close()
    return {"files_before_checkpoint": files, "database_after_checkpoint": database.stat().st_size,
            "logical_bytes": logical, "snapshots": snapshots}


def mission(implementation: str, every: int, instrument: bool, label: str) -> dict[str, Any]:
    use(implementation)
    profile.guard_engine()
    sys.path.insert(0, str(profile.REPO / "tests"))
    from backend_support import Api, make_settings, migrate
    from fastapi.testclient import TestClient
    from sqlalchemy import event

    from backend.application import create_app
    from backend.core.permissions import GlobalRole

    TMP.mkdir(parents=True, exist_ok=True)
    database = TMP / f"{label}-{uuid4().hex}.db"
    migrate(f"sqlite:///{database.as_posix()}")
    settings = make_settings(database, TMP, snapshot_every_ticks=every)
    statements: Counter[str] = Counter()
    clock = {"execute": 0.0}
    persist: list[float] = []
    steps: list[float] = []
    checkpoint_ticks: list[float] = []
    parts: dict[str, float] = {}
    with TestClient(create_app(settings)) as client:
        api = Api(client, settings)
        api.user("coord", GlobalRole.COORDINATOR)
        api.login("coord")
        created = api.mission("coord", agents=AGENTS, seed=profile.require_profiling_seed(SEED),
                              horizon=TICKS)
        manager: Any = client.app.state.container.runtime  # type: ignore[attr-defined]
        runtime = manager._prepare(UUID(created["id"]), "coord")
        engine = manager.db.sessions.kw["bind"]
        if instrument:
            started: list[float] = []

            @event.listens_for(engine, "before_cursor_execute")
            def before(*args: Any) -> None:
                started.append(time.perf_counter())

            @event.listens_for(engine, "after_cursor_execute")
            def after(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
                clock["execute"] += (time.perf_counter() - started.pop()) * 1000
                words = statement.split()
                verb = words[0].upper()
                if verb == "SELECT":
                    table = words[words.index("FROM") + 1] if "FROM" in words else "?"
                else:
                    table = words[2] if verb in ("INSERT", "DELETE") else words[1]
                statements[f"{verb} {table}"] += 1

            command = runtime.ctx.command
            adapter = sys.modules[ADAPTER]

            def timed(owner: Any, name: str, key: str) -> None:
                original = getattr(owner, name)

                def call(*args: Any, **kwargs: Any) -> Any:
                    begin = time.perf_counter()
                    result = original(*args, **kwargs)
                    parts[key] = parts.get(key, 0.0) + (time.perf_counter() - begin) * 1000
                    return result

                setattr(owner, name, call)

            timed(command, "snapshot", "read_model_build")
            timed(command, "checkpoint", "checkpoint_build")
            timed(adapter, "digest", "digest")
        process = cProfile.Profile() if instrument else None
        count = 0
        while not runtime.ctx.finished:
            begin = time.perf_counter()
            runtime.ctx.step()
            steps.append((time.perf_counter() - begin) * 1000)
            runtime.ticks += 1
            count += 1
            full = runtime.ticks % every == 0
            if process:
                process.enable()
            begin = time.perf_counter()
            ok = manager.persist(runtime, checkpoint=full)
            elapsed = (time.perf_counter() - begin) * 1000
            if process:
                process.disable()
            if ok is False:
                raise RuntimeError(f"persistence failed: {runtime.last_error}")
            persist.append(elapsed)
            if full:
                checkpoint_ticks.append(elapsed)
        shot = storage(database)
        rows = canonical(database)
        verified = verify(database)
    result: dict[str, Any] = {
        "implementation": implementation, "snapshot_every_ticks": every, "ticks": count,
        "persist": stats(persist), "checkpoint_tick": stats(checkpoint_ticks),
        "step": stats(steps), "persist_total_ms": sum(persist), "storage": shot,
        "snapshot_digests_verified": verified, "peak_rss_MiB": peak_rss_mib(),
    }
    if instrument:
        profiled: Any = pstats.Stats(process)
        table: Any = profiled.stats
        total = float(sum(v[2] for v in table.values()))

        def share(fragment: str) -> float:
            return float(sum(v[2] for k, v in table.items()
                             if fragment in k[0].replace("\\", "/"))) / total

        result["instrumented"] = {
            "statements": dict(statements.most_common()),
            "statements_per_tick": sum(statements.values()) / count,
            "cursor_execute_ms_total": clock["execute"], "builders_ms_total": dict(parts),
            "own_time_share": {"sqlalchemy": share("/sqlalchemy/"), "json": share("/json/"),
                               "pydantic": share("/pydantic"),
                               "backend": share("/SWARM-AID/backend/")},
            "profiled_seconds": total,
            "top": [{"function": f"{Path(k[0]).name}:{k[1]}:{k[2]}", "share": v[2] / total,
                     "calls": v[1]}
                    for k, v in sorted(table.items(), key=lambda kv: -kv[1][2])[:14]],
        }
    (TMP / f"{label}.rows.json").write_text(json.dumps(rows), encoding="utf8")
    return result


def verify(database: Path) -> dict[str, int]:
    """Round trip: every stored snapshot still matches its digest through the backend's check."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from backend.database import models as m
    from backend.integrations.runtime import verify_snapshot

    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with Session(engine) as session:
        rows = session.scalars(select(m.MissionSnapshot)).all()
        good = sum(verify_snapshot(row) for row in rows)
    engine.dispose()
    return {"snapshots": len(rows), "verified": good}


def child(implementation: str, every: int, instrument: bool, label: str) -> dict[str, Any]:
    done = subprocess.run(
        [sys.executable, "-m", "evaluation.phase13_cluster2", "mission", "--impl",
         implementation, "--every", str(every), "--label", label,
         *(["--instrument"] if instrument else [])],
        capture_output=True, text=True, check=False, cwd=profile.REPO)
    if done.returncode:
        raise RuntimeError(done.stderr[-2000:])
    result: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return result


def compare() -> None:
    (ROOT / "13d").mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    runs, equivalence = [], {}
    for every in (10, 5):  # 10 is the default; 5 is the Phase 13A fixture
        for round_ in range(ROUNDS):
            order = ("before", "after") if round_ % 2 == 0 else ("after", "before")
            for implementation in order:
                label = f"{implementation}-{every}-{round_}"
                runs.append(child(implementation, every, False, label) | {"round": round_})
                print(f"[compare] every={every} round={round_ + 1}/{ROUNDS} {implementation} "
                      f"persist_median={runs[-1]['persist']['median_ms']:.1f}ms "
                      f"p95={runs[-1]['persist']['p95_ms']:.1f} "
                      f"rss={runs[-1]['peak_rss_MiB']:.0f}MiB "
                      f"elapsed={time.perf_counter() - started:.0f}s", flush=True)
        old, new = (json.loads((TMP / f"{i}-{every}-0.rows.json").read_bytes())
                    for i in ("before", "after"))
        equivalence[str(every)] = {
            "tables": {k: len(v) for k, v in old.items() if v},
            "differing_tables": sorted(k for k in old.keys() | new.keys()
                                       if old.get(k) != new.get(k))}
        print(f"[compare] every={every} differing_tables="
              f"{equivalence[str(every)]['differing_tables']}", flush=True)
    (ROOT / "13d/runs.json").write_text(json.dumps(runs, indent=1), "utf8")
    (ROOT / "13d/persistence_equivalence.json").write_text(json.dumps(equivalence, indent=2),
                                                           "utf8")
    instrumented = [child(i, 10, True, f"{i}-instrumented") for i in ("before", "after")]
    (ROOT / "13d/database_query_measurements.json").write_text(json.dumps({
        "note": "single thread; instrumented timings are inflated, use counts and shares",
        "runs": instrumented}, indent=2), "utf8")
    for r in instrumented:
        i = r["instrumented"]
        print(f"[queries] {r['implementation']} statements_per_tick="
              f"{i['statements_per_tick']:.1f} shares={i['own_time_share']}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("compare", "mission"))
    parser.add_argument("--impl", choices=("before", "after"), default="after")
    parser.add_argument("--every", type=int, default=10)
    parser.add_argument("--label", default="manual")
    parser.add_argument("--instrument", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    if args.command == "compare":
        compare()
    else:
        print(json.dumps(mission(args.impl, args.every, args.instrument, args.label)))


if __name__ == "__main__":
    main()
