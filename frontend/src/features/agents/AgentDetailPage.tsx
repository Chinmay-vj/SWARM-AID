import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { AgentReport, Observation } from "../../contracts/api";
import { DataTable, Pagination, Tabs, type Column } from "../../components/ui/data";
import { Bar, Kv, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { EmptyState, QueryView } from "../../components/ui/states";
import { useLiveInterval, useMission, useMissionQuery, useMode } from "../../hooks/data";
import { formatConfidence, formatLocation, formatSimTime, humanize } from "../../lib/format";
import { ConditionBadge } from "./FleetPage";
import { useActivity } from "../../stores/activity";
import { EventList } from "../events/EventList";

type Tab = "overview" | "status" | "positions" | "observations" | "events";
const PAGE = 25;

export default function AgentDetailPage() {
  const { missionId, agentId } = useParams();
  const synthetic = useMode() === "synthetic";
  const live = useLiveInterval();
  const mission = useMission(missionId);
  const agent = useMissionQuery(missionId, ["agent", agentId], (p, _id, s) => p.agent(agentId!, s), {
    refetchInterval: live,
  });
  const [tab, setTab] = useState<Tab>("overview");
  const [offset, setOffset] = useState(0);
  const status = useMissionQuery(
    missionId,
    ["agent", agentId, "status", offset],
    (p, _id, s) => p.agentReports(agentId!, "status", { limit: PAGE, offset }, s),
    { enabled: tab === "status" },
  );
  const positions = useMissionQuery(
    missionId,
    ["agent", agentId, "positions", offset],
    (p, _id, s) => p.agentReports(agentId!, "location-history", { limit: PAGE, offset }, s),
    { enabled: tab === "positions" || tab === "overview" },
  );
  const observations = useMissionQuery(
    missionId,
    ["agent", agentId, "observations", offset],
    (p, _id, s) => p.agentObservations(agentId!, { limit: PAGE, offset }, s),
    { enabled: tab === "observations" || tab === "overview" },
  );
  const tasks = useMissionQuery(
    missionId,
    ["tasks", "agent", agent.data?.agent_key],
    (p, id, s) => p.tasks(id, { member: agent.data!.agent_key, limit: 50 }, s),
    { enabled: Boolean(agent.data) },
  );
  const allEvents = useActivity((s) => s.events);
  const agentKey = agent.data?.agent_key;
  const events = useMemo(
    () =>
      allEvents.filter(
        (e) =>
          e.resource_id === agentId ||
          (agentKey !== undefined &&
            (e.payload.agent_key === agentKey ||
              e.payload.reporter === agentKey ||
              e.payload.member === agentKey)),
      ),
    [allEvents, agentId, agentKey],
  );
  const base = `/missions/${missionId}`;

  const reportCols: Column<AgentReport>[] = [
    {
      key: "t",
      header: "Sim time",
      cell: (r) => <span className="mono">{formatSimTime(r.sim_time_ms)}</span>,
    },
    {
      key: "s",
      header: "State",
      cell: (r) => (r.state ? <StatusBadge status={r.state} tone="info" /> : "—"),
    },
    { key: "l", header: "Reported location", cell: (r) => formatLocation(r.location) },
    {
      key: "b",
      header: "Battery",
      cell: (r) => (r.battery_fraction === null ? "—" : `${Math.round(r.battery_fraction * 100)}%`),
    },
    {
      key: "d",
      header: "Details",
      cell: (r) =>
        Array.isArray(r.details.degraded_sensors) && r.details.degraded_sensors.length
          ? `degraded: ${r.details.degraded_sensors.join(", ")}`
          : "",
    },
  ];
  const obsCols: Column<Observation>[] = [
    {
      key: "t",
      header: "Observed",
      cell: (o) => <span className="mono">{formatSimTime(o.observed_ms)}</span>,
    },
    { key: "k", header: "Kind", cell: (o) => `${humanize(o.kind)}${o.label ? ` · ${o.label}` : ""}` },
    { key: "c", header: "Confidence", cell: (o) => formatConfidence(o.confidence) },
    { key: "l", header: "Location", cell: (o) => formatLocation(o.location) },
    { key: "o", header: "Outcome", cell: (o) => <StatusBadge status={o.outcome} tone="info" /> },
    { key: "f", header: "Freshness", cell: (o) => <StatusBadge status={o.stale ? "stale" : "fresh"} /> },
  ];

  return (
    <QueryView query={agent} rows={6}>
      {(a) => (
        <div className="stack">
          <PageHeader
            title={`Agent ${a.agent_key}`}
            description={`Model 1 ${a.kind} agent · reported data only (private agent memory is not exposed)`}
            actions={
              <>
                <SourceTag synthetic={synthetic} />
                <Link to={`${base}/fleet`}>Back to fleet</Link>
              </>
            }
          />
          <Tabs<Tab>
            label="Agent sections"
            active={tab}
            onChange={(t) => {
              setTab(t);
              setOffset(0);
            }}
            tabs={[
              { key: "overview", label: "Overview" },
              { key: "status", label: "Status history" },
              { key: "positions", label: "Position history" },
              { key: "observations", label: "Observations" },
              { key: "events", label: "Event timeline" },
            ]}
          />
          {tab === "overview" && (
            <div className="grid cols-2">
              <Panel title="Reported status">
                <Kv
                  items={[
                    ["Condition", <ConditionBadge key="c" a={a} now={mission.data?.last_sim_ms ?? null} />],
                    ["Availability (coordinator)", <StatusBadge key="a" status={a.availability} />],
                    [
                      "Reported state",
                      a.reported_state ? (
                        <StatusBadge key="s" status={a.reported_state} tone="info" />
                      ) : (
                        "not reported"
                      ),
                    ],
                    ["Communication", <StatusBadge key="m" status={a.communication} />],
                    ["Last report", formatSimTime(a.last_report_ms)],
                    ["Reported position", formatLocation(a.location)],
                    ["Position reported at", formatSimTime(a.last_location_ms)],
                    ["Battery", <Bar key="b" fraction={a.battery_fraction} label="battery" />],
                    [
                      "Degraded sensors",
                      a.degraded_sensors.length ? a.degraded_sensors.join(", ") : "none reported",
                    ],
                    ["Observations (total)", observations.data?.total ?? "—"],
                  ]}
                />
              </Panel>
              <Panel title="Tasks">
                <QueryView
                  query={tasks}
                  isEmpty={(p) => p.items.length === 0}
                  empty={<EmptyState title="No tasks recorded for this agent" />}
                >
                  {(p) => (
                    <div className="stack tight">
                      {p.items.slice(0, 10).map((t) => (
                        <div key={t.id} className="row between">
                          <span>
                            {humanize(t.category)} → {formatLocation(t.target)}
                          </span>
                          <span className="row" style={{ gap: 4 }}>
                            <StatusBadge status={t.coordinator_state} tone="info" />
                            <StatusBadge status={t.knowledge} />
                          </span>
                        </div>
                      ))}
                      <Link to={`${base}/coordination`}>All tasks</Link>
                    </div>
                  )}
                </QueryView>
              </Panel>
              <Panel title="Recent positions">
                <QueryView
                  query={positions}
                  isEmpty={(p) => p.items.length === 0}
                  empty={<EmptyState title="No position reports" />}
                >
                  {(p) => (
                    <DataTable
                      caption="Recent positions"
                      rows={p.items.slice(0, 6)}
                      columns={reportCols.slice(0, 4)}
                      rowKey={(r) => `${r.sim_time_ms}`}
                    />
                  )}
                </QueryView>
              </Panel>
              <Panel title="Recent observations">
                <QueryView
                  query={observations}
                  isEmpty={(p) => p.items.length === 0}
                  empty={<EmptyState title="No observations from this agent" />}
                >
                  {(p) => (
                    <DataTable
                      caption="Recent observations"
                      rows={p.items.slice(0, 6)}
                      columns={obsCols.slice(0, 4)}
                      rowKey={(o) => o.id}
                    />
                  )}
                </QueryView>
              </Panel>
            </div>
          )}
          {tab === "status" && (
            <Panel title="Status reports (heartbeats)">
              <QueryView query={status} isEmpty={(p) => p.items.length === 0}>
                {(p) => (
                  <>
                    <DataTable
                      caption="Status reports"
                      rows={p.items}
                      columns={reportCols}
                      rowKey={(r) => `${r.sim_time_ms}-${r.state}`}
                    />
                    <Pagination total={p.total} limit={PAGE} offset={offset} onChange={setOffset} />
                  </>
                )}
              </QueryView>
            </Panel>
          )}
          {tab === "positions" && (
            <Panel title="Position and health reports">
              <QueryView query={positions} isEmpty={(p) => p.items.length === 0}>
                {(p) => (
                  <>
                    <DataTable
                      caption="Position history"
                      rows={p.items}
                      columns={reportCols}
                      rowKey={(r) => `${r.sim_time_ms}`}
                    />
                    <Pagination total={p.total} limit={PAGE} offset={offset} onChange={setOffset} />
                  </>
                )}
              </QueryView>
            </Panel>
          )}
          {tab === "observations" && (
            <Panel title="Observations reported by this agent">
              <QueryView query={observations} isEmpty={(p) => p.items.length === 0}>
                {(p) => (
                  <>
                    <DataTable
                      caption="Agent observations"
                      rows={p.items}
                      columns={obsCols}
                      rowKey={(o) => o.id}
                    />
                    <Pagination total={p.total} limit={PAGE} offset={offset} onChange={setOffset} />
                  </>
                )}
              </QueryView>
            </Panel>
          )}
          {tab === "events" && (
            <Panel title="Events for this agent (this session)">
              <EventList events={events} missionId={missionId!} synthetic={synthetic} />
            </Panel>
          )}
        </div>
      )}
    </QueryView>
  );
}
