"""End-to-end synthetic backend demonstration against a real uvicorn process.

python scripts/backend_demo.py [--port 8765]

Creates a fresh SQLite database under runs/backend/demo-<timestamp>/, migrates it, creates
synthetic users, runs a six-agent flood mission with a scheduled command outage, exercises
human review through Model 2, restarts the server and verifies persistence. All reported
values are measured during the run and written to demo_results.json. Synthetic data only.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = secrets.token_urlsafe(18)


class Demo:
    def __init__(self, port: int) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.folder = ROOT / "runs" / "backend" / f"demo-{stamp}"
        self.folder.mkdir(parents=True)
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.env = os.environ | {
            "SWARM_JWT_SECRET": secrets.token_urlsafe(48),
            "SWARM_DATABASE_URL": f"sqlite:///{(self.folder / 'demo.db').as_posix()}",
            "SWARM_EVIDENCE_DIR": str(self.folder / "evidence"),
            "SWARM_SIMULATION_TICK_DELAY_MS": "150",
            "SWARM_WEBSOCKET_HEARTBEAT_SECONDS": "2",
            "SWARM_LOG_LEVEL": "WARNING",
            "SWARM_NEW_USER_PASSWORD": PASSWORD,
        }
        self.server: subprocess.Popen[bytes] | None = None
        self.steps: list[dict[str, Any]] = []
        self.ws_events: list[dict[str, Any]] = []
        self.ws_stop = threading.Event()

    # ----- infrastructure ------------------------------------------------------------------
    def run(self, *args: str) -> str:
        out = subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()

    def start_server(self) -> float:
        started = time.perf_counter()
        log = (self.folder / "server.log").open("ab")
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
            ],
            cwd=ROOT,
            env=self.env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        for _ in range(200):
            try:
                if httpx.get(f"{self.base}/health/ready", timeout=1).status_code == 200:
                    return time.perf_counter() - started
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise RuntimeError("server did not become ready")

    def kill_server(self) -> None:
        assert self.server is not None
        self.server.kill()  # abrupt: simulates a crash, no graceful shutdown
        self.server.wait(timeout=30)

    def step(self, name: str, **result: Any) -> None:
        entry = {"step": name, **result}
        self.steps.append(entry)
        print(f"[{len(self.steps):02d}] {name}: {json.dumps(result, default=str)}")

    # ----- API helpers ---------------------------------------------------------------------
    def login(self, client: httpx.Client, username: str) -> str:
        response = client.post(
            "/api/v1/auth/login", json={"username": username, "password": PASSWORD}
        )
        response.raise_for_status()
        token: str = response.json()["access_token"]
        return token

    def wait(self, predicate: Any, timeout: float = 120) -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.1)
        raise TimeoutError("condition not reached")

    def listen(self, mission_id: str, token: str) -> None:
        url = f"ws://127.0.0.1:{self.port}/ws/v1/missions/{mission_id}"
        with connect(url) as ws:
            ws.send(json.dumps({"type": "auth", "token": token}))
            while not self.ws_stop.is_set():
                try:
                    frame = json.loads(ws.recv(timeout=0.5))
                except TimeoutError:
                    continue
                except Exception:  # noqa: BLE001 - server killed at the end of phase one
                    return
                self.ws_events.append(frame)

    # ----- scenario ------------------------------------------------------------------------
    def main(self) -> dict[str, Any]:
        self.run("-m", "alembic", "upgrade", "head")
        self.step("migrate", current=self.run("-m", "alembic", "current").splitlines()[-1])
        for user, role in (("coordinator", "coordinator"), ("researcher", "researcher")):
            self.run("-m", "backend.cli", "create-user", "--username", user, "--role", role)
        self.step("users_created", users=["coordinator", "researcher"])
        self.step("server_started", ready_seconds=round(self.start_server(), 2))

        client = httpx.Client(base_url=self.base, timeout=30)
        token = self.login(client, "coordinator")
        client.headers["Authorization"] = f"Bearer {token}"
        self.step("coordinator_authenticated", me=client.get("/api/v1/auth/me").json()["subject"])

        mission = client.post(
            "/api/v1/missions",
            json={
                "name": "Synthetic flood demonstration",
                "config": {
                    "scenario_id": "flood_basic",
                    "agents": 6,
                    "seed": 12988,
                    "horizon": 60,
                    "outage_steps": [25, 26, 27, 28],
                },
            },
        ).json()
        mid = mission["id"]
        self.step("mission_created", mission_id=mid, status=mission["status"])
        listener = threading.Thread(target=self.listen, args=(mid, token), daemon=True)
        listener.start()
        time.sleep(0.5)
        client.post(f"/api/v1/missions/{mid}/start").raise_for_status()
        self.step("simulation_started", agents=6)

        queue = self.wait(lambda: client.get(f"/api/v1/missions/{mid}/review-queue").json())
        client.post(
            f"/api/v1/missions/{mid}/pause", json={"reason": "operator reviewing"}
        ).raise_for_status()
        queue = client.get(f"/api/v1/missions/{mid}/review-queue").json()
        item = queue[0]
        rec = item["recommendation"]
        summary = client.get(f"/api/v1/missions/{mid}/summary").json()
        self.step(
            "reports_processed",
            observations=summary["observations"],
            incidents=summary["incidents_by_disposition"],
            pending_recommendations=summary["pending_recommendations"],
        )
        incident = client.get(f"/api/v1/incidents/{rec['incident_id']}").json()
        group = client.get(f"/api/v1/incidents/{rec['incident_id']}/evidence").json()
        self.step(
            "incident_retrieved",
            category=incident["category"],
            priority=incident["priority_level"],
            location=incident["location"],
            evidence_observations=len(group["observations"]),
            recommendation_version=rec["version"],
        )
        decision = client.post(
            f"/api/v1/recommendations/{rec['id']}/approve",
            json={
                "version": rec["version"],
                "reason": "synthetic review approved",
                "idempotency_key": "demo-approve-1",
            },
        ).json()
        client.post(
            f"/api/v1/missions/{mid}/resume", json={"reason": "review submitted"}
        ).raise_for_status()

        def resolved(decision_id: str) -> Any:
            items = client.get(
                f"/api/v1/missions/{mid}/human-decisions", params={"limit": 500}
            ).json()["items"]
            found = next(d for d in items if d["id"] == decision_id)
            return found if found["status"] != "submitted" else None

        outcome = self.wait(lambda: resolved(decision["id"]))
        self.step("human_approval", status=outcome["status"], reason=outcome["outcome_reason"])

        def second_review() -> Any:
            for entry in client.get(f"/api/v1/missions/{mid}/review-queue").json():
                if entry["recommendation"]["id"] != rec["id"]:
                    return entry
            return None

        later = self.wait(second_review)
        client.post(
            f"/api/v1/missions/{mid}/pause", json={"reason": "second review"}
        ).raise_for_status()
        current = client.get(f"/api/v1/recommendations/{later['recommendation']['id']}").json()
        reject = client.post(
            f"/api/v1/recommendations/{current['id']}/reject",
            json={"version": current["version"], "reason": "synthetic evidence insufficient"},
        )
        client.post(
            f"/api/v1/missions/{mid}/resume", json={"reason": "review submitted"}
        ).raise_for_status()
        rejection = (
            self.wait(lambda: resolved(reject.json()["id"]))
            if reject.status_code == 202
            else reject.json()
        )
        self.step(
            "new_evidence_review",
            recommendation_version=current["version"],
            http_status=reject.status_code,
            outcome=rejection.get("status", rejection.get("error")),
        )

        final = self.wait(
            lambda: (
                (m := client.get(f"/api/v1/missions/{mid}").json())["status"]
                in ("completed", "failed")
                and m
            ),
            timeout=180,
        )
        self.step("mission_finished", status=final["status"], sim_time_ms=final["last_sim_ms"])
        events = client.get(f"/api/v1/missions/{mid}/events", params={"limit": 1000}).json()
        kinds = [e["event_type"] for e in events]
        self.step(
            "communication_interruption",
            model2_unavailable=kinds.count("MODEL_2_UNAVAILABLE"),
            model2_recovered=kinds.count("MODEL_2_RECOVERED"),
            communication_degraded=kinds.count("COMMUNICATION_DEGRADED"),
            communication_restored=kinds.count("COMMUNICATION_RESTORED"),
        )
        time.sleep(1)
        self.ws_stop.set()
        listener.join(timeout=5)
        ws_kinds = [f["event"]["event_type"] for f in self.ws_events if f.get("type") == "event"]
        self.step(
            "websocket_delivery",
            frames=len(self.ws_events),
            events=len(ws_kinds),
            rest_events=len(events),
            ordered=[f["event"]["sequence"] for f in self.ws_events if f.get("type") == "event"]
            == sorted(f["event"]["sequence"] for f in self.ws_events if f.get("type") == "event"),
            heartbeats=sum(f.get("type") == "heartbeat" for f in self.ws_events),
        )
        metrics = client.get(f"/api/v1/missions/{mid}/metrics").json()
        self.step(
            "mission_metrics",
            human_decisions=metrics["human_decisions"],
            counts=metrics["runs"][0]["operational_metrics"]["model2_counts"],
        )
        before = client.get(f"/api/v1/missions/{mid}/summary").json()
        client.close()

        self.kill_server()
        try:
            httpx.get(f"{self.base}/health/live", timeout=2)
            reachable = True
        except httpx.HTTPError:
            reachable = False
        assert not reachable, "old server still answering after kill"
        self.step(
            "server_killed",
            note="abrupt termination, no graceful shutdown",
            old_server_reachable=reachable,
        )
        self.step("server_restarted", ready_seconds=round(self.start_server(), 2))
        client = httpx.Client(base_url=self.base, timeout=30)
        client.headers["Authorization"] = f"Bearer {self.login(client, 'coordinator')}"
        after = client.get(f"/api/v1/missions/{mid}/summary").json()
        self.step(
            "persistence_after_restart",
            identical_summary=after == before,
            observations=after["observations"],
        )
        recovery = client.post(f"/api/v1/missions/{mid}/model2/recovery").json()
        self.step(
            "model2_recovery",
            **{
                k: recovery[k]
                for k in (
                    "restored",
                    "integrity_ok",
                    "matches_persisted_read_model",
                    "restored_incidents",
                )
            },
        )

        members = client.get("/api/v1/auth/me").json()
        researcher = httpx.Client(base_url=self.base, timeout=30)
        researcher_token = self.login(researcher, "researcher")
        researcher_id = httpx.get(
            f"{self.base}/api/v1/auth/me", headers={"Authorization": f"Bearer {researcher_token}"}
        ).json()["user_id"]
        client.post(
            f"/api/v1/missions/{mid}/members", json={"user_id": researcher_id, "role": "researcher"}
        ).raise_for_status()
        researcher.headers["Authorization"] = f"Bearer {researcher_token}"
        export = researcher.get(f"/api/v1/missions/{mid}/exports/research").json()
        (self.folder / "research_export.json").write_text(
            json.dumps(export, indent=2), encoding="utf-8"
        )
        csv_text = researcher.get(
            f"/api/v1/missions/{mid}/exports/operational", params={"format": "csv"}
        ).text
        (self.folder / "operational_export.csv").write_text(csv_text, encoding="utf-8")
        self.step(
            "research_export",
            reproducibility=export["reproducibility"]["git_commit"]
            if "git_commit" in export["reproducibility"]
            else export["reproducibility"]["runs"][0]["git_commit"],
            ground_truth_included=bool(export.get("evaluator_ground_truth")),
            csv_rows=csv_text.count("\n"),
        )
        audit = client.get(f"/api/v1/missions/{mid}/audit", params={"limit": 500}).json()
        actions: dict[str, int] = {}
        for entry in audit["items"]:
            actions[entry["action"]] = actions.get(entry["action"], 0) + 1
        self.step("audit_history", total=audit["total"], actions=actions, viewer=members["subject"])
        client.close()
        researcher.close()
        self.kill_server()
        results = {
            "generated_at": datetime.now(UTC).isoformat(),
            "mission_id": mid,
            "steps": self.steps,
        }
        (self.folder / "demo_results.json").write_text(
            json.dumps(results, indent=2, default=str), encoding="utf-8"
        )
        print(f"results: {self.folder / 'demo_results.json'}")
        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    demo = Demo(parser.parse_args().port)
    try:
        demo.main()
    finally:
        if demo.server is not None and demo.server.poll() is None:
            demo.server.kill()
