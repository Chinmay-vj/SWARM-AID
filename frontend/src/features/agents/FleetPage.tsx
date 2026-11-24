import { LayoutGrid, Table } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { Agent } from "../../contracts/api";
import { DataTable, SearchField, SelectField, type Column } from "../../components/ui/data";
import { Bar, Button, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { EmptyState, QueryView } from "../../components/ui/states";
import { useLiveInterval, useMission, useMissionQuery, useMode } from "../../hooks/data";
import { agentCondition, type AgentCondition } from "../../lib/freshness";
import { formatLocation, formatSimTime, statusLabelSafe } from "./agentFormat";

const CONDITION_HELP: Record<AgentCondition, string> = {
  nominal: "Reporting, connected, no degraded sensors",
  degraded: "Reporting with degraded sensors or a degraded link",
  stale: "No report within the freshness window; not a confirmed failure",
  unavailable: "Coordinator marks the agent unavailable",
  unknown: "No report received yet",
};

export default function FleetPage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const navigate = useNavigate();
  const live = useLiveInterval();
  const mission = useMission(missionId);
  const agents = useMissionQuery(missionId, ["agents"], (p, id, s) => p.agents(id, s), {
    refetchInterval: live,
  });
  const observations = useMissionQuery(
    missionId,
    ["observations", "fleet-counts"],
    (p, id, s) => p.observations(id, { limit: 500 }, s),
    { refetchInterval: 15_000 },
  );
  const [view, setView] = useState<"grid" | "table">("grid");
  const [query, setQuery] = useState("");
  const [condition, setCondition] = useState("");
  const now = mission.data?.last_sim_ms ?? null;
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    observations.data?.items.forEach((o) => (c[o.reporter] = (c[o.reporter] ?? 0) + 1));
    return c;
  }, [observations.data]);
  const base = `/missions/${missionId}`;

  const filter = (list: Agent[]) =>
    list.filter(
      (a) =>
        (!query || a.agent_key.toLowerCase().includes(query.toLowerCase())) &&
        (!condition || agentCondition(a, now) === condition),
    );

  const columns: Column<Agent>[] = [
    {
      key: "id",
      header: "Agent",
      cell: (a) => <Link to={`${base}/fleet/${a.id}`}>{a.agent_key}</Link>,
      sort: (a) => a.agent_key,
    },
    {
      key: "cond",
      header: "Condition",
      cell: (a) => <ConditionBadge a={a} now={now} />,
      sort: (a) => agentCondition(a, now),
    },
    {
      key: "avail",
      header: "Availability",
      cell: (a) => <StatusBadge status={a.availability} />,
      sort: (a) => a.availability,
    },
    {
      key: "state",
      header: "Reported state",
      cell: (a) => statusLabelSafe(a.reported_state),
      sort: (a) => a.reported_state,
    },
    {
      key: "comm",
      header: "Link",
      cell: (a) => <StatusBadge status={a.communication} />,
      sort: (a) => a.communication,
    },
    { key: "pos", header: "Reported position", cell: (a) => formatLocation(a.location) },
    {
      key: "last",
      header: "Last report",
      cell: (a) => <span className="mono">{formatSimTime(a.last_report_ms)}</span>,
      sort: (a) => a.last_report_ms,
    },
    {
      key: "bat",
      header: "Battery",
      cell: (a) => <Bar fraction={a.battery_fraction} label={`${a.agent_key} battery`} />,
      sort: (a) => a.battery_fraction,
    },
    {
      key: "sens",
      header: "Degraded sensors",
      cell: (a) =>
        a.degraded_sensors.length ? (
          a.degraded_sensors.join(", ")
        ) : (
          <span className="muted">none reported</span>
        ),
    },
    {
      key: "obs",
      header: "Recent obs.",
      cell: (a) => counts[a.agent_key] ?? 0,
      sort: (a) => counts[a.agent_key] ?? 0,
    },
  ];

  return (
    <div className="stack">
      <PageHeader
        title="Drone fleet · Model 1 agents"
        description="Each drone runs its own Model 1 agent. Values are the agents' own reports as received by the coordinator."
        actions={<SourceTag synthetic={synthetic} />}
      />
      <Panel
        title="Agents"
        actions={
          <div className="row" role="group" aria-label="View">
            <Button
              size="sm"
              variant={view === "grid" ? "primary" : "default"}
              aria-pressed={view === "grid"}
              icon={<LayoutGrid size={13} aria-hidden="true" />}
              onClick={() => setView("grid")}
            >
              Grid
            </Button>
            <Button
              size="sm"
              variant={view === "table" ? "primary" : "default"}
              aria-pressed={view === "table"}
              icon={<Table size={13} aria-hidden="true" />}
              onClick={() => setView("table")}
            >
              Table
            </Button>
          </div>
        }
      >
        <div className="filters" style={{ marginBottom: 10 }}>
          <SearchField label="Search agent" value={query} onChange={setQuery} placeholder="d0" />
          <SelectField
            label="Condition"
            value={condition}
            onChange={setCondition}
            options={["", "nominal", "degraded", "stale", "unavailable", "unknown"]}
          />
        </div>
        <QueryView
          query={agents}
          isEmpty={(a) => a.length === 0}
          empty={
            <EmptyState title="No agents registered">Agents register when the mission starts.</EmptyState>
          }
        >
          {(list) =>
            view === "table" ? (
              <DataTable
                caption="Model 1 agents"
                rows={filter(list)}
                columns={columns}
                rowKey={(a) => a.id}
                onSelect={(a) => navigate(`${base}/fleet/${a.id}`)}
              />
            ) : (
              <div className="card-grid">
                {filter(list).map((a) => (
                  <Link key={a.id} to={`${base}/fleet/${a.id}`} className="entity-card">
                    <div className="row between">
                      <b>{a.agent_key}</b>
                      <ConditionBadge a={a} now={now} />
                    </div>
                    <div className="row" style={{ gap: 4 }}>
                      <StatusBadge status={a.availability} />
                      <StatusBadge status={a.communication} />
                      {a.reported_state && <StatusBadge status={a.reported_state} tone="info" />}
                    </div>
                    <span className="xs">{formatLocation(a.location)}</span>
                    <span className="xs muted">
                      last report {formatSimTime(a.last_report_ms)} · {counts[a.agent_key] ?? 0} recent
                      observations
                    </span>
                    <Bar fraction={a.battery_fraction} label={`${a.agent_key} battery`} />
                    {a.degraded_sensors.length > 0 && (
                      <span className="xs" style={{ color: "var(--warn)" }}>
                        ▲ degraded: {a.degraded_sensors.join(", ")}
                      </span>
                    )}
                  </Link>
                ))}
              </div>
            )
          }
        </QueryView>
        <p className="xs muted" style={{ marginTop: 8 }}>
          A missing heartbeat is shown as stale or unknown; it does not prove agent failure. Battery is shown
          only when reported.
        </p>
      </Panel>
    </div>
  );
}

export function ConditionBadge({ a, now }: { a: Agent; now: number | null }) {
  const c = agentCondition(a, now);
  return <StatusBadge status={c === "nominal" ? "available" : c} label={c} title={CONDITION_HELP[c]} />;
}
