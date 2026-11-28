"""Skipping unchanged tasks keeps rows exact, including after a failed and retried tick."""

from typing import Any
from uuid import UUID

import pytest
from backend_support import Api
from sqlalchemy import select

from backend.database import models as m

SEED = 12981


def assert_tasks_match(manager: Any, runtime: Any) -> int:
    fixture = runtime.ctx.fleet.assignments
    with manager.db.read() as session:
        rows = {r.model2_id: r for r in session.scalars(
            select(m.Task).where(m.Task.mission_id == runtime.mission_id))}
        events = list(session.scalars(
            select(m.TaskEvent).where(m.TaskEvent.mission_id == runtime.mission_id)))
        assert rows.keys() == {t.task_id for t in fixture.tasks.values()}
        for task in fixture.tasks.values():
            row, last = rows[task.task_id], task.history[-1]
            assert (row.coordinator_state, row.updated_ms) == (last.state, last.time_ms)
            ordinals = sorted(e.ordinal for e in events if e.task_id == row.id)
            assert ordinals == list(range(len(task.history)))
        return len(rows)


@pytest.mark.parametrize("fail_every", [0, 3])
def test_task_rows_stay_exact_across_rollbacks(
    api: Api, coordinator: str, monkeypatch: pytest.MonkeyPatch, fail_every: int
) -> None:
    created = api.mission(coordinator, agents=3, seed=SEED, horizon=40)
    manager: Any = api.client.app.state.container.runtime  # type: ignore[attr-defined]
    runtime = manager._prepare(UUID(created["id"]), coordinator)
    original = runtime.sync._sync_runtime
    calls = 0

    def flaky(session: Any) -> None:
        nonlocal calls
        calls += 1
        original(session)
        if fail_every and calls % fail_every == 0:
            raise RuntimeError("injected failure after task rows were written")

    monkeypatch.setattr(runtime.sync, "_sync_runtime", flaky)
    failures = 0
    while not runtime.ctx.finished:
        runtime.ctx.step()
        if not manager.persist(runtime):
            failures += 1
            assert manager.persist(runtime)  # the retry repeats the rolled-back work
        assert_tasks_match(manager, runtime)
    assert assert_tasks_match(manager, runtime) > 3
    assert (failures > 0) is bool(fail_every)


def test_dashboard_read_endpoints_answer_and_stay_scoped(api: Api, coordinator: str) -> None:
    for probe in ("/health/live", "/health/ready"):
        assert api.client.get(probe).status_code == 200
    mid = api.mission(coordinator, agents=3, seed=SEED, horizon=20)["id"]
    assert api.post(f"/api/v1/missions/{mid}/start", coordinator).status_code == 200
    api.wait_status(mid, coordinator, {"completed", "failed"})
    paths = ["", "/summary", "/history", "/metrics", "/events", "/agents", "/observations",
             "/incidents", "/recommendations", "/review-queue", "/alerts", "/human-decisions",
             "/tasks", "/snapshots"]
    api.user("outsider")
    api.login("outsider")
    for path in paths:
        url = f"/api/v1/missions/{mid}{path}"
        assert api.get(url, coordinator).status_code == 200, path
        assert api.get(url, "outsider").status_code in (403, 404), path
        assert api.get(url, None).status_code == 401, path
