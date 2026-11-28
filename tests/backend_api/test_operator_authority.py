"""Operator pause through the real API and mission loop (SQLite, development seed, no mocks)."""

import time
from typing import Any
from uuid import UUID

import pytest
from backend_support import Api, decision_status
from fastapi.testclient import TestClient

from backend.application import create_app
from backend.core.config import BackendSettings
from backend.core.permissions import GlobalRole

SEED = 12980


@pytest.fixture
def paced(slow_settings: BackendSettings) -> Any:
    with TestClient(create_app(slow_settings)) as client:
        api = Api(client, slow_settings)
        api.user("coord", GlobalRole.COORDINATOR)
        api.login("coord")
        api.user("viewer", GlobalRole.OBSERVER)
        api.login("viewer")
        yield api


def start(api: Api) -> tuple[str, Any, list[tuple[str, int, int]]]:
    """Start a long mission and record (mission state, tick, drones moved) for every tick."""
    mid: str = api.mission("coord", agents=6, seed=SEED, horizon=2000,
                           coordination="fixed_sector")["id"]
    assert api.post(f"/api/v1/missions/{mid}/start", "coord").status_code == 200
    runtime = api.client.app.state.container.runtime.get(UUID(mid))  # type: ignore[attr-defined]
    ctx, original = runtime.ctx, runtime.ctx.step
    trace: list[tuple[str, int, int]] = []

    def step() -> None:
        before = {a: d.position for a, d in ctx.engine.drones.items()}
        original()
        moved = sum(d.position != before[a] for a, d in ctx.engine.drones.items())
        trace.append((ctx.fleet.assignments.transitions[-1][1], ctx.engine.t, moved))

    ctx.step = step
    api.wait(lambda: any(moved for _, _, moved in trace))
    return mid, ctx, trace


def override(api: Api, mid: str, action: str, as_: str = "coord") -> Any:
    return api.post(f"/api/v1/missions/{mid}/override", as_,
                    {"action": action, "reason": "authority check"})


def accepted(api: Api, mid: str, response: Any) -> None:
    assert response.status_code == 202, response.text
    api.wait(lambda: decision_status(api, mid, "coord", response.json()["id"]) == "accepted")


def ticks(api: Api, trace: list[tuple[str, int, int]], count: int) -> None:
    target = len(trace) + count
    api.wait(lambda: len(trace) >= target)


def test_backend_override_pause_stops_movement_until_operator_resumes(paced: Api) -> None:
    mid, ctx, trace = start(paced)
    assert ctx.fleet.allow_external_policy is False
    assert override(paced, mid, "pause", as_="viewer").status_code in (403, 404)
    assert paced.post(f"/api/v1/missions/{mid}/pause", "viewer").status_code in (403, 404)

    accepted(paced, mid, override(paced, mid, "pause"))
    ticks(paced, trace, 15)
    # pausing and resuming execution is not an operator resume of the mission
    assert paced.post(f"/api/v1/missions/{mid}/pause", "coord").status_code == 200
    time.sleep(0.3)
    frozen = len(trace)
    time.sleep(0.3)
    assert len(trace) == frozen  # execution pause stops ticking
    assert paced.post(f"/api/v1/missions/{mid}/resume", "coord").status_code == 200
    ticks(paced, trace, 15)

    held = [moved for state, _, moved in trace if state == "paused"]
    assert len(held) >= 30 and sum(held) == 0
    first = next(i for i, row in enumerate(trace) if row[0] == "paused")
    assert all(state == "paused" for state, _, _ in trace[first:])

    assert override(paced, mid, "resume", as_="viewer").status_code in (403, 404)
    resumed_at = len(trace)
    accepted(paced, mid, override(paced, mid, "resume"))
    # movement returns only now, so the zero above was not an idle fleet
    paced.wait(lambda: any(s == "active" and moved for s, _, moved in trace[resumed_at:]))


def test_backend_mission_without_status_fails_closed(paced: Api) -> None:
    mid, ctx, trace = start(paced)
    paced.post(f"/api/v1/missions/{mid}/pause", "coord")
    time.sleep(0.3)
    with ctx.lock:
        assignments, ctx.fleet.assignments = ctx.fleet.assignments, None
    begin = len(trace)
    # assignments are absent, so record movement directly
    positions = {a: d.position for a, d in ctx.engine.drones.items()}
    ctx.step = type(ctx).step.__get__(ctx)
    for _ in range(10):
        ctx.step()
    assert {a: d.position for a, d in ctx.engine.drones.items()} == positions
    assert len(trace) == begin
    ctx.fleet.assignments = assignments  # control: the same fleet does move once restored
    for _ in range(20):
        ctx.step()
    assert {a: d.position for a, d in ctx.engine.drones.items()} != positions
