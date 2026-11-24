import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import type { CoordinationConflict, Task } from "../../contracts/api";
import { DataTable, Pagination, SelectField, type Column } from "../../components/ui/data";
import { Kv, Metric, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { EmptyState, QueryView } from "../../components/ui/states";
import { useLiveInterval, useMissionQuery, useMode } from "../../hooks/data";
import { formatFraction, formatLocation, formatSimTime, humanize, shortId } from "../../lib/format";

const PAGE = 50;

export default function CoordinationPage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const live = useLiveInterval();
  const [member, setMember] = useState("");
  const [state, setState] = useState("");
  const [knowledge, setKnowledge] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const tasks = useMissionQuery(
    missionId,
    ["tasks", member, state, offset],
    (p, id, s) =>
      p.tasks(id, { member: member || undefined, state: state || undefined, limit: PAGE, offset }, s),
    { refetchInterval: live },
  );
  const agents = useMissionQuery(missionId, ["agents"], (p, id, s) => p.agents(id, s));
  const coverage = useMissionQuery(missionId, ["coverage"], (p, id, s) => p.coverage(id, s), {
    refetchInterval: live,
  });
  const sectors = useMissionQuery(missionId, ["coverage", "sectors"], (p, id, s) => p.sectors(id, s));
  const conflicts = useMissionQuery(missionId, ["tasks", "conflicts"], (p, id, s) => p.conflicts(id, s), {
    refetchInterval: live,
  });
  const history = useMissionQuery(
    missionId,
    ["tasks", "history", selected],
    (p, _id, s) => p.taskHistory(selected!, s),
    { enabled: Boolean(selected) },
  );

  const overlap = useMemo(() => {
    const seen = new Map<string, string[]>();
    sectors.data?.forEach((s) =>
      s.cells.forEach(([x, y]) => seen.set(`${x},${y}`, [...(seen.get(`${x},${y}`) ?? []), s.member])),
    );
    return [...seen.values()].filter((m) => m.length > 1).length;
  }, [sectors.data]);

  const cols: Column<Task>[] = [
    { key: "id", header: "Task", cell: (t) => <code>{shortId(t.id)}</code> },
    { key: "cat", header: "Category", cell: (t) => humanize(t.category), sort: (t) => t.category },
    { key: "m", header: "Assigned agent", cell: (t) => t.member, sort: (t) => t.member },
    { key: "tg", header: "Target", cell: (t) => formatLocation(t.target) },
    {
      key: "c",
      header: "Coordinator state",
      cell: (t) => <StatusBadge status={t.coordinator_state} tone="info" />,
      sort: (t) => t.coordinator_state,
    },
    {
      key: "r",
      header: "Agent-reported",
      cell: (t) =>
        t.reported_status ? (
          `${t.reported_status} @ ${formatSimTime(t.reported_ms)}`
        ) : (
          <span className="muted">not reported</span>
        ),
    },
    {
      key: "k",
      header: "Knowledge",
      cell: (t) => <StatusBadge status={t.knowledge} />,
      sort: (t) => t.knowledge,
    },
    {
      key: "u",
      header: "Updated",
      cell: (t) => <span className="mono">{formatSimTime(t.updated_ms)}</span>,
      sort: (t) => t.updated_ms,
    },
    { key: "e", header: "Expires", cell: (t) => <span className="mono">{formatSimTime(t.expires_ms)}</span> },
  ];
  const conflictCols: Column<CoordinationConflict>[] = [
    {
      key: "t",
      header: "Sim time",
      cell: (c) => <span className="mono">{formatSimTime(c.sim_time_ms)}</span>,
    },
    { key: "s", header: "Source", cell: (c) => c.source },
    { key: "r", header: "Reason", cell: (c) => c.reason },
    { key: "m", header: "Message", cell: (c) => (c.message_id ? <code>{shortId(c.message_id)}</code> : "—") },
  ];

  return (
    <div className="stack">
      <PageHeader
        title="Tasks & coordination"
        description="Phase 5 coordination as known to the coordinator. Coordinator state and agent-reported status are shown separately; disagreements are marked conflicting, missing reports stale or unknown."
        actions={<SourceTag synthetic={synthetic} />}
      />
      <div className="metrics">
        <Metric
          label="Reported coverage"
          value={formatFraction(coverage.data?.reported_fraction)}
          hint={`${coverage.data?.reported_cells.length ?? "?"} cells reported · ${coverage.data?.unknown_cells ?? "?"} unknown`}
          tone="ok"
          synthetic={synthetic}
        />
        <Metric label="Tasks" value={tasks.data?.total ?? "—"} hint="all states" synthetic={synthetic} />
        <Metric
          label="Coordination conflicts"
          value={conflicts.data?.length ?? "—"}
          hint="rejected/invalid transitions"
          tone="warn"
          synthetic={synthetic}
        />
        <Metric
          label="Overlapping sector cells"
          value={sectors.data ? overlap : "—"}
          hint="cells assigned to >1 agent"
          tone="info"
          synthetic={synthetic}
        />
      </div>
      <Panel title="Tasks">
        <div className="filters" style={{ marginBottom: 8 }}>
          <SelectField
            label="Agent"
            value={member}
            onChange={(v) => {
              setMember(v);
              setOffset(0);
            }}
            options={[
              { value: "", label: "All" },
              ...(agents.data ?? []).map((a) => ({ value: a.agent_key, label: a.agent_key })),
            ]}
          />
          <SelectField
            label="Coordinator state"
            value={state}
            onChange={(v) => {
              setState(v);
              setOffset(0);
            }}
            options={[
              "",
              "pending",
              "assigned",
              "accepted",
              "in_progress",
              "completed",
              "rejected",
              "expired",
              "cancelled",
            ]}
          />
          <SelectField
            label="Knowledge"
            value={knowledge}
            onChange={setKnowledge}
            options={["", "coordinator_known", "reported", "conflicting", "stale", "unknown"]}
            help="Filters the current page"
          />
        </div>
        <QueryView
          query={tasks}
          isEmpty={(p) => p.items.length === 0}
          empty={<EmptyState title="No tasks">Independent coordination issues no tasks.</EmptyState>}
        >
          {(p) => (
            <>
              <DataTable
                caption="Tasks"
                rows={p.items.filter((t) => !knowledge || t.knowledge === knowledge)}
                columns={cols}
                rowKey={(t) => t.id}
                onSelect={(t) => setSelected(t.id)}
                selectedKey={selected}
                initialSort={{ key: "u", dir: "desc" }}
              />
              <Pagination total={p.total} limit={PAGE} offset={offset} onChange={setOffset} />
            </>
          )}
        </QueryView>
      </Panel>
      <div className="grid cols-2">
        <Panel title="Task history">
          {!selected ? (
            <p className="muted small">Select a task.</p>
          ) : (
            <QueryView
              query={history}
              isEmpty={(h) => h.length === 0}
              empty={<EmptyState title="No history recorded" />}
            >
              {(h) => (
                <ul className="timeline">
                  {h.map((e, i) => (
                    <li key={i}>
                      <span className="t">{formatSimTime(e.sim_time_ms)}</span>
                      <div>
                        <StatusBadge status={e.state} tone="info" />{" "}
                        <span className="xs muted">
                          {e.source} · {e.reason}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </QueryView>
          )}
        </Panel>
        <Panel title="Sectors (public configuration)">
          <QueryView
            query={sectors}
            isEmpty={(s) => s.length === 0}
            empty={
              <EmptyState title="No sectors">This coordination policy does not assign sectors.</EmptyState>
            }
          >
            {(s) => <Kv items={s.map((x) => [x.member, `${x.cells.length} cells`])} />}
          </QueryView>
        </Panel>
      </div>
      <Panel title="Coordination conflicts">
        <QueryView
          query={conflicts}
          isEmpty={(c) => c.length === 0}
          empty={<EmptyState title="No conflicts recorded" />}
        >
          {(c) => (
            <DataTable
              caption="Coordination conflicts"
              rows={c
                .slice(-200)
                .reverse()
                .map((x, i) => ({ ...x, key: `${i}` }))}
              columns={conflictCols}
              rowKey={(x) => `${x.key}-${x.sim_time_ms}-${x.message_id ?? x.reason}`}
            />
          )}
        </QueryView>
      </Panel>
    </div>
  );
}
