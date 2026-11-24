/**
 * Phase 5 and Phase 6 experiment comparison from stored, evaluator-measured results
 * (GET /api/v1/experiments). Statistics are computed from the stored episode rows only.
 * Trained-model and MARL baselines are future work; new experiment families appear here when
 * their runners write comparison.csv files.
 */
import { useMemo, useState } from "react";
import type { ExperimentInfo } from "../../contracts/api";
import { MeanBarChart } from "../../components/charts/SeriesChart";
import { DataTable, SelectField, type Column } from "../../components/ui/data";
import { Kv, PageHeader, Panel, SourceTag } from "../../components/ui/primitives";
import { AlertBox, EmptyState, QueryView } from "../../components/ui/states";
import { keys, useMode, useProviderQuery } from "../../hooks/data";
import { downloadText, toCsv } from "../../lib/csv";
import { formatWallTime } from "../../lib/format";
import { groupSummaries, numericColumns, type Row } from "../../lib/stats";
import { usePreferences } from "../../stores/preferences";

const BASELINES: Record<string, string> = {
  independent: "Independent coordination",
  fixed_sector: "Fixed-sector coordination",
  shared_information: "Shared-information coordination",
  direct: "Direct report forwarding",
  rules: "Individual rule-based assessment",
  fusion: "Multi-agent evidence fusion",
};
const IDENTIFIERS = new Set(["scenario", "agents", "seed", "policy", "mode"]);
const fmt = (v: number | null) => (v === null ? "—" : Math.abs(v) < 10 ? v.toFixed(4) : v.toFixed(2));

