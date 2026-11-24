/**
 * Mission research analytics from measured backend data:
 *  - time series from METRICS_UPDATED events (operational metrics published by the runtime),
 *  - human review latency from persisted decisions,
 *  - per-run operational metrics.
 * Evaluator ground truth (verified coverage, missed people) is only available through the
 * research export, which requires the researcher mission role. Nothing is estimated here.
 */
import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { SeriesChart } from "../../components/charts/SeriesChart";
import { DataTable, type Column } from "../../components/ui/data";
import { Button, Kv, Metric, PageHeader, Panel, SourceTag } from "../../components/ui/primitives";
import { AlertBox, EmptyState, QueryView } from "../../components/ui/states";
import {
  useLiveInterval,
  useMissionPermissions,
  useMissionQuery,
  useMode,
  useProvider,
} from "../../hooks/data";
import { downloadText, sanitizeCsvText } from "../../lib/csv";
import { formatDuration, formatFraction, formatNumber, formatSimTime } from "../../lib/format";
import { summarize } from "../../lib/stats";
import { asApiError } from "../../services/api/errors";
import type { ExportFormat, ExportKind } from "../../services/providers/types";

export const METRIC_DEFINITIONS: [string, string, string][] = [
  [
    "Reported coverage",
    "fraction of grid cells",
    "Cells agents reported as observed ÷ all cells. Agent-reported; not verified.",
  ],
  [
    "Evaluator-measured coverage",
    "fraction",
    "Simulator ground truth; research export only (researcher role).",
  ],
  ["Admitted findings", "count", "Model 1 reports admitted by Model 2."],
  ["Delivery ratio", "0–1", "Delivered ÷ intended messages in the simulated network."],
  ["Communication latency", "ms (simulation)", "Mean / median / p95 message delivery time."],
  ["Incidents", "count", "Incidents Model 2 has opened."],
  ["Tasks issued", "count", "Coordination tasks issued (Phase 5)."],
  [
    "Human review latency",
    "ms (wall clock)",
    "Decision resolved_at − submitted_at, from persisted decisions.",
  ],
];

interface Point extends Record<string, number | null> {
  t: number;
  reported_cells: number | null;
  findings: number | null;
  incidents: number | null;
  delivery: number | null;
  tasks: number | null;
  latency: number | null;
}

