/**
 * Data freshness classification.
 *
 * Simulation-time freshness uses the backend's window (FRESHNESS_MS = 1500 ms in
 * backend/services/queries.py, matching Model 2's default). When the backend already marks a
 * record stale, that flag wins. Wall-clock staleness (no updates received by the browser) uses
 * a provisional client threshold documented in docs/frontend/DATA_CONTRACTS.md.
 */
export const BACKEND_FRESHNESS_MS = 1500;
/** Provisional: a connected view with no server update for this long is marked stale. */
export const CLIENT_STALE_AFTER_MS = 20_000;

export type Freshness = "fresh" | "stale" | "unknown" | "missing";

export function classifySimAge(
  reportedMs: number | null | undefined,
  nowMs: number | null | undefined,
  backendStale?: boolean | null,
  windowMs = BACKEND_FRESHNESS_MS,
): Freshness {
  if (reportedMs === null || reportedMs === undefined) return "missing";
  if (backendStale === true) return "stale";
  if (nowMs === null || nowMs === undefined) return backendStale === false ? "fresh" : "unknown";
  return nowMs - reportedMs >= windowMs ? "stale" : "fresh";
}

/** Wall-clock freshness of the browser's copy of server state. */
export function classifySync(
  lastSyncAt: number | null | undefined,
  now: number,
  staleAfter = CLIENT_STALE_AFTER_MS,
): Freshness {
  if (!lastSyncAt) return "unknown";
  return now - lastSyncAt >= staleAfter ? "stale" : "fresh";
}

/**
 * Agent condition as known to the dashboard. A missing heartbeat alone is "stale"/"unknown",
 * never "failed": failure requires an explicit report.
 */
export type AgentCondition = "nominal" | "degraded" | "stale" | "unavailable" | "unknown";

export function agentCondition(
  a: {
    availability: string;
    communication: string;
    degraded_sensors: string[];
    last_report_ms: number | null;
  },
  nowMs: number | null,
): AgentCondition {
  if (a.availability === "unavailable") return "unavailable";
  if (a.last_report_ms === null) return "unknown";
  if (a.availability === "stale" || classifySimAge(a.last_report_ms, nowMs) === "stale") return "stale";
  if (a.availability === "unknown") return "unknown";
  if (a.degraded_sensors.length > 0 || a.communication === "degraded" || a.communication === "disconnected")
    return "degraded";
  return "nominal";
}
