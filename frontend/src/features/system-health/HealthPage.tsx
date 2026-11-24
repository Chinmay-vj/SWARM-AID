import { useMemo } from "react";
import { Kv, Metric, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { AlertBox, QueryView } from "../../components/ui/states";
import { keys, useMode, useProviderQuery } from "../../hooks/data";
import { classifySync } from "../../lib/freshness";
import { formatDuration, formatNumber } from "../../lib/format";
import { canReadSystemHealth } from "../../lib/permissions";
import { useConnection } from "../../stores/connection";
import { useSession } from "../../stores/session";

export function clientApiStats(samples: { status: number | null; ms: number }[]) {
  const sorted = samples.map((s) => s.ms).sort((a, b) => a - b);
  const errors = samples.filter((s) => s.status === null || s.status >= 500).length;
  return {
    n: samples.length,
    p50: sorted.length ? sorted[Math.floor(sorted.length / 2)]! : null,
    p95: sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))]! : null,
    errorRate: samples.length ? errors / samples.length : null,
    clientErrors: samples.filter((s) => s.status !== null && s.status >= 400 && s.status < 500).length,
  };
}

export default function HealthPage() {
  const mode = useMode();
  const me = useSession((s) => s.me);
  const admin = canReadSystemHealth(me) && mode === "connected";
  const conn = useConnection();
  const probe = useProviderQuery(keys.global(mode, "probe"), (p, s) => p.probe(s), {
    refetchInterval: 10_000,
  });
  const health = useProviderQuery(keys.global(mode, "system-health"), (p, s) => p.systemHealth(s), {
    enabled: admin,
    refetchInterval: 10_000,
  });
  const metrics = useProviderQuery(keys.global(mode, "system-metrics"), (p, s) => p.systemMetrics(s), {
    enabled: admin,
    refetchInterval: 15_000,
  });
  const stats = useMemo(() => clientApiStats(conn.samples), [conn.samples]);
  const sync = classifySync(conn.lastSyncAt, Date.now());

  return (
    <div className="stack">
      <PageHeader
        title="System health"
        description="Backend probes, this browser's measured API latency and the event stream. Detailed backend health requires the administrator role."
        actions={<SourceTag synthetic={mode === "synthetic"} />}
      />
      {mode === "synthetic" && (
        <AlertBox tone="info">
          Synthetic demo mode does not use the backend. Switch to connected mode to see backend health.
        </AlertBox>
      )}
      <div className="metrics">
        <Metric
          label="Backend liveness"
          value={probe.data ? (probe.data.live ? "live" : "unreachable") : "unknown"}
          tone={probe.data?.live ? "ok" : probe.data ? "bad" : "muted"}
          hint="/health/live"
        />
        <Metric
          label="Readiness"
          value={
            probe.data?.ready === null || probe.data === undefined
              ? "unknown"
              : probe.data.ready
                ? "ready"
                : "not ready"
          }
          tone={probe.data?.ready ? "ok" : probe.data?.ready === false ? "bad" : "muted"}
          hint="database + migrations"
        />
        <Metric
          label="Event stream"
          value={conn.stream}
          tone={conn.stream === "open" ? "ok" : conn.stream === "failed" ? "bad" : "warn"}
          hint={conn.streamDetail ?? "selected mission"}
        />
        <Metric
          label="Last synchronization"
          value={conn.lastSyncAt ? `${formatDuration(Date.now() - conn.lastSyncAt)} ago` : "never"}
          tone={sync === "fresh" ? "ok" : sync === "stale" ? "warn" : "muted"}
          hint={sync}
        />
        <Metric
          label="API latency p50 / p95"
          value={stats.p50 === null ? "—" : `${Math.round(stats.p50)} / ${Math.round(stats.p95 ?? 0)} ms`}
          hint={`browser-measured, ${stats.n} requests`}
        />
        <Metric
          label="API errors"
          value={stats.errorRate === null ? "—" : `${(stats.errorRate * 100).toFixed(1)}%`}
          tone={stats.errorRate ? "warn" : "ok"}
          hint={`network/5xx · ${stats.clientErrors} 4xx`}
        />
        <Metric label="Resynchronizations" value={conn.resyncCount} hint="event gaps recovered" />
      </div>
      {mode === "connected" && !canReadSystemHealth(me) && (
        <AlertBox tone="info" title="Detailed backend health is restricted.">
          The backend exposes /system/health and /system/metrics to administrators only.
        </AlertBox>
      )}
      {admin && (
        <div className="grid cols-2">
          <Panel title="Backend (administrator view)">
            <QueryView query={health} rows={6}>
              {(h) => (
                <div className="stack tight">
                  <Kv
                    items={[
                      ["Overall", <StatusBadge key="s" status={h.status === "ok" ? "healthy" : h.status} />],
                      ["Version / environment", `${h.version} · ${h.environment}`],
                      ["Database dialect", h.database.dialect],
                      [
                        "Database reachable",
                        <StatusBadge
                          key="d"
                          status={h.database.reachable ? "ok" : "unavailable"}
                          label={h.database.reachable ? "reachable" : "unreachable"}
                        />,
                      ],
                      [
                        "Migration",
                        `${h.database.migration_revision ?? "none"} (expected ${h.database.expected_revision})`,
                      ],
                      ["Transaction failures", h.database.transaction_failures],
                      ["Active simulations", `${h.simulations.active} / ${h.simulations.limit}`],
                      ["Persistence failures", h.simulations.persistence_failures],
                      ["WebSocket connections", h.websocket.connections ?? 0],
                      [
                        "Queued frames / dropped slow clients",
                        `${h.websocket.queued_frames ?? 0} / ${h.websocket.slow_clients_dropped ?? 0}`,
                      ],
                      ["Authentication failures", h.authentication_failures],
                      [
                        "Peak process memory",
                        h.process_peak_memory_mb === null
                          ? "unknown"
                          : `${formatNumber(h.process_peak_memory_mb, 1)} MB`,
                      ],
                    ]}
                  />
                  {h.database.dialect === "sqlite" && (
                    <p className="xs muted">
                      SQLite development database. PostgreSQL/PostGIS health is not shown because it is not in
                      use.
                    </p>
                  )}
                </div>
              )}
            </QueryView>
          </Panel>
          <Panel title="Running simulations and delivery">
            <QueryView query={metrics} rows={6}>
              {(m) => (
                <div className="stack tight">
                  <Kv
                    items={[
                      [
                        "WebSocket delivery p50 / p95",
                        `${m.websocket_delivery_latency_ms.p50 === null ? "—" : Math.round(m.websocket_delivery_latency_ms.p50)} / ${m.websocket_delivery_latency_ms.p95 === null ? "—" : Math.round(m.websocket_delivery_latency_ms.p95)} ms (${m.websocket_delivery_latency_ms.samples} samples)`,
                      ],
                      ...Object.entries(m.health.simulations.missions).map(
                        ([id, r]) =>
                          [
                            `Mission ${id.slice(0, 8)}`,
                            `${String(r.running ? "running" : "paused")} · ${String(r.ticks)} ticks · Model 2 ${String(r.model2_state)} · db failures ${String(r.consecutive_db_failures)}${r.last_error ? ` · last error: ${String(r.last_error)}` : ""}`,
                          ] as [string, string],
                      ),
                    ]}
                  />
                  {Object.keys(m.health.simulations.missions).length === 0 && (
                    <p className="small muted">No simulation is running.</p>
                  )}
                </div>
              )}
            </QueryView>
          </Panel>
        </div>
      )}
    </div>
  );
}
