"""Bounded CPU benchmark of the Phase 7 backend against a real uvicorn process (no reload).

python -m evaluation.backend_benchmark [--agents 3 6 10 20] [--reports 40] [--port 8766]

For each fleet size: one running mission, one agent credential per drone, concurrent report
ingestion through Model 2 (plus duplicate resubmission), REST read latency and WebSocket
delivery latency. Also measures direct database write/read latency, concurrent WebSocket
connections, server memory and restart-to-ready recovery. Local results are not a statement
about production scalability.
"""

import argparse
import json
import os
import platform
import secrets
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = secrets.token_urlsafe(18)


def summarize(
    samples: list[float], errors: int = 0, seconds: float | None = None
) -> dict[str, Any]:
    values = sorted(samples)

    def pct(p: float) -> float | None:
        return round(values[min(len(values) - 1, int(p * len(values)))], 2) if values else None

    total = len(values) + errors
    return {
        "count": len(values),
        "errors": errors,
        "error_rate": round(errors / total, 4) if total else None,
        "mean_ms": round(statistics.fmean(values), 2) if values else None,
        "median_ms": round(statistics.median(values), 2) if values else None,
        "p95_ms": pct(0.95),
        "p99_ms": pct(0.99),
        "throughput_per_s": round(len(values) / seconds, 1) if seconds else None,
    }


