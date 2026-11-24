"""Health and system metrics. Public probes expose minimal information."""

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.api.dependencies import ContainerDep, PrincipalDep
from backend.core.errors import Forbidden
from backend.monitoring import process_peak_memory_mb

public = APIRouter(tags=["health"])
router = APIRouter(tags=["system"])
HEAD_REVISION = "0001"


@public.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@public.get("/health/ready")
async def ready(services: ContainerDep) -> JSONResponse:
    db_ok = await asyncio.to_thread(services.db.ping)
    revision = await asyncio.to_thread(services.db.migration_revision) if db_ok else None
    migrations_ok = revision == HEAD_REVISION or not services.settings.require_migrations
    ok = db_ok and migrations_ok
    return JSONResponse({"status": "ready" if ok else "not_ready"}, status_code=200 if ok else 503)


def _detail(services: ContainerDep) -> dict[str, Any]:
    db_ok = services.db.ping()
    runtimes = {
        str(mid): {
            "ticks": rt.ticks,
            "sim_time_ms": rt.ctx.now_ms,
            "running": rt.running.is_set(),
            "finished": rt.ctx.finished,
            "model2_state": rt.ctx.command.state,
            "consecutive_db_failures": rt.db_failures,
            "last_error": rt.last_error,
        }
        for mid, rt in services.runtime.runtimes.items()
        if rt.task is not None and not rt.task.done()
    }
    degraded = (
        (not db_ok)
        or any(r["consecutive_db_failures"] for r in runtimes.values())
        or any(r["model2_state"] == "offline" for r in runtimes.values())
    )
    return {
        "status": "degraded" if degraded else "ok",
        "version": services.settings.version,
        "environment": services.settings.environment,
        "database": {
            "dialect": services.db.engine.dialect.name,
            "reachable": db_ok,
            "migration_revision": services.db.migration_revision() if db_ok else None,
            "expected_revision": HEAD_REVISION,
            "transaction_failures": services.db.transaction_failures,
        },
        "simulations": {
            "active": services.runtime.active_count(),
            "limit": services.settings.max_concurrent_simulations,
            "persistence_failures": services.runtime.persistence_failures,
            "missions": runtimes,
        },
        "websocket": {
            "connections": services.hub.count,
            "queued_frames": services.hub.queue_depth(),
            "dispatched_events": services.hub.dispatched,
            "slow_clients_dropped": services.hub.dropped_slow,
            "publish_failures": services.hub.publish_failures,
        },
        "authentication_failures": services.auth.failures,
        "process_peak_memory_mb": process_peak_memory_mb(),
    }


@router.get("/system/health")
async def system_health(principal: PrincipalDep, services: ContainerDep) -> dict[str, Any]:
    if not principal.is_admin:
        raise Forbidden("administrator role required")
    return await asyncio.to_thread(_detail, services)


@router.get("/system/metrics")
async def system_metrics(principal: PrincipalDep, services: ContainerDep) -> dict[str, Any]:
    if not principal.is_admin:
        raise Forbidden("administrator role required")
    latencies = sorted(services.hub.delivery_latency_ms)
    return {
        "api": services.metrics.snapshot(),
        "websocket_delivery_latency_ms": {
            "samples": len(latencies),
            "p50": latencies[len(latencies) // 2] if latencies else None,
            "p95": latencies[int(len(latencies) * 0.95)] if latencies else None,
        },
        "health": await asyncio.to_thread(_detail, services),
    }
