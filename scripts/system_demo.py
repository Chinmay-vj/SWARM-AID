"""Phase 9 connected demonstration against the running system (scripts/start_system.ps1).

    python scripts/system_demo.py                 # phase 1: missions, review, faults, exports
    python scripts/system_demo.py --verify PATH   # phase 2, after stop_system.ps1 + start_system.ps1

Uses the development accounts (admin, coordinator, operator, researcher, observer). The shared
password is read from SWARM_DEV_PASSWORD or the git-ignored runs/backend/dev-credentials.env and
is never printed. Every value in the report is measured from the live backend; workflows that
do not occur are reported as not observed rather than assumed. Synthetic simulation only.

Phase 1 leaves one long mission running on purpose so that the graceful shutdown performed by
stop_system.ps1 can be verified in phase 2 (status "stopped", reason "backend shutdown").
"""

import argparse
import json
import os
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
DASHBOARD = "http://127.0.0.1:5173"


def password() -> str:
    value = os.environ.get("SWARM_DEV_PASSWORD")
    if value:
        return value
    path = ROOT / "runs" / "backend" / "dev-credentials.env"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("SWARM_DEV_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("SWARM_DEV_PASSWORD not set and runs/backend/dev-credentials.env missing")


class Demo:
    def __init__(self) -> None:
        self.secret = password()
        self.steps: list[dict[str, Any]] = []
        self.clients: dict[str, httpx.Client] = {}
        self.user_ids: dict[str, str] = {}

    # ----- helpers ---------------------------------------------------------------------------
    def step(self, name: str, ok: bool, **result: Any) -> None:
        self.steps.append({"step": name, "ok": ok, **result})
        mark = "ok  " if ok else "FAIL"
        print(f"[{mark}] {len(self.steps):02d} {name}: {json.dumps(result, default=str)[:300]}")

    def client(self, user: str) -> httpx.Client:
        if user not in self.clients:
            c = httpx.Client(base_url=BASE, timeout=30)
            r = c.post("/api/v1/auth/login", json={"username": user, "password": self.secret})
            r.raise_for_status()
            c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
            self.user_ids[user] = c.get("/api/v1/auth/me").json()["user_id"]
            self.clients[user] = c
        return self.clients[user]

    def token(self, user: str) -> str:
        return str(self.client(user).headers["Authorization"]).removeprefix("Bearer ")

    @staticmethod
    def wait(predicate: Any, timeout: float = 120, interval: float = 0.2) -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(interval)
        return None

    def create(self, name: str, **config: Any) -> str:
        c = self.client("coordinator")
        r = c.post("/api/v1/missions", json={"name": name, "config": config})
        r.raise_for_status()
        mid: str = r.json()["id"]
        for user, role in (
            ("observer", "observer"),
            ("researcher", "researcher"),
            ("operator", "operator"),
        ):
            c.post(
                f"/api/v1/missions/{mid}/members",
                json={"user_id": self.user_ids.get(user) or self._uid(user), "role": role},
            )
        return mid

    def _uid(self, user: str) -> str:
        self.client(user)
        return self.user_ids[user]

    def events(self, mid: str, user: str = "coordinator") -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        after = 0
        while True:
            page = (
                self.client(user)
                .get(
                    f"/api/v1/missions/{mid}/events",
                    params={"after_sequence": after, "limit": 1000},
                )
                .json()
            )
            out += page
            if len(page) < 1000:
                return out
            after = page[-1]["sequence"]

    def status(self, mid: str) -> dict[str, Any]:
        return dict(self.client("coordinator").get(f"/api/v1/missions/{mid}").json())

    # ----- WebSocket -------------------------------------------------------------------------
    def stream(
        self,
        mid: str,
        user: str,
        stop: threading.Event,
        sink: list[dict[str, Any]],
        after: int | None = None,
    ) -> None:
        with connect(f"ws://127.0.0.1:8000/ws/v1/missions/{mid}") as ws:
            ws.send(json.dumps({"type": "auth", "token": self.token(user)}))
            if after is not None:
                ws.send(json.dumps({"type": "subscribe", "after_sequence": after}))
            while not stop.is_set():
                try:
                    sink.append(json.loads(ws.recv(timeout=0.5)))
                except TimeoutError:
                    continue
                except Exception:  # noqa: BLE001 - closed by server
                    return

    # ----- phase 1 ---------------------------------------------------------------------------
    def phase1(self) -> dict[str, Any]:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        live = httpx.get(f"{BASE}/health/live", timeout=5).status_code
        ready = httpx.get(f"{BASE}/health/ready", timeout=5).status_code
        self.step("backend_ready", live == 200 and ready == 200, live=live, ready=ready)
        dash = httpx.get(DASHBOARD, timeout=5).status_code
        self.step("dashboard_available", dash == 200, url=DASHBOARD, status=dash)
        health = self.client("admin").get("/api/v1/system/health").json()
        self.step(
            "database_ready",
            health["database"]["reachable"] and health["database"]["migration_revision"] == "0001",
            dialect=health["database"]["dialect"],
            revision=health["database"]["migration_revision"],
        )
        sims = health["simulations"]
        if sims["active"] >= sims["limit"]:
            raise SystemExit(
                f"{sims['active']} of {sims['limit']} simulation slots are busy (paused missions "
                "count). Run stop_system.ps1 and start_system.ps1, or stop those missions first."
            )
        me = self.client("coordinator").get("/api/v1/auth/me").json()
        self.step("authorized_login", me["global_role"] == "coordinator", role=me["global_role"])

        # Main mission: six-agent flood, seed 42, long enough for review.
        mid = self.create(
            f"Phase 9 demo flood {stamp}",
            scenario_id="flood_basic",
            agents=6,
            seed=42,
            horizon=5000,
        )
        m = self.status(mid)
        self.step(
            "mission_created",
            m["status"] == "draft",
            mission_id=mid,
            config={k: m["config"][k] for k in ("scenario_id", "agents", "seed")},
        )
        stop, frames = threading.Event(), []  # type: ignore[var-annotated]
        listener = threading.Thread(
            target=self.stream, args=(mid, "observer", stop, frames), daemon=True
        )
        listener.start()
        time.sleep(0.5)
        c = self.client("coordinator")
        r = c.post(f"/api/v1/missions/{mid}/start")
        self.step("simulation_started", r.status_code in (200, 202), http=r.status_code)
        dup = c.post(f"/api/v1/missions/{mid}/start")
        self.step(
            "duplicate_start_refused",
            dup.status_code == 409,
            code=dup.json().get("error", {}).get("code"),
        )

        agents = self.wait(
            lambda: (a := c.get(f"/api/v1/missions/{mid}/agents").json()) and len(a) == 6 and a
        )
        keys = sorted(a["agent_key"] for a in agents or [])
        self.step("independent_model1_agents", len(set(keys)) == 6, agents=keys)
        obs = self.wait(
            lambda: (
                (p := c.get(f"/api/v1/missions/{mid}/observations", params={"limit": 200}).json())[
                    "total"
                ]
                > 20
                and p
            )
        )
        items = obs["items"] if obs else []
        crs = Counter((o["location"] or {}).get("crs", "none") for o in items)
        self.step(
            "agent_observations",
            bool(items),
            total=obs["total"] if obs else 0,
            reporters=len({o["reporter"] for o in items}),
            crs=dict(crs),
            outcomes=dict(Counter(o["outcome"] for o in items)),
        )
        self.step(
            "reports_reach_model2",
            any(o["outcome"] == "admitted" for o in items),
            admitted=sum(o["outcome"] == "admitted" for o in items),
        )

        queue = self.wait(lambda: c.get(f"/api/v1/missions/{mid}/review-queue").json(), 90)
        c.post(f"/api/v1/missions/{mid}/pause", json={"reason": "phase 9 review"})
        paused = self.wait(lambda: self.status(mid)["status"] == "paused", 10)
        self.step("simulation_paused", bool(paused))
        tasks = c.get(f"/api/v1/missions/{mid}/tasks", params={"limit": 200}).json()
        sectors = c.get(f"/api/v1/missions/{mid}/sectors").json()
        events = self.events(mid)
        kinds = Counter(e["event_type"] for e in events)
        self.step(
            "cooperative_coordination",
            tasks["total"] > 0,
            tasks=tasks["total"],
            sectors=len(sectors),
            task_events=kinds.get("TASK_UPDATED", 0),
        )
        queue = c.get(f"/api/v1/missions/{mid}/review-queue").json() or queue or []
        if not queue:
            self.step("incident_and_recommendation", False, note="no recommendation produced")
            return self.finish(mid, stamp, stop, listener, frames, [])
        rec = queue[0]["recommendation"]
        incident = c.get(f"/api/v1/incidents/{rec['incident_id']}").json()
        group = c.get(f"/api/v1/incidents/{rec['incident_id']}/evidence").json()
        reporters = {o["reporter"] for o in group["observations"]}
        self.step(
            "evidence_fusion",
            len(group["observations"]) >= 1,
            observations=len(group["observations"]),
            independent_reporters=len(reporters),
        )
        self.step(
            "incident_assessment",
            True,
            category=incident["category"],
            disposition=incident["disposition"],
            priority=incident["priority_level"],
            supporting=incident["supporting_observations"],
            conflicting=incident["conflicting_observations"],
        )
        self.step(
            "structured_recommendation",
            True,
            request=rec["request"],
            version=rec["version"],
            unknowns=rec["unknowns"],
            expires_ms=rec["expires_ms"],
        )

        o = self.client("observer").post(
            f"/api/v1/recommendations/{rec['id']}/approve",
            json={"version": rec["version"], "reason": "x"},
        )
        self.step("unauthorized_decision_refused", o.status_code == 403, http=o.status_code)
        stale = c.post(
            f"/api/v1/recommendations/{rec['id']}/approve",
            json={"version": rec["version"] + 7, "reason": "stale check"},
        )
        self.step(
            "stale_version_refused",
            stale.status_code == 409,
            code=stale.json().get("error", {}).get("code"),
        )
        key = f"phase9-{uuid4().hex[:12]}"
        body = {
            "version": rec["version"],
            "reason": "phase 9 synthetic review",
            "idempotency_key": key,
        }
        first = c.post(f"/api/v1/recommendations/{rec['id']}/approve", json=body)
        again = c.post(f"/api/v1/recommendations/{rec['id']}/approve", json=body)
        decision = first.json()
        self.step(
            "human_review_submitted",
            first.status_code == 202,
            status=decision.get("status"),
            duplicate_same_decision=again.json().get("id") == decision.get("id"),
        )
        c.post(f"/api/v1/missions/{mid}/resume", json={"reason": "review submitted"})
        self.step(
            "simulation_resumed",
            bool(self.wait(lambda: self.status(mid)["status"] == "running", 10)),
        )

        def resolved() -> Any:
            items = c.get(f"/api/v1/missions/{mid}/human-decisions", params={"limit": 500}).json()[
                "items"
            ]
            d = next((d for d in items if d["id"] == decision["id"]), None)
            return d if d and d["status"] != "submitted" else None

        outcome = self.wait(resolved, 60)
        self.step(
            "persistent_human_decision",
            outcome is not None,
            status=outcome and outcome["status"],
            outcome_reason=outcome and outcome["outcome_reason"],
        )

        # Trace one observation of the reviewed incident.
        trace = c.get(f"/api/v1/observations/{group['observations'][0]['id']}/trace").json()
        self.step(
            "observation_trace",
            bool(trace.get("incidents")),
            incidents=len(trace["incidents"]),
            recommendations=len(trace["recommendations"]),
            decisions=len(trace["decisions"]),
            events=len(trace["events"]),
            evidence_origins=sorted({e["origin"] for e in trace["evidence"]}),
        )
        # Contradictory evidence: the simulation fixtures do not produce two different
        # findings for one cell at one instant, so two authenticated agent reports do (the
        # same path a deployed Model 1 would use). Model 2, not this script, flags the conflict.
        c.post(f"/api/v1/missions/{mid}/pause", json={"reason": "contradictory evidence check"})
        self.wait(lambda: self.status(mid)["status"] == "paused", 10)
        now = self.status(mid)["last_sim_ms"]
        bodies = []
        for agent, label in (("d0", "water"), ("d1", "fire")):
            cred = c.post(
                f"/api/v1/missions/{mid}/agent-credentials", json={"agent_key": agent}
            ).json()
            token = httpx.post(
                f"{BASE}/api/v1/auth/machine-token",
                json={"credential_id": cred["credential_id"], "secret": cred["secret"]},
            ).json()["access_token"]
            body = {
                "observation_id": str(uuid4()),
                "kind": "hazard",
                "label": label,
                "observed_ms": now,
                "confidence": 0.7,
                "cell": [11, 9],
                "evidence": [
                    {
                        "evidence_id": str(uuid4()),
                        "captured_ms": now,
                        "modality": "image",
                        "artifact_key": "synthetic/phase9-demo",
                    }
                ],
            }
            r = httpx.post(
                f"{BASE}/api/v1/missions/{mid}/observations",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            bodies.append((body, r.status_code, r.json().get("outcome")))
        hazards = c.get(
            f"/api/v1/missions/{mid}/observations", params={"limit": 500, "kind": "hazard"}
        ).json()["items"]
        second = next(
            (o for o in hazards if o["observation_id"] == bodies[1][0]["observation_id"]), None
        )
        roles = (
            [
                t["role"]
                for t in c.get(f"/api/v1/observations/{second['id']}/trace").json()["incidents"]
            ]
            if second
            else []
        )
        self.step(
            "contradictory_evidence",
            "conflicting" in roles,
            reports=[(b[1], b[2]) for b in bodies],
            second_report_roles=roles,
            note="injected through the authenticated agent-report API",
        )
        c.post(f"/api/v1/missions/{mid}/resume", json={"reason": "check complete"})

        return self.finish(mid, stamp, stop, listener, frames, [rec["id"]])

    def finish(
        self,
        mid: str,
        stamp: str,
        stop: threading.Event,
        listener: threading.Thread,
        frames: list[dict[str, Any]],
        recs: list[str],
    ) -> dict[str, Any]:
        c = self.client("coordinator")
        # WebSocket: drop and reconnect with the last sequence seen, then compare with REST.
        time.sleep(1.5)
        stop.set()
        listener.join(timeout=5)
        seen = [f["event"]["sequence"] for f in frames if f.get("type") == "event"]
        last = max(seen, default=0)
        time.sleep(1.5)  # events produced while disconnected
        stop2, frames2 = threading.Event(), []  # type: ignore[var-annotated]
        t2 = threading.Thread(
            target=self.stream, args=(mid, "observer", stop2, frames2, last), daemon=True
        )
        t2.start()
        time.sleep(2.5)
        stop2.set()
        t2.join(timeout=5)
        replay = [f["event"]["sequence"] for f in frames2 if f.get("type") == "event"]
        combined = sorted(set(seen) | set(replay))
        # Compare from the first event this client saw: earlier events predate the connection.
        rest = [
            e["sequence"]
            for e in self.events(mid)
            if min(combined, default=0) <= e["sequence"] <= max(combined, default=0)
        ]
        self.step(
            "websocket_reconnection",
            bool(replay) and combined == rest,
            before_disconnect=len(seen),
            last_sequence=last,
            replayed=len(replay),
            first_replayed=min(replay, default=None),
            gaps=sorted(set(rest) - set(combined))[:5],
            welcome=any(f.get("type") == "welcome" for f in frames2),
        )
        bad = httpx.Client(base_url=BASE).get(f"/api/v1/missions/{mid}")
        self.step("unauthenticated_read_refused", bad.status_code == 401, http=bad.status_code)

        # Communication degradation, Model 2 unavailability and recovery (scheduled outage).
        outage = self.create(
            f"Phase 9 demo outage {stamp}",
            scenario_id="flood_server_unavailable",
            agents=6,
            seed=42,
            outage_steps=[12, 13, 14, 15],
        )
        outage_start = c.post(f"/api/v1/missions/{outage}/start")
        if outage_start.status_code != 200:
            self.step(
                "outage_mission_started",
                False,
                http=outage_start.status_code,
                body=outage_start.json(),
            )
        done = self.wait(lambda: self.status(outage)["status"] in ("completed", "failed"), 120)
        kinds = [e["event_type"] for e in self.events(outage)]
        self.step(
            "communication_degradation",
            "COMMUNICATION_DEGRADED" in kinds,
            degraded=kinds.count("COMMUNICATION_DEGRADED"),
        )
        self.step(
            "communication_recovery",
            "COMMUNICATION_RESTORED" in kinds,
            restored=kinds.count("COMMUNICATION_RESTORED"),
        )
        ordered = (
            "MODEL_2_UNAVAILABLE" in kinds
            and "MODEL_2_RECOVERED" in kinds
            and kinds.index("MODEL_2_UNAVAILABLE") < kinds.index("MODEL_2_RECOVERED")
        )
        self.step(
            "model2_unavailability_handled",
            ordered,
            unavailable=kinds.count("MODEL_2_UNAVAILABLE"),
            recovered=kinds.count("MODEL_2_RECOVERED"),
            final_status=done and self.status(outage)["status"],
        )

        # Measured metrics and authorized research export.
        metrics = c.get(f"/api/v1/missions/{outage}/metrics").json()
        self.step(
            "measured_metrics",
            bool(metrics.get("runs")),
            keys=sorted(metrics["runs"][0]["operational_metrics"]) if metrics.get("runs") else [],
        )
        researcher = self.client("researcher")
        export = researcher.get(f"/api/v1/missions/{outage}/exports/research")
        refused = self.client("observer").get(f"/api/v1/missions/{outage}/exports/research")
        body = export.json() if export.status_code == 200 else {}
        self.step(
            "research_export",
            export.status_code == 200 and refused.status_code == 403,
            researcher=export.status_code,
            observer=refused.status_code,
            git_commit=(body.get("reproducibility", {}).get("runs") or [{}])[0].get("git_commit"),
        )

        # Stop the main mission and retrieve its persisted record.
        r = c.post(f"/api/v1/missions/{mid}/stop", json={"reason": "phase 9 demonstration"})
        final = self.wait(
            lambda: (s := self.status(mid))["status"] in ("stopped", "completed") and s, 30
        )
        summary = c.get(f"/api/v1/missions/{mid}/summary").json()
        history = c.get(f"/api/v1/missions/{mid}/history").json()
        self.step(
            "simulation_stopped",
            bool(final) and r.status_code in (200, 202),
            status=final and final["status"],
            history=[h["status"] for h in history],
        )
        run_metrics = c.get(f"/api/v1/missions/{mid}/metrics").json()["runs"][0]
        comm = run_metrics["operational_metrics"]["communication"]
        full = run_metrics["operational_metrics"].get("communication_full", {})
        self.step(
            "communication_flow",
            comm.get("delivered", 0) > 0,
            generated=comm.get("generated"),
            delivered=comm.get("delivered"),
            dropped=comm.get("dropped"),
            delivery_ratio=comm.get("delivery_ratio"),
            latency_p95_ms=full.get("p95_ms"),
            note="persisted run metrics; peer and command traffic share these router counters",
        )
        self.step(
            "persistent_record_retrieval",
            summary["observations"] > 0,
            observations=summary["observations"],
            incidents=summary["incidents_by_disposition"],
        )

        # Leave one mission running for the graceful-shutdown check in phase 2.
        running = self.create(
            f"Phase 9 demo shutdown {stamp}",
            scenario_id="flood_basic",
            agents=3,
            seed=43,
            horizon=5000,
        )
        c.post(f"/api/v1/missions/{running}/start")
        started = bool(self.wait(lambda: self.status(running)["status"] == "running", 10))
        # Paused so it cannot end on its own before stop_system.ps1 (drones run out of battery).
        c.post(f"/api/v1/missions/{running}/pause", json={"reason": "held for shutdown check"})
        held = bool(self.wait(lambda: self.status(running)["status"] == "paused", 10))
        self.step("mission_held_for_shutdown", started and held, mission_id=running)
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "missions": {"main": mid, "outage": outage, "shutdown": running},
            "summary_before_shutdown": summary,
            "steps": self.steps,
        }
        folder = ROOT / "runs" / "phase9" / "demo"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"demo-{stamp}.json"
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"report: {path}")
        print(f"{sum(s['ok'] for s in self.steps)}/{len(self.steps)} steps ok")
        print(
            "next: stop_system.ps1, start_system.ps1, then: "
            f"python scripts/system_demo.py --verify {path.relative_to(ROOT)}"
        )
        return report

    # ----- phase 2 ---------------------------------------------------------------------------
    def phase2(self, path: Path) -> dict[str, Any]:
        report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        c = self.client("coordinator")
        missions = report["missions"]
        shut = self.status(missions["shutdown"])
        history = c.get(f"/api/v1/missions/{missions['shutdown']}/history").json()
        reasons = [h["reason"] for h in history]
        self.step(
            "graceful_shutdown_recorded",
            shut["status"] == "stopped" and "backend shutdown" in reasons,
            status=shut["status"],
            reasons=reasons,
        )
        after = c.get(f"/api/v1/missions/{missions['main']}/summary").json()
        self.step(
            "records_survive_restart",
            after == report["summary_before_shutdown"],
            observations=after["observations"],
        )
        recovery = c.post(f"/api/v1/missions/{missions['main']}/model2/recovery").json()
        self.step(
            "model2_memory_recovery",
            bool(recovery.get("integrity_ok")),
            **{
                k: recovery.get(k)
                for k in ("restored", "integrity_ok", "matches_persisted_read_model")
            },
        )
        report["verification"] = self.steps
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"{sum(s['ok'] for s in self.steps)}/{len(self.steps)} verification steps ok")
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    demo = Demo()
    result = demo.phase2(args.verify) if args.verify else demo.phase1()
    raise SystemExit(0 if all(s["ok"] for s in demo.steps) else 1)
