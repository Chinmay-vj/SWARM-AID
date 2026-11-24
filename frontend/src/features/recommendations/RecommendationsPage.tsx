import { useMemo } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { Recommendation } from "../../contracts/api";
import { DataTable, Pagination, SelectField, type Column } from "../../components/ui/data";
import { PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { EmptyState, QueryView } from "../../components/ui/states";
import { useLiveInterval, useMission, useMissionQuery, useMode } from "../../hooks/data";
import { formatDuration, formatSimTime, shortId } from "../../lib/format";
import { statusLabel } from "../../lib/status";

const PAGE = 50;
export const REC_STATUSES = [
  "pending",
  "approved",
  "confirmed",
  "rejected",
  "revision_requested",
  "superseded",
  "expired",
];

export default function RecommendationsPage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const navigate = useNavigate();
  const live = useLiveInterval();
  const mission = useMission(missionId);
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const offset = Number(params.get("offset") ?? 0);
  const list = useMissionQuery(
    missionId,
    ["recommendations", status, offset],
    (p, id, s) => p.recommendations(id, { status: status || undefined, limit: PAGE, offset }, s),
    { refetchInterval: live },
  );
  const base = `/missions/${missionId}`;
  const now = mission.data?.last_sim_ms ?? 0;
  const columns = useMemo<Column<Recommendation>[]>(
    () => [
      {
        key: "id",
        header: "Recommendation",
        cell: (r) => <Link to={`${base}/recommendations/${r.id}`}>{shortId(r.id)}</Link>,
      },
      { key: "v", header: "Version", cell: (r) => `v${r.version}`, sort: (r) => r.version },
      { key: "req", header: "Request", cell: (r) => statusLabel(r.request), sort: (r) => r.request },
      { key: "st", header: "Status", cell: (r) => <StatusBadge status={r.status} />, sort: (r) => r.status },
      {
        key: "inc",
        header: "Incident",
        cell: (r) => <Link to={`${base}/incidents/${r.incident_id}`}>{shortId(r.incident_id)}</Link>,
      },
      {
        key: "ev",
        header: "Evidence",
        cell: (r) => r.evidence_ids.length,
        sort: (r) => r.evidence_ids.length,
      },
      {
        key: "cr",
        header: "Created",
        cell: (r) => <span className="mono">{formatSimTime(r.created_sim_ms)}</span>,
        sort: (r) => r.created_sim_ms,
      },
      {
        key: "exp",
        header: "Review deadline",
        cell: (r) =>
          r.status === "pending"
            ? `${formatDuration(Math.max(0, r.expires_ms - now))} left`
            : formatSimTime(r.expires_ms),
        sort: (r) => r.expires_ms,
      },
    ],
    [base, now],
  );
  return (
    <div className="stack">
      <PageHeader
        title="Recommendation center"
        description="Model 2 decision-support recommendations. Each version is bound to an incident revision. Recommendations are not verified real-world rescue instructions."
        actions={<SourceTag synthetic={synthetic} />}
      />
      <Panel title="Recommendations">
        <div className="filters" style={{ marginBottom: 8 }}>
          <SelectField
            label="Status"
            value={status}
            onChange={(v) => {
              const next = new URLSearchParams();
              if (v) next.set("status", v);
              setParams(next, { replace: true });
            }}
            options={[
              { value: "", label: "All" },
              ...REC_STATUSES.map((s) => ({ value: s, label: statusLabel(s) })),
            ]}
          />
        </div>
        <QueryView
          query={list}
          rows={8}
          isEmpty={(p) => p.items.length === 0}
          empty={<EmptyState title="No recommendations" />}
        >
          {(p) => (
            <>
              <DataTable
                caption="Recommendations"
                rows={p.items}
                columns={columns}
                rowKey={(r) => r.id}
                onSelect={(r) => navigate(`${base}/recommendations/${r.id}`)}
              />
              <Pagination
                total={p.total}
                limit={PAGE}
                offset={offset}
                onChange={(o) => {
                  const next = new URLSearchParams(params);
                  next.set("offset", String(o));
                  setParams(next, { replace: true });
                }}
              />
            </>
          )}
        </QueryView>
      </Panel>
    </div>
  );
}
