import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import type { Alert, Decision, ReviewItem } from "../../contracts/api";
import { ConfirmDialog } from "../../components/ui/dialogs";
import { DataTable, Pagination, SelectField, Tabs, TextField, type Column } from "../../components/ui/data";
import { Button, Kv, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { AlertBox, EmptyState, QueryView } from "../../components/ui/states";
import {
  useLiveInterval,
  useMission,
  useMissionMutation,
  useMissionPermissions,
  useMissionQuery,
  useMode,
} from "../../hooks/data";
import { formatDuration, formatLocation, formatSimTime, formatWallTime, shortId } from "../../lib/format";
import { newIdempotencyKey } from "../../lib/idempotency";
import { deniedReason } from "../../lib/permissions";
import { statusLabel } from "../../lib/status";
import { asApiError } from "../../services/api/errors";
import { usePreferences } from "../../stores/preferences";
import { DecisionDialog, type DecisionTarget, type RecommendationAction } from "./DecisionDialog";

type Tab = "queue" | "alerts" | "decisions" | "override";
const PAGE = 50;

export default function ReviewPage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const live = useLiveInterval();
  const perms = useMissionPermissions(missionId);
  const mission = useMission(missionId);
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab | null) ?? "queue";
  const [dialog, setDialog] = useState<DecisionTarget | null>(null);
  const [alertOffset, setAlertOffset] = useState(0);
  const [decisionOffset, setDecisionOffset] = useState(0);
  const [unackOnly, setUnackOnly] = useState("true");
  const timeDisplay = usePreferences((s) => s.timeDisplay);
  const queue = useMissionQuery(missionId, ["review"], (p, id, s) => p.reviewQueue(id, s), {
    refetchInterval: live,
  });
  const alerts = useMissionQuery(
    missionId,
    ["alerts", unackOnly, alertOffset],
    (p, id, s) => p.alerts(id, { unacknowledged: unackOnly === "true", limit: PAGE, offset: alertOffset }, s),
    { enabled: tab === "alerts", refetchInterval: live },
  );
  const decisions = useMissionQuery(
    missionId,
    ["decisions", decisionOffset],
    (p, id, s) => p.decisions(id, { limit: PAGE, offset: decisionOffset }, s),
    { enabled: tab === "decisions", refetchInterval: live },
  );
  const ack = useMissionMutation(missionId, (p, alertId: string) =>
    p.acknowledgeAlert(alertId, "seen in dashboard"),
  );
  const base = `/missions/${missionId}`;
  const open = (item: ReviewItem, action: RecommendationAction) =>
    setDialog({
      kind: "recommendation",
      action,
      recommendation: item.recommendation,
      incident: item.incident,
    });
  const canDecide = perms.has("recommendation.decide");

  const alertCols: Column<Alert>[] = [
    { key: "t", header: "Sent", cell: (a) => <span className="mono">{formatSimTime(a.sent_sim_ms)}</span> },
    { key: "p", header: "Priority", cell: (a) => <StatusBadge status={a.priority} /> },
    { key: "r", header: "Reason", cell: (a) => a.priority_reason },
    {
      key: "i",
      header: "Incident",
      cell: (a) => (
        <Link to={`${base}/incidents/${a.incident_id}`}>
          {shortId(a.incident_id)} r{a.incident_revision}
        </Link>
      ),
    },
    { key: "s", header: "Review state", cell: (a) => <StatusBadge status={a.review_state} /> },
    { key: "e", header: "Evidence", cell: (a) => a.supporting_evidence.length },
    {
      key: "a",
      header: "Acknowledged",
      cell: (a) =>
        a.acknowledged_at ? (
          formatWallTime(a.acknowledged_at, timeDisplay)
        ) : (
          <Button
            size="sm"
            disabled={!perms.has("alert.acknowledge") || ack.isPending}
            title={
              !perms.has("alert.acknowledge")
                ? deniedReason("alert.acknowledge")
                : "Records that you saw this alert; does not change the incident"
            }
            onClick={() => ack.mutate(a.id)}
          >
            Acknowledge
          </Button>
        ),
    },
  ];
  const decisionCols: Column<Decision>[] = [
    {
      key: "t",
      header: "Submitted",
      cell: (d) => `${formatSimTime(d.sim_time_ms)} · ${formatWallTime(d.submitted_at, timeDisplay)}`,
    },
    { key: "k", header: "Kind", cell: (d) => statusLabel(d.kind) },
    { key: "a", header: "Action", cell: (d) => statusLabel(d.action) },
    {
      key: "r",
      header: "Resource",
      cell: (d) =>
        d.recommendation_id ? (
          <Link to={`${base}/recommendations/${d.recommendation_id}`}>
            rec {shortId(d.recommendation_id)}
          </Link>
        ) : d.incident_id ? (
          <Link to={`${base}/incidents/${d.incident_id}`}>incident {shortId(d.incident_id)}</Link>
        ) : (
          "mission"
        ),
    },
    {
      key: "v",
      header: "Version",
      cell: (d) => (d.expected_revision === null ? "—" : `v${d.expected_revision}`),
    },
    { key: "by", header: "Role", cell: (d) => d.actor_role },
    { key: "s", header: "Model 2 outcome", cell: (d) => <StatusBadge status={d.status} /> },
    {
      key: "o",
      header: "Reason / outcome",
      cell: (d) => `${d.reason}${d.outcome_reason ? ` · ${d.outcome_reason}` : ""}`,
    },
  ];

  return (
    <div className="stack">
      <PageHeader
        title="Human review"
        description="Recommendations awaiting a human decision, operator alerts and the decision record. Decisions are validated by Model 2 before they take effect."
        actions={<SourceTag synthetic={synthetic} />}
      />
      {mission.data?.status === "running" && (queue.data?.length ?? 0) > 0 && (
        <AlertBox tone="info" title="Deadlines run on simulation time.">
          Pause the mission (overview) if reviewers need more time. Recommendations do not expire while
          paused; decisions submitted while paused are validated when it resumes.
        </AlertBox>
      )}
      {!canDecide && (
        <AlertBox tone="info">
          Your mission role can view reviews but cannot approve or reject recommendations. Operators can
          acknowledge incidents and alerts and submit feedback from the incident page.
        </AlertBox>
      )}
      <Tabs<Tab>
        label="Review sections"
        active={tab}
        onChange={(t) => setParams({ tab: t }, { replace: true })}
        tabs={[
          { key: "queue", label: `Review queue (${queue.data?.length ?? 0})` },
          { key: "alerts", label: "Operator alerts" },
          { key: "decisions", label: "Decision history" },
          { key: "override", label: "Simulated overrides" },
        ]}
      />
      {tab === "queue" && (
        <QueryView
          query={queue}
          rows={6}
          isEmpty={(q) => q.length === 0}
          empty={
            <Panel>
              <EmptyState title="Nothing awaiting review">Model 2 has no pending recommendations.</EmptyState>
            </Panel>
          }
        >
          {(items) => (
            <div className="stack">
              {items.map((item) => (
                <Panel
                  key={item.recommendation.id}
                  title={
                    <>
                      {statusLabel(item.recommendation.request)} · v{item.recommendation.version}
                    </>
                  }
                  actions={
                    <>
                      <StatusBadge status={item.incident.priority_level} />
                      <span className="xs muted">{formatDuration(item.remaining_ms)} left (sim)</span>
                    </>
                  }
                >
                  <div className="grid cols-2">
                    <Kv
                      items={[
                        [
                          "Recommendation",
                          <Link key="r" to={`${base}/recommendations/${item.recommendation.id}`}>
                            {shortId(item.recommendation.id)} v{item.recommendation.version}
                          </Link>,
                        ],
                        [
                          "Incident",
                          <Link key="i" to={`${base}/incidents/${item.incident.id}`}>
                            {statusLabel(item.incident.category)} · r{item.incident.revision}
                          </Link>,
                        ],
                        ["Estimated location", formatLocation(item.incident.location)],
                        [
                          "Evidence",
                          `${item.recommendation.evidence_ids.length} items · ${item.incident.supporting_observations} supporting / ${item.incident.conflicting_observations} conflicting`,
                        ],
                      ]}
                    />
                    <Kv
                      items={[
                        [
                          "Model 2 urgency",
                          item.incident.priority_level
                            ? statusLabel(item.incident.priority_level)
                            : "not assessed",
                        ],
                        ["Rationale", item.incident.priority_reason ?? "—"],
                        ["Uncertainty", item.recommendation.unknowns.join("; ") || "none listed"],
                        ["Evidence age", formatDuration(item.incident.freshness_ms)],
                      ]}
                    />
                  </div>
                  {item.incident.conflicting_observations > 0 && (
                    <AlertBox tone="warn">
                      Conflicting evidence: {item.incident.conflicting_observations} report(s) contradict this
                      assessment.
                    </AlertBox>
                  )}
                  <div className="row" style={{ marginTop: 10 }}>
                    <Button
                      variant="ok"
                      disabled={!canDecide}
                      title={!canDecide ? deniedReason("recommendation.decide") : undefined}
                      onClick={() => open(item, "approve")}
                    >
                      Approve review
                    </Button>
                    <Button variant="bad" disabled={!canDecide} onClick={() => open(item, "reject")}>
                      Reject
                    </Button>
                    <Button
                      variant="warn"
                      disabled={!canDecide}
                      onClick={() => open(item, "request-revision")}
                    >
                      Request revision
                    </Button>
                    <Link to={`${base}/evidence?incident=${item.incident.id}`}>Inspect evidence</Link>
                  </div>
                </Panel>
              ))}
            </div>
          )}
        </QueryView>
      )}
      {tab === "alerts" && (
        <Panel
          title="Operator alerts (backend)"
          actions={
            <SelectField
              label="Show"
              value={unackOnly}
              onChange={(v) => {
                setUnackOnly(v);
                setAlertOffset(0);
              }}
              options={[
                { value: "true", label: "Unacknowledged" },
                { value: "false", label: "All" },
              ]}
            />
          }
        >
          {ack.isError && <AlertBox tone="bad">{asApiError(ack.error).userMessage}</AlertBox>}
          <QueryView
            query={alerts}
            isEmpty={(p) => p.items.length === 0}
            empty={<EmptyState title="No alerts" />}
          >
            {(p) => (
              <>
                <DataTable
                  caption="Operator alerts"
                  rows={p.items}
                  columns={alertCols}
                  rowKey={(a) => a.id}
                />
                <Pagination total={p.total} limit={PAGE} offset={alertOffset} onChange={setAlertOffset} />
              </>
            )}
          </QueryView>
        </Panel>
      )}
      {tab === "decisions" && (
        <Panel title="Persisted human decisions">
          <QueryView
            query={decisions}
            isEmpty={(p) => p.items.length === 0}
            empty={<EmptyState title="No decisions recorded" />}
          >
            {(p) => (
              <>
                <DataTable
                  caption="Human decisions"
                  rows={p.items}
                  columns={decisionCols}
                  rowKey={(d) => d.id}
                />
                <Pagination
                  total={p.total}
                  limit={PAGE}
                  offset={decisionOffset}
                  onChange={setDecisionOffset}
                />
              </>
            )}
          </QueryView>
        </Panel>
      )}
      {tab === "override" && <OverridePanel missionId={missionId!} allowed={perms.has("mission.override")} />}
      {dialog && <DecisionDialog missionId={missionId!} target={dialog} onClose={() => setDialog(null)} />}
    </div>
  );
}

