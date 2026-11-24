import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { IncidentRevision, IncidentTransition, Observation } from "../../contracts/api";
import { DataTable, Tabs, type Column } from "../../components/ui/data";
import { Button, Kv, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { AlertBox, EmptyState, QueryView } from "../../components/ui/states";
import { useLiveInterval, useMissionPermissions, useMissionQuery, useMode } from "../../hooks/data";
import {
  formatConfidence,
  formatDuration,
  formatLocation,
  formatSimTime,
  humanize,
  shortId,
} from "../../lib/format";
import { deniedReason, type Permission } from "../../lib/permissions";
import { statusLabel } from "../../lib/status";
import { DecisionDialog, type DecisionTarget, type IncidentDecision } from "../oversight/DecisionDialog";

type Tab = "summary" | "evidence" | "assessments" | "recommendations" | "timeline";

const ACTIONS: {
  action: IncidentDecision;
  label: string;
  permission: Permission;
  variant: "ok" | "warn" | "primary" | "bad";
}[] = [
  { action: "acknowledge", label: "Acknowledge review", permission: "incident.acknowledge", variant: "ok" },
  {
    action: "request-review",
    label: "Request priority review",
    permission: "incident.request_review",
    variant: "primary",
  },
  {
    action: "correct",
    label: "Request clarification / correct",
    permission: "feedback.correct",
    variant: "warn",
  },
  {
    action: "resolution-report",
    label: "Simulated resolution report",
    permission: "incident.resolution_report",
    variant: "primary",
  },
  { action: "close", label: "Close", permission: "incident.close", variant: "bad" },
];

export default function IncidentDetailPage() {
  const { missionId, incidentId } = useParams();
  const synthetic = useMode() === "synthetic";
  const live = useLiveInterval();
  const perms = useMissionPermissions(missionId);
  const [tab, setTab] = useState<Tab>("summary");
  const [dialog, setDialog] = useState<DecisionTarget | null>(null);
  const incident = useMissionQuery(
    missionId,
    ["incident", incidentId],
    (p, _id, s) => p.incident(incidentId!, s),
    { refetchInterval: live },
  );
  const group = useMissionQuery(
    missionId,
    ["incident", incidentId, "group"],
    (p, _id, s) => p.evidenceGroup(incidentId!, s),
    { refetchInterval: live },
  );
  const assessments = useMissionQuery(
    missionId,
    ["incident", incidentId, "assessments"],
    (p, _id, s) => p.incidentAssessments(incidentId!, s),
    { refetchInterval: live },
  );
  const history = useMissionQuery(
    missionId,
    ["incident", incidentId, "history"],
    (p, _id, s) => p.incidentHistory(incidentId!, s),
    { refetchInterval: live },
  );
  const recs = useMissionQuery(
    missionId,
    ["recommendations", "for-incident", incidentId],
    (p, id, s) => p.recommendations(id, { limit: 200 }, s),
    { refetchInterval: live },
  );
  const decisions = useMissionQuery(
    missionId,
    ["decisions", "for-incident"],
    (p, id, s) => p.decisions(id, { limit: 200 }, s),
    { enabled: tab === "timeline" || tab === "summary" },
  );
  const base = `/missions/${missionId}`;
  const incidentRecs = useMemo(
    () =>
      (recs.data?.items ?? [])
        .filter((r) => r.incident_id === incidentId)
        .sort((a, b) => b.version - a.version),
    [recs.data, incidentId],
  );
  const incidentDecisions = (decisions.data?.items ?? []).filter((d) => d.incident_id === incidentId);

  const obsCols: Column<Observation>[] = [
    {
      key: "t",
      header: "Observed",
      cell: (o) => <span className="mono">{formatSimTime(o.observed_ms)}</span>,
      sort: (o) => o.observed_ms,
    },
    { key: "r", header: "Agent", cell: (o) => o.reporter, sort: (o) => o.reporter },
    { key: "k", header: "Kind", cell: (o) => `${humanize(o.kind)}${o.label ? ` · ${o.label}` : ""}` },
    {
      key: "c",
      header: "Confidence",
      cell: (o) => formatConfidence(o.confidence),
      sort: (o) => o.confidence,
    },
    { key: "l", header: "Location", cell: (o) => formatLocation(o.location) },
    { key: "f", header: "Freshness", cell: (o) => <StatusBadge status={o.stale ? "stale" : "fresh"} /> },
    {
      key: "e",
      header: "Evidence",
      cell: (o) => <Link to={`${base}/evidence?observation=${o.id}`}>view</Link>,
    },
  ];
  const revCols: Column<IncidentRevision>[] = [
    { key: "r", header: "Rev.", cell: (r) => r.revision },
    {
      key: "t",
      header: "Sim time",
      cell: (r) => <span className="mono">{formatSimTime(r.sim_time_ms)}</span>,
    },
    { key: "c", header: "Category", cell: (r) => humanize(r.category) },
    { key: "p", header: "Urgency", cell: (r) => <StatusBadge status={r.priority_level} /> },
    { key: "pr", header: "Model 2 reason", cell: (r) => r.priority_reason ?? "—" },
    { key: "n", header: "Reports", cell: (r) => r.report_message_ids.length },
    { key: "u", header: "Uncertainty", cell: (r) => r.uncertainties.join("; ") || "—" },
  ];
  const histCols: Column<IncidentTransition>[] = [
    {
      key: "t",
      header: "Sim time",
      cell: (h) => <span className="mono">{formatSimTime(h.sim_time_ms)}</span>,
    },
    { key: "r", header: "Rev.", cell: (h) => h.revision },
    {
      key: "s",
      header: "Transition",
      cell: (h) => (
        <span>
          {statusLabel(h.previous)} → <StatusBadge status={h.state} />
        </span>
      ),
    },
    { key: "a", header: "Actor", cell: (h) => h.actor },
    { key: "ref", header: "Reference", cell: (h) => <code>{shortId(h.reference)}</code> },
  ];

  return (
    <QueryView query={incident} rows={6}>
      {(i) => (
        <div className="stack">
          <PageHeader
            title={`${statusLabel(i.category)} incident ${shortId(i.id)}`}
            description={`Revision ${i.revision} · opened ${formatSimTime(i.opened_sim_ms)} · updated ${formatSimTime(i.updated_sim_ms)}`}
            actions={
              <>
                <SourceTag synthetic={synthetic} />
                <Link to={`${base}/incidents`}>All incidents</Link>
              </>
            }
          />
          {i.category === "possible_human" && (
            <AlertBox tone="info">
              Possible human presence reported by agents. Not confirmed. Not a rescue outcome.
            </AlertBox>
          )}
          <Panel title="Actions">
            <div className="row">
              {ACTIONS.map((a) => {
                const allowed = perms.has(a.permission);
                const unavailable =
                  (a.action === "close" && i.disposition !== "resolution_reported") ||
                  i.disposition === "closed" ||
                  (a.action === "acknowledge" && i.disposition !== "human_review_pending");
                return (
                  <Button
                    key={a.action}
                    variant={a.variant}
                    disabled={!allowed || unavailable}
                    title={
                      !allowed
                        ? deniedReason(a.permission)
                        : unavailable
                          ? "Not valid in the current lifecycle state"
                          : undefined
                    }
                    onClick={() => setDialog({ kind: "incident", action: a.action, incident: i })}
                  >
                    {a.label}
                  </Button>
                );
              })}
            </div>
            <p className="xs muted" style={{ marginTop: 6 }}>
              Actions are bound to revision r{i.revision}. The backend and Model 2 re-validate each one;
              buttons you cannot use are disabled and the backend still enforces permissions.
            </p>
          </Panel>
          <Tabs<Tab>
            label="Incident sections"
            active={tab}
            onChange={setTab}
            tabs={[
              { key: "summary", label: "Summary" },
              { key: "evidence", label: `Evidence (${(group.data?.observations.length ?? 0).toString()})` },
              { key: "assessments", label: "Model 2 assessments" },
              { key: "recommendations", label: `Recommendations (${incidentRecs.length})` },
              { key: "timeline", label: "Timeline & reviews" },
            ]}
          />
          {tab === "summary" && (
            <div className="grid cols-2">
              <Panel title="Current assessment">
                <Kv
                  items={[
                    ["Lifecycle", <StatusBadge key="d" status={i.disposition} />],
                    [
                      "Urgency (Model 2)",
                      i.priority_level ? <StatusBadge key="p" status={i.priority_level} /> : "not assessed",
                    ],
                    ["Urgency reason", i.priority_reason ?? "—"],
                    ["Operator flag", i.operator_priority ?? "none"],
                    ["Estimated location", formatLocation(i.location)],
                    ["Supporting observations", i.supporting_observations],
                    ["Conflicting observations", i.conflicting_observations],
                    [
                      "Independent source agents",
                      group.data
                        ? `${group.data.distinct_reporters.length} (${group.data.distinct_reporters.join(", ")})`
                        : "—",
                    ],
                    ["Evidence age", formatDuration(i.freshness_ms)],
                    [
                      "Current recommendation",
                      i.current_recommendation_id ? (
                        <Link key="r" to={`${base}/recommendations/${i.current_recommendation_id}`}>
                          {shortId(i.current_recommendation_id)}
                        </Link>
                      ) : (
                        "none"
                      ),
                    ],
                  ]}
                />
              </Panel>
              <Panel title="Human review status">
                {incidentDecisions.length === 0 ? (
                  <EmptyState title="No human decisions recorded for this incident" />
                ) : (
                  <ul className="timeline">
                    {incidentDecisions.map((d) => (
                      <li key={d.id}>
                        <span className="t">{formatSimTime(d.sim_time_ms)}</span>
                        <div>
                          {statusLabel(d.action)} (r{d.expected_revision ?? "?"}) by {d.actor_role} ·{" "}
                          <StatusBadge status={d.status} />
                          <div className="xs muted">
                            {d.reason}
                            {d.outcome_reason ? ` · ${d.outcome_reason}` : ""}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </div>
          )}
          {tab === "evidence" && (
            <Panel
              title="Evidence group (supporting and contradictory reports)"
              actions={<Link to={`${base}/evidence?incident=${i.id}`}>Open in evidence center</Link>}
            >
              <QueryView query={group} isEmpty={(g) => g.observations.length === 0}>
                {(g) => (
                  <>
                    <p className="small muted" style={{ marginBottom: 6 }}>
                      {g.observations.length} reports from {g.distinct_reporters.length} independent agent(s).
                      Model 2 counts {i.supporting_observations} as supporting and{" "}
                      {i.conflicting_observations} as conflicting.
                    </p>
                    <DataTable
                      caption="Evidence group observations"
                      rows={g.observations}
                      columns={obsCols}
                      rowKey={(o) => o.id}
                      initialSort={{ key: "t", dir: "desc" }}
                    />
                  </>
                )}
              </QueryView>
            </Panel>
          )}
          {tab === "assessments" && (
            <Panel title="Model 2 assessment history">
              <QueryView query={assessments} isEmpty={(a) => a.length === 0}>
                {(a) => (
                  <DataTable
                    caption="Assessment revisions"
                    rows={[...a].reverse()}
                    columns={revCols}
                    rowKey={(r) => String(r.revision)}
                  />
                )}
              </QueryView>
              <p className="xs muted" style={{ marginTop: 6 }}>
                Only structured fields exposed by the backend are shown. Model 2's internal reasoning is not
                reconstructed.
              </p>
            </Panel>
          )}
          {tab === "recommendations" && (
            <Panel title="Recommendation versions">
              {incidentRecs.length === 0 ? (
                <EmptyState title="No recommendations" />
              ) : (
                <div className="stack tight">
                  {incidentRecs.map((r) => (
                    <div key={r.id} className="row between">
                      <Link to={`${base}/recommendations/${r.id}`}>
                        v{r.version} · {statusLabel(r.request)}
                      </Link>
                      <span className="row" style={{ gap: 4 }}>
                        <StatusBadge status={r.status} />
                        <span className="xs muted">
                          created {formatSimTime(r.created_sim_ms)} · expires {formatSimTime(r.expires_ms)}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          )}
          {tab === "timeline" && (
            <Panel title="Lifecycle transitions">
              <QueryView query={history} isEmpty={(h) => h.length === 0}>
                {(h) => (
                  <DataTable
                    caption="Incident transitions"
                    rows={[...h].reverse()}
                    columns={histCols}
                    rowKey={(x) => `${x.revision}-${x.state}-${x.reference}`}
                  />
                )}
              </QueryView>
            </Panel>
          )}
          {dialog && (
            <DecisionDialog missionId={missionId!} target={dialog} onClose={() => setDialog(null)} />
          )}
        </div>
      )}
    </QueryView>
  );
}