class Bench:
    def __init__(self, port: int) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.folder = ROOT / "runs" / "backend" / f"benchmark-{stamp}"
        self.folder.mkdir(parents=True)
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.env = os.environ | {
            "SWARM_JWT_SECRET": secrets.token_urlsafe(48),
            "SWARM_DATABASE_URL": f"sqlite:///{(self.folder / 'bench.db').as_posix()}",
            "SWARM_EVIDENCE_DIR": str(self.folder / "evidence"),
            "SWARM_SIMULATION_TICK_DELAY_MS": "250",
            "SWARM_LOG_LEVEL": "WARNING",
            "SWARM_LOGIN_ATTEMPTS_PER_MINUTE": "1000",
            "SWARM_MAX_CONCURRENT_SIMULATIONS": "1",
            "SWARM_WEBSOCKET_MAX_CONNECTIONS": "200",
            "SWARM_NEW_USER_PASSWORD": PASSWORD,
        }
        self.server: subprocess.Popen[bytes] | None = None

    def run(self, *args: str) -> None:
        subprocess.run(
            [sys.executable, *args], cwd=ROOT, env=self.env, capture_output=True, check=True
        )

    def start(self) -> float:
        started = time.perf_counter()
        self.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=self.env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(300):
            try:
                if httpx.get(f"{self.base}/health/ready", timeout=1).status_code == 200:
                    return time.perf_counter() - started
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        raise RuntimeError("server not ready")

    def stop(self) -> None:
        if self.server is not None:
            self.server.kill()
            self.server.wait(timeout=30)

    def token(self, http: httpx.Client | None = None) -> str:
        poster = http.post if http is not None else httpx.post
        response = poster(
            f"{self.base}/api/v1/auth/login", json={"username": "bench", "password": PASSWORD}
        )
        response.raise_for_status()
        value: str = response.json()["access_token"]
        return value

    def fleet(self, client: httpx.Client, agents: int, reports: int) -> dict[str, Any]:
        mission = client.post(
            "/api/v1/missions",
            json={
                "name": f"bench-{agents}",
                "config": {
                    "scenario_id": "flood_basic",
                    "agents": agents,
                    "seed": 42,
                    "horizon": 5000,
                    "coordination": "independent",
                },
            },
        ).json()
        mid = mission["id"]
        credentials = [
            client.post(
                f"/api/v1/missions/{mid}/agent-credentials", json={"agent_key": f"d{i}"}
            ).json()
            for i in range(agents)
        ]
        tokens = [
            httpx.post(
                f"{self.base}/api/v1/auth/machine-token",
                json={"credential_id": c["credential_id"], "secret": c["secret"]},
            ).json()["access_token"]
            for c in credentials
        ]
        # Persistent per-agent clients: creating an httpx client per request costs ~200 ms of
        # client-side setup on Windows and would be measured as server latency.
        agent_clients = [
            httpx.Client(base_url=self.base, timeout=30, headers={"Authorization": f"Bearer {tok}"})
            for tok in tokens
        ]
        ws_latency: list[float] = []
        ws_stop = threading.Event()

        def listen() -> None:
            with connect(f"ws://127.0.0.1:{self.port}/ws/v1/missions/{mid}") as ws:
                ws.send(
                    json.dumps(
                        {"type": "auth", "token": client.headers["Authorization"].split()[1]}
                    )
                )
                while not ws_stop.is_set():
                    try:
                        frame = json.loads(ws.recv(timeout=0.5))
                    except TimeoutError:
                        continue
                    if frame.get("type") == "event":
                        occurred = datetime.fromisoformat(frame["event"]["occurred_at"])
                        ws_latency.append((datetime.now(UTC) - occurred).total_seconds() * 1000)

        listener = threading.Thread(target=listen, daemon=True)
        listener.start()
        client.post(f"/api/v1/missions/{mid}/start").raise_for_status()
        time.sleep(1.0)
        sent: list[tuple[int, dict[str, Any]]] = []
        latencies: list[float] = []
        outcomes: dict[str, int] = {}
        error_codes: dict[str, int] = {}
        errors = 0
        lock = threading.Lock()

        def submit(index: int) -> None:
            nonlocal errors
            agent = index % agents
            now = client.get(f"/api/v1/missions/{mid}").json()["last_sim_ms"]
            body = {
                "observation_id": str(uuid4()),
                "kind": "possible_human" if index % 3 else "hazard",
                "label": None if index % 3 else "water",
                "observed_ms": now,
                "confidence": 0.5,
                "cell": [index % 12, (index // 12) % 10],
                "evidence": [
                    {
                        "evidence_id": str(uuid4()),
                        "captured_ms": now,
                        "modality": "thermal",
                        "artifact_key": "bench/synthetic",
                    }
                ],
            }
            started = time.perf_counter()
            response = agent_clients[agent].post(f"/api/v1/missions/{mid}/observations", json=body)
            elapsed = (time.perf_counter() - started) * 1000
            with lock:
                if response.status_code == 202:
                    latencies.append(elapsed)
                    outcome = response.json()["outcome"]
                    outcomes[outcome] = outcomes.get(outcome, 0) + 1
                    sent.append((agent, body))
                else:
                    errors += 1
                    try:
                        code = f"{response.status_code}:{response.json()['error']['code']}"
                    except (ValueError, KeyError):
                        code = str(response.status_code)
                    error_codes[code] = error_codes.get(code, 0) + 1

        total = agents * reports
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=min(agents, 16)) as pool:
            list(pool.map(submit, range(total)))
        ingest_seconds = time.perf_counter() - started

        duplicates: list[float] = []
        dup_ok = 0
        for agent, body in sent[: max(10, total // 10)]:
            started = time.perf_counter()
            response = agent_clients[agent].post(f"/api/v1/missions/{mid}/observations", json=body)
            duplicates.append((time.perf_counter() - started) * 1000)
            dup_ok += response.status_code == 202 and response.json()["duplicate"]

        reads: dict[str, list[float]] = {
            "summary": [],
            "incidents": [],
            "observations": [],
            "review_queue": [],
            "map": [],
        }
        paths = {
            "summary": f"/api/v1/missions/{mid}/summary",
            "incidents": f"/api/v1/missions/{mid}/incidents",
            "observations": f"/api/v1/missions/{mid}/observations",
            "review_queue": f"/api/v1/missions/{mid}/review-queue",
            "map": f"/api/v1/missions/{mid}/map",
        }
        for _ in range(40):
            for name, path in paths.items():
                started = time.perf_counter()
                ok = client.get(path).status_code == 200
                if ok:
                    reads[name].append((time.perf_counter() - started) * 1000)
        client.post(f"/api/v1/missions/{mid}/stop", json={"reason": "benchmark complete"})
        for agent_client in agent_clients:
            agent_client.close()
        ws_stop.set()
        listener.join(timeout=5)
        return {
            "agents": agents,
            "reports_submitted": total,
            "ingestion": summarize(latencies, errors, ingest_seconds)
            | {"outcomes": outcomes, "error_codes": error_codes},
            "duplicate_resubmission": summarize(duplicates) | {"recognized_duplicates": dup_ok},
            "reads": {name: summarize(values) for name, values in reads.items()},
            "websocket_delivery": summarize(ws_latency),
        }

    def connections(self, client: httpx.Client, count: int) -> dict[str, Any]:
        mission = client.post(
            "/api/v1/missions",
            json={"name": "ws-bench", "config": {"scenario_id": "flood_basic", "agents": 3}},
        ).json()
        token = client.headers["Authorization"].split()[1]
        latencies: list[float] = []
        failures = 0
        sockets = []
        for _ in range(count):
            started = time.perf_counter()
            try:
                ws = connect(f"ws://127.0.0.1:{self.port}/ws/v1/missions/{mission['id']}")
                ws.send(json.dumps({"type": "auth", "token": token}))
                assert json.loads(ws.recv(timeout=5))["type"] == "welcome"
                latencies.append((time.perf_counter() - started) * 1000)
                sockets.append(ws)
            except Exception:  # noqa: BLE001
                failures += 1
        for ws in sockets:
            ws.close()
        return {"requested": count, "authenticated_connect": summarize(latencies, failures)}

    def database(self) -> dict[str, Any]:
        from backend.core.config import BackendSettings
        from backend.database.models import AuditLog
        from backend.database.session import Database, build_engine

        settings = BackendSettings(
            _env_file=None, jwt_secret="x" * 40, database_url=self.env["SWARM_DATABASE_URL"]
        )
        db = Database(build_engine(settings))
        writes, reads = [], []
        ids = []
        for i in range(300):
            started = time.perf_counter()
            with db.transaction() as session:
                row = AuditLog(
                    actor="bench",
                    actor_type="service",
                    action="bench.write",
                    resource_type="bench",
                    request_id=str(i),
                    outcome="success",
                )
                session.add(row)
                session.flush()
                ids.append(row.id)
            writes.append((time.perf_counter() - started) * 1000)
        for row_id in ids:
            started = time.perf_counter()
            with db.read() as session:
                session.get(AuditLog, row_id)
            reads.append((time.perf_counter() - started) * 1000)
        db.dispose()
        return {"single_row_commit": summarize(writes), "primary_key_read": summarize(reads)}

    def main(self, sizes: list[int], reports: int) -> dict[str, Any]:
        self.run("-m", "alembic", "upgrade", "head")
        self.run("-m", "backend.cli", "create-user", "--username", "bench", "--role", "coordinator")
        self.run(
            "-m",
            "backend.cli",
            "create-user",
            "--username",
            "benchadmin",
            "--role",
            "administrator",
        )
        cold_start = self.start()
        assert self.server is not None
        client = httpx.Client(base_url=self.base, timeout=60)
        client.headers["Authorization"] = f"Bearer {self.token()}"
        logins: list[float] = []
        login_client = httpx.Client(timeout=30)
        for _ in range(20):
            started = time.perf_counter()
            self.token(login_client)
            logins.append((time.perf_counter() - started) * 1000)
        fleets = [self.fleet(client, size, reports) for size in sizes]
        conns = self.connections(client, 50)
        admin = httpx.post(
            f"{self.base}/api/v1/auth/login", json={"username": "benchadmin", "password": PASSWORD}
        ).json()["access_token"]
        health = httpx.get(
            f"{self.base}/api/v1/system/health", headers={"Authorization": f"Bearer {admin}"}
        ).json()
        memory = health["process_peak_memory_mb"]  # reported by the server process itself
        client.close()
        self.stop()
        restart = self.start()
        self.stop()
        result = {
            "generated_at": datetime.now(UTC).isoformat(),
            "environment": {
                "platform": platform.platform(),
                "processor": platform.processor(),
                "logical_cpus": os.cpu_count(),
                "python": platform.python_version(),
                "database": "SQLite (WAL, synchronous=NORMAL) on local disk",
                "server": "single uvicorn worker, no reload",
            },
            "server_cold_start_seconds": round(cold_start, 2),
            "restart_to_ready_seconds": round(restart, 2),
            "server_peak_working_set_mb": memory,
            "login_argon2id": summarize(logins),
            "fleets": fleets,
            "websocket_connections": conns,
            "database": self.database(),
        }
        (self.folder / "benchmark_results.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, indent=2))
        print(f"results: {self.folder / 'benchmark_results.json'}")
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", type=int, nargs="+", default=[3, 6, 10, 20])
    parser.add_argument("--reports", type=int, default=40, help="reports per agent")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    bench = Bench(args.port)
    try:
        bench.main(args.agents, args.reports)
    finally:
        bench.stop()