function OverridePanel({ missionId, allowed }: { missionId: string; allowed: boolean }) {
  const [action, setAction] = useState<"pause" | "resume" | "end">("pause");
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(() => newIdempotencyKey());
  const mutation = useMissionMutation(
    missionId,
    (p, v: { action: "pause" | "resume" | "end"; reason: string }) =>
      p.override(missionId, { ...v, idempotency_key: key }),
  );
  return (
    <Panel title="Simulated assignment override">
      <p className="small">
        Sends a revision-bound override (pause, resume or end task assignments) to Model 2 coordination. This
        is separate from simulation lifecycle control and never commands a physical drone. Model 2 validates
        it.
      </p>
      <div className="filters" style={{ marginTop: 8 }}>
        <SelectField
          label="Override"
          value={action}
          onChange={(v) => setAction(v as typeof action)}
          options={["pause", "resume", "end"]}
        />
        <TextField label="Reason" value={reason} onChange={setReason} maxLength={100} />
        <Button
          variant="warn"
          disabled={!allowed || !reason.trim()}
          title={!allowed ? deniedReason("mission.override") : undefined}
          onClick={() => setOpen(true)}
        >
          Submit override…
        </Button>
      </div>
      {mutation.data && (
        <AlertBox tone="info">
          Override {mutation.data.action} submitted · status <StatusBadge status={mutation.data.status} />{" "}
          (Model 2 validates it).
        </AlertBox>
      )}
      <ConfirmDialog
        open={open}
        title={`Submit simulated override “${action}”?`}
        confirmLabel="Submit override"
        tone="warn"
        busy={mutation.isPending}
        onCancel={() => setOpen(false)}
        onConfirm={() =>
          mutation.mutate(
            { action, reason: reason.trim() },
            {
              onSuccess: () => {
                setOpen(false);
                setKey(newIdempotencyKey());
              },
            },
          )
        }
      >
        <p>
          Model 2 coordination will receive a human override to {action} task assignments for this mission.
        </p>
        {mutation.isError && <AlertBox tone="bad">{asApiError(mutation.error).userMessage}</AlertBox>}
      </ConfirmDialog>
    </Panel>
  );
}