export default function AnalyticsPage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const live = useLiveInterval();
  const perms = useMissionPermissions(missionId);
  const metrics = useMissionQuery(missionId, ["metrics"], (p, id, s) => p.metrics(id, s), {
    refetchInterval: live,
    enabled: perms.has("metrics.read"),
  });
  const series = useMissionQuery(
    missionId,
    ["analytics", "series"],
    (p, id, s) => p.events(id, { after: 0, limit: 1000, eventType: "METRICS_UPDATED" }, s),
    { refetchInterval: live, enabled: perms.has("metrics.read") },
  );
  const decisions = useMissionQuery(
    missionId,
    ["decisions", "analytics"],
    (p, id, s) => p.decisions(id, { limit: 500 }, s),
    { enabled: perms.has("metrics.read") },
  );
  const summary = useMissionQuery(missionId, ["summary"], (p, id, s) => p.summary(id, s), {
    refetchInterval: live,
  });

  const points = useMemo<Point[]>(
    () =>
      (series.data ?? []).map((e) => {
        const p = e.payload as Record<string, unknown>;
        const comm = (p.communication ?? {}) as Record<string, unknown>;
        const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
        return {
          t: (num(p.sim_time_ms) ?? e.sim_time_ms ?? 0) / 1000,
          reported_cells: num(p.reported_cells),
          findings: num(p.admitted_findings),
          incidents: num(p.incidents),
          delivery: num(comm.delivery_ratio),
          tasks: num(p.tasks_issued),
          latency: num(comm.mean_ms),
        };
      }),
    [series.data],
  );
  const latency = useMemo(
    () =>
      summarize(
        (decisions.data?.items ?? [])
          .filter((d) => d.resolved_at && d.kind !== "alert_acknowledgement")
          .map((d) => Date.parse(d.resolved_at!) - Date.parse(d.submitted_at)),
      ),
    [decisions.data],
  );

  if (!perms.has("metrics.read"))
    return (
      <div className="stack">
        <PageHeader title="Research analytics" />
        <AlertBox tone="info" title="Not available for your mission role.">
          Research metrics require the coordinator or researcher mission role (metrics.read).
        </AlertBox>
      </div>
    );

  const runCols: Column<NonNullable<typeof metrics.data>["runs"][number]>[] = [
    { key: "r", header: "Run", cell: (r) => <code>{r.run_id.slice(0, 8)}</code> },
    { key: "s", header: "Started", cell: (r) => new Date(r.started_at).toLocaleString() },
    { key: "e", header: "End reason", cell: (r) => r.end_reason ?? "running" },
    { key: "t", header: "Final sim time", cell: (r) => formatSimTime(r.final_sim_ms) },
    {
      key: "f",
      header: "Admitted findings",
      cell: (r) => formatNumber(r.operational_metrics?.admitted_findings ?? null),
    },
    { key: "i", header: "Incidents", cell: (r) => formatNumber(r.operational_metrics?.incidents ?? null) },
    {
      key: "c",
      header: "Reported cells",
      cell: (r) => formatNumber(r.operational_metrics?.reported_cells ?? null),
    },
    {
      key: "d",
      header: "Delivery ratio",
      cell: (r) => formatFraction(r.operational_metrics?.communication?.delivery_ratio ?? null, 1),
    },
  ];

  return (
    <div className="stack">
      <PageHeader
        title="Research analytics"
        description="Measured metrics for this mission from the backend. Missing measurements are shown as missing."
        actions={<SourceTag synthetic={synthetic} measured={!synthetic} />}
      />
      {synthetic && (
        <AlertBox tone="warn" title="Synthetic demonstration metrics.">
          These values come from in-browser playback and are not research results.
        </AlertBox>
      )}
      <div className="metrics">
        <Metric
          label="Observations"
          value={summary.data?.observations ?? "—"}
          hint="persisted reports"
          synthetic={synthetic}
        />
        <Metric
          label="Admitted findings"
          value={formatNumber(points.at(-1)?.findings ?? null)}
          hint="latest metrics event"
          synthetic={synthetic}
        />
        <Metric
          label="Reported cells"
          value={formatNumber(points.at(-1)?.reported_cells ?? null)}
          hint="agent-reported"
          synthetic={synthetic}
        />
        <Metric
          label="Delivery ratio"
          value={formatFraction(points.at(-1)?.delivery ?? null, 1)}
          hint="simulated network"
          synthetic={synthetic}
        />
        <Metric
          label="Human review latency"
          value={latency.median === null ? "—" : formatDuration(latency.median)}
          hint={`median of ${latency.n} resolved decisions`}
          synthetic={synthetic}
        />
        <Metric
          label="Pending recommendations"
          value={summary.data?.pending_recommendations ?? "—"}
          hint="awaiting review"
          synthetic={synthetic}
        />
      </div>
      <QueryView
        query={series}
        rows={4}
        isEmpty={(s) => s.length === 0}
        empty={
          <Panel>
            <EmptyState title="No metrics events yet">
              The runtime publishes METRICS_UPDATED every 10 ticks while a mission runs.
            </EmptyState>
          </Panel>
        }
      >
        {() => (
          <div className="grid cols-2">
            <Panel title="Reported coverage and findings">
              <SeriesChart
                title="Reported cells and admitted findings over simulation time"
                points={points}
                x="t"
                xLabel="sim time (s)"
                series={[
                  { key: "reported_cells", label: "Reported cells", color: "var(--chart-2)" },
                  { key: "findings", label: "Admitted findings", color: "var(--chart-1)" },
                ]}
              />
            </Panel>
            <Panel title="Incidents and tasks">
              <SeriesChart
                title="Incidents and coordination tasks over simulation time"
                points={points}
                x="t"
                xLabel="sim time (s)"
                series={[
                  { key: "incidents", label: "Incidents", color: "var(--chart-5)" },
                  { key: "tasks", label: "Tasks issued", color: "var(--chart-3)" },
                ]}
              />
            </Panel>
            <Panel title="Communication delivery ratio">
              <SeriesChart
                title="Delivery ratio over simulation time"
                points={points}
                x="t"
                xLabel="sim time (s)"
                series={[{ key: "delivery", label: "Delivery ratio", color: "var(--chart-4)" }]}
              />
            </Panel>
            <Panel title="Communication latency">
              <SeriesChart
                title="Mean message latency over simulation time"
                points={points}
                x="t"
                xLabel="sim time (s)"
                yLabel="ms"
                series={[{ key: "latency", label: "Mean latency (ms)", color: "var(--chart-1)" }]}
              />
            </Panel>
          </div>
        )}
      </QueryView>
      <div className="grid cols-2">
        <Panel title="Human review latency (wall clock)">
          {latency.n === 0 ? (
            <EmptyState title="No resolved decisions" />
          ) : (
            <Kv
              items={[
                ["Resolved decisions (n)", latency.n],
                ["Mean", formatDuration(latency.mean)],
                ["Median", formatDuration(latency.median)],
                ["Standard deviation", formatDuration(latency.sd)],
                ["Range", `${formatDuration(latency.min)} – ${formatDuration(latency.max)}`],
                [
                  "95% CI (mean)",
                  latency.ci95
                    ? `${formatDuration(latency.ci95[0])} – ${formatDuration(latency.ci95[1])}`
                    : "needs n ≥ 2",
                ],
              ]}
            />
          )}
        </Panel>
        <Panel title="Metric definitions">
          <table className="table">
            <caption className="sr-only">Metric definitions</caption>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">Unit</th>
                <th scope="col">Definition</th>
              </tr>
            </thead>
            <tbody>
              {METRIC_DEFINITIONS.map(([a, b, c]) => (
                <tr key={a}>
                  <td>{a}</td>
                  <td>{b}</td>
                  <td>{c}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
      <Panel title="Simulation runs">
        <QueryView
          query={metrics}
          isEmpty={(m2) => m2.runs.length === 0}
          empty={<EmptyState title="No runs recorded" />}
        >
          {(m2) => (
            <DataTable caption="Simulation runs" rows={m2.runs} columns={runCols} rowKey={(r) => r.run_id} />
          )}
        </QueryView>
      </Panel>
      <ExportsPanel missionId={missionId!} synthetic={synthetic} />
    </div>
  );
}

function ExportsPanel({ missionId, synthetic }: { missionId: string; synthetic: boolean }) {
  const provider = useProvider();
  const perms = useMissionPermissions(missionId);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async (kind: ExportKind, format: ExportFormat) => {
    setBusy(`${kind}-${format}`);
    setError(null);
    try {
      const text = await provider.exportMission(missionId, kind, format);
      const name = `${synthetic ? "SYNTHETIC-" : ""}mission-${missionId}-${kind}.${format}`;
      downloadText(
        name,
        format === "csv" ? sanitizeCsvText(text) : text,
        format === "csv" ? "text/csv" : "application/json",
      );
    } catch (e) {
      setError(asApiError(e).userMessage);
    } finally {
      setBusy(null);
    }
  };
  return (
    <Panel title="Research exports">
      <p className="small">
        Exports include reproducibility metadata (scenario, seed, agent count, coordination policy, Model 2
        mode, software version, git revision per run, timestamps). The operational export contains reported
        and decided data; the research export adds evaluator ground truth and requires the researcher role.
        CSV cells are neutralised against formula injection.
      </p>
      <div className="row" style={{ marginTop: 8 }}>
        {(["operational", "research"] as const).map((kind) =>
          (["json", "csv"] as const).map((format) => {
            const permission = kind === "research" ? "export.research" : "export.operational";
            const allowed = perms.has(permission);
            return (
              <Button
                key={`${kind}-${format}`}
                icon={<Download size={14} aria-hidden="true" />}
                disabled={!allowed || busy !== null}
                title={!allowed ? `Requires ${permission}` : undefined}
                onClick={() => void run(kind, format)}
              >
                {busy === `${kind}-${format}` ? "Exporting…" : `${kind} ${format.toUpperCase()}`}
              </Button>
            );
          }),
        )}
      </div>
      {synthetic && (
        <p className="xs muted">Synthetic exports are labelled SYNTHETIC in the file name and content.</p>
      )}
      {error && <AlertBox tone="bad">{error}</AlertBox>}
    </Panel>
  );
}