export default function ExperimentsPage() {
  const mode = useMode();
  const timeDisplay = usePreferences((s) => s.timeDisplay);
  const list = useProviderQuery(keys.global(mode, "experiments"), (p, s) => p.experiments(s), {
    staleTime: 30_000,
  });
  const [selected, setSelected] = useState("");
  const chosen = selected || list.data?.[0]?.experiment_id || "";
  const detail = useProviderQuery(
    keys.global(mode, "experiment", chosen),
    (p, s) => p.experiment(chosen, s),
    { enabled: Boolean(chosen), staleTime: 60_000 },
  );
  const [metric, setMetric] = useState("");
  const [scenario, setScenario] = useState("");
  const [agents, setAgents] = useState("");

  const rows = useMemo(() => (detail.data?.data ?? []) as Row[], [detail.data]);
  const family = detail.data?.family;
  const factor = family === "command" ? "mode" : "policy";
  const metrics = useMemo(
    () => (detail.data ? numericColumns(rows, detail.data.columns).filter((c) => !IDENTIFIERS.has(c)) : []),
    [rows, detail.data],
  );
  const activeMetric = metric && metrics.includes(metric) ? metric : (metrics[0] ?? "");
  const filtered = rows.filter(
    (r) => (!scenario || r.scenario === scenario) && (!agents || String(r.agents) === agents),
  );
  const groups = useMemo(
    () => (activeMetric ? groupSummaries(filtered, ["scenario", "agents", factor], activeMetric) : []),
    [filtered, activeMetric, factor],
  );
  const scenarios = [...new Set(rows.map((r) => String(r.scenario)))];
  const agentCounts = [...new Set(rows.map((r) => String(r.agents)))].sort((a, b) => Number(a) - Number(b));
  const seeds = [...new Set(rows.map((r) => String(r.seed)))];

  const cols: Column<(typeof groups)[number]>[] = [
    {
      key: "s",
      header: "Scenario",
      cell: (g) => String(g.group.scenario),
      sort: (g) => String(g.group.scenario),
    },
    { key: "a", header: "Agents", cell: (g) => String(g.group.agents), sort: (g) => Number(g.group.agents) },
    {
      key: "f",
      header: family === "command" ? "Model 2 mode" : "Coordination policy",
      cell: (g) => BASELINES[String(g.group[factor])] ?? String(g.group[factor]),
      sort: (g) => String(g.group[factor]),
    },
    { key: "n", header: "n", cell: (g) => g.summary.n, sort: (g) => g.summary.n },
    { key: "mean", header: "Mean", cell: (g) => fmt(g.summary.mean), sort: (g) => g.summary.mean },
    { key: "med", header: "Median", cell: (g) => fmt(g.summary.median), sort: (g) => g.summary.median },
    { key: "sd", header: "SD", cell: (g) => fmt(g.summary.sd) },
    {
      key: "ci",
      header: "95% CI",
      cell: (g) => (g.summary.ci95 ? `${fmt(g.summary.ci95[0])} – ${fmt(g.summary.ci95[1])}` : "n < 2"),
    },
    { key: "miss", header: "Missing", cell: (g) => g.summary.missing },
  ];

  const exportCsv = () => {
    if (!detail.data) return;
    const header = [
      "experiment_id",
      "family",
      "scenario",
      "agents",
      factor,
      "metric",
      "n",
      "missing",
      "mean",
      "median",
      "sd",
      "ci95_low",
      "ci95_high",
      "data_source",
    ];
    const body = groups.map((g) => [
      detail.data!.experiment_id,
      family,
      g.group.scenario,
      g.group.agents,
      g.group[factor],
      activeMetric,
      g.summary.n,
      g.summary.missing,
      g.summary.mean,
      g.summary.median,
      g.summary.sd,
      g.summary.ci95?.[0] ?? "",
      g.summary.ci95?.[1] ?? "",
      "stored experiment results (evaluator-measured)",
    ]);
    downloadText(
      `experiment-${detail.data.experiment_id}-${activeMetric}-summary.csv`,
      toCsv(header, body),
      "text/csv",
    );
  };

  return (
    <div className="stack">
      <PageHeader
        title="Experiment results"
        description="Stored Phase 5 coordination and Phase 6 command-agent baseline comparisons. Values are evaluator-measured simulation results; summaries are computed from stored episodes only."
        actions={<SourceTag synthetic={false} measured />}
      />
      <QueryView
        query={list}
        rows={4}
        isEmpty={(l) => l.length === 0}
        empty={
          <Panel>
            <EmptyState title="No stored experiments found">
              Run python -m evaluation.experiment_runner or evaluation.command_agent_experiments; results are
              read from the backend's experiments directory.
            </EmptyState>
          </Panel>
        }
      >
        {(experiments) => (
          <>
            <Panel title="Experiment">
              <div className="filters">
                <SelectField
                  label="Experiment"
                  value={chosen}
                  onChange={(v) => {
                    setSelected(v);
                    setMetric("");
                    setScenario("");
                    setAgents("");
                  }}
                  options={experiments.map((e: ExperimentInfo) => ({
                    value: e.experiment_id,
                    label: `${e.collection} · ${e.family} · ${e.rows} episodes · ${e.experiment_id.slice(0, 8)}`,
                  }))}
                />
                <SelectField label="Metric" value={activeMetric} onChange={setMetric} options={metrics} />
                <SelectField
                  label="Scenario"
                  value={scenario}
                  onChange={setScenario}
                  options={["", ...scenarios]}
                />
                <SelectField
                  label="Agents"
                  value={agents}
                  onChange={setAgents}
                  options={["", ...agentCounts]}
                />
              </div>
            </Panel>
            <QueryView query={detail} rows={6}>
              {(d) => (
                <>
                  <div className="grid side-main">
                    <Panel title="Metadata">
                      <Kv
                        items={[
                          ["Experiment ID", <code key="i">{d.experiment_id}</code>],
                          [
                            "Family",
                            d.family === "coordination"
                              ? "Phase 5 coordination baselines"
                              : "Phase 6 Model 2 baselines",
                          ],
                          ["Collection", d.collection],
                          ["Created", formatWallTime(d.created_at, timeDisplay)],
                          ["Episodes", `${d.rows} rows · ${d.episodes} episode files`],
                          ["Seeds", seeds.join(", ")],
                          ["Simulator version", d.simulator_version ?? "not recorded"],
                          ["Columns", d.columns.join(", ")],
                        ]}
                      />
                      {d.definitions && (
                        <>
                          <h3 style={{ marginTop: 10 }}>Definitions</h3>
                          <Kv items={Object.entries(d.definitions)} />
                        </>
                      )}
                    </Panel>
                    <Panel
                      title={`Mean ${activeMetric} by ${family === "command" ? "Model 2 mode" : "policy"}`}
                    >
                      <MeanBarChart
                        title={`${activeMetric} per group`}
                        label={activeMetric}
                        rows={groups.map((g) => ({
                          name: `${String(g.group.scenario).replace(/_basic$/, "")}/${g.group.agents}/${g.group[factor]}`,
                          mean: g.summary.mean,
                          low: g.summary.ci95?.[0] ?? null,
                          high: g.summary.ci95?.[1] ?? null,
                        }))}
                      />
                    </Panel>
                  </div>
                  <Panel
                    title="Comparison table"
                    actions={
                      <button className="btn sm" onClick={exportCsv}>
                        Export summary CSV
                      </button>
                    }
                  >
                    {groups.some((g) => g.summary.n < 3) && (
                      <AlertBox tone="warn">
                        Some groups have fewer than 3 samples; intervals are wide or unavailable. Do not
                        over-interpret differences.
                      </AlertBox>
                    )}
                    <DataTable
                      caption="Experiment comparison"
                      rows={groups}
                      columns={cols}
                      rowKey={(g) => JSON.stringify(g.group)}
                    />
                    <p className="xs muted" style={{ marginTop: 6 }}>
                      95% intervals use Student t on the episode values. Trained-model and MARL results are
                      not available yet (later phases).
                    </p>
                  </Panel>
                </>
              )}
            </QueryView>
          </>
        )}
      </QueryView>
    </div>
  );
}
