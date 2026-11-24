import { useMemo } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { PRIORITY_LEVELS, type Incident } from "../../contracts/api";
import { DataTable, Pagination, SelectField, type Column } from "../../components/ui/data";
import { PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { EmptyState, QueryView } from "../../components/ui/states";
import { useLiveInterval, useMissionQuery, useMode } from "../../hooks/data";
import { formatDuration, formatLocation, formatSimTime, humanize, shortId } from "../../lib/format";

const PAGE = 50;
export const DISPOSITIONS = [
  "reported",
  "human_review_pending",
  "acknowledged",
  "confirmed",
  "rejected",
  "corrected",
  "expired",
  "resolution_reported",
  "closed",
];

export default function IncidentsPage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const navigate = useNavigate();
  const live = useLiveInterval();
  const [params, setParams] = useSearchParams();
  const disposition = params.get("disposition") ?? "";
  const category = params.get("category") ?? "";
  const priority = params.get("priority") ?? "";
  const group = params.get("group") ?? "";
  const offset = Number(params.get("offset") ?? 0);
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    if (k !== "offset") next.delete("offset");
    setParams(next, { replace: true });
  };
  const q = {
    disposition: disposition || undefined,
    category: category || undefined,
    priority: priority || undefined,
    limit: PAGE,
    offset,
  };
  const list = useMissionQuery(missionId, ["incidents", q], (p, id, s) => p.incidents(id, q, s), {
    refetchInterval: live,
  });
  const base = `/missions/${missionId}`;

  const columns = useMemo<Column<Incident>[]>(
    () => [
      {
        key: "id",
        header: "Incident",
        cell: (i) => <Link to={`${base}/incidents/${i.id}`}>{shortId(i.id)}</Link>,
      },
      { key: "cat", header: "Category", cell: (i) => humanize(i.category), sort: (i) => i.category },
      {
        key: "disp",
        header: "Lifecycle",
        cell: (i) => <StatusBadge status={i.disposition} />,
        sort: (i) => i.disposition,
      },
      {
        key: "pri",
        header: "Urgency (Model 2)",
        cell: (i) =>
          i.priority_level ? (
            <StatusBadge status={i.priority_level} />
          ) : (
            <span className="muted">not assessed</span>
          ),
        sort: (i) => PRIORITY_LEVELS.indexOf(i.priority_level as (typeof PRIORITY_LEVELS)[number]),
      },
      { key: "op", header: "Operator flag", cell: (i) => i.operator_priority ?? "—" },
      { key: "loc", header: "Estimated location", cell: (i) => formatLocation(i.location) },
      {
        key: "ev",
        header: "Evidence",
        cell: (i) => `${i.supporting_observations} supporting · ${i.conflicting_observations} conflicting`,
        sort: (i) => i.supporting_observations,
      },
      { key: "rev", header: "Rev.", cell: (i) => i.revision, sort: (i) => i.revision },
      {
        key: "upd",
        header: "Updated",
        cell: (i) => <span className="mono">{formatSimTime(i.updated_sim_ms)}</span>,
        sort: (i) => i.updated_sim_ms,
      },
      {
        key: "fresh",
        header: "Evidence age",
        cell: (i) => formatDuration(i.freshness_ms),
        sort: (i) => i.freshness_ms,
      },
    ],
    [base],
  );

  return (
    <div className="stack">
      <PageHeader
        title="Incidents"
        description="Model 2 assessments built from Model 1 reports. Urgency is Model 2's priority level; it is not the same as confidence. A possible-human incident is unverified until a human decision says otherwise."
        actions={<SourceTag synthetic={synthetic} />}
      />
      <Panel title="Filters">
        <div className="filters">
          <SelectField
            label="Lifecycle"
            value={disposition}
            onChange={(v) => set("disposition", v)}
            options={[
              { value: "", label: "All" },
              ...DISPOSITIONS.map((d) => ({ value: d, label: humanize(d) })),
            ]}
          />
          <SelectField
            label="Category"
            value={category}
            onChange={(v) => set("category", v)}
            options={["", "possible_human", "uncertain_need", "hazard", "confirmed_need"]}
          />
          <SelectField
            label="Urgency"
            value={priority}
            onChange={(v) => set("priority", v)}
            options={[
              { value: "", label: "All" },
              ...PRIORITY_LEVELS.map((p) => ({ value: p, label: humanize(p) })),
            ]}
          />
          <SelectField
            label="Group by"
            value={group}
            onChange={(v) => set("group", v)}
            options={[
              { value: "", label: "No grouping" },
              { value: "disposition", label: "Lifecycle" },
              { value: "category", label: "Category" },
              { value: "priority_level", label: "Urgency" },
            ]}
          />
        </div>
      </Panel>
      <Panel title="Incident list">
        <QueryView
          query={list}
          rows={8}
          isEmpty={(p) => p.items.length === 0}
          empty={
            <EmptyState title="No incidents">
              Model 2 has not opened any incident matching these filters.
            </EmptyState>
          }
        >
          {(p) => (
            <>
              {group ? (
                Object.entries(
                  p.items.reduce<Record<string, Incident[]>>((acc, i) => {
                    const k = String(i[group as keyof Incident] ?? "unknown");
                    (acc[k] ??= []).push(i);
                    return acc;
                  }, {}),
                ).map(([k, rows]) => (
                  <div key={k} className="stack tight" style={{ marginBottom: 12 }}>
                    <h3>
                      {humanize(k)} ({rows.length})
                    </h3>
                    <DataTable
                      caption={`Incidents: ${k}`}
                      rows={rows}
                      columns={columns}
                      rowKey={(i) => i.id}
                      onSelect={(i) => navigate(`${base}/incidents/${i.id}`)}
                    />
                  </div>
                ))
              ) : (
                <DataTable
                  caption="Incidents"
                  rows={p.items}
                  columns={columns}
                  rowKey={(i) => i.id}
                  onSelect={(i) => navigate(`${base}/incidents/${i.id}`)}
                  initialSort={{ key: "upd", dir: "desc" }}
                />
              )}
              <Pagination
                total={p.total}
                limit={PAGE}
                offset={offset}
                onChange={(o) => set("offset", String(o))}
              />
            </>
          )}
        </QueryView>
      </Panel>
    </div>
  );
}
