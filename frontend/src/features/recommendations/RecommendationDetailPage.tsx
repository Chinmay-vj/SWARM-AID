import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Recommendation } from "../../contracts/api";
import { SelectField } from "../../components/ui/data";
import { Button, Kv, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { AlertBox, EmptyState, QueryView } from "../../components/ui/states";
import {
  useLiveInterval,
  useMission,
  useMissionPermissions,
  useMissionQuery,
  useMode,
} from "../../hooks/data";
import { formatDuration, formatLocation, formatSimTime, shortId } from "../../lib/format";
import { deniedReason } from "../../lib/permissions";
import { statusLabel } from "../../lib/status";
import { DecisionDialog, type DecisionTarget, type RecommendationAction } from "../oversight/DecisionDialog";

/** Field-by-field comparison of two recommendation versions. */
export function diffRecommendations(a: Recommendation, b: Recommendation) {
  const evA = new Set(a.evidence_ids);
  const evB = new Set(b.evidence_ids);
  return {
    request: a.request === b.request ? null : { from: a.request, to: b.request },
    status: a.status === b.status ? null : { from: a.status, to: b.status },
    added: b.evidence_ids.filter((e) => !evA.has(e)),
    removed: a.evidence_ids.filter((e) => !evB.has(e)),
    unknownsAdded: b.unknowns.filter((u) => !a.unknowns.includes(u)),
    unknownsRemoved: a.unknowns.filter((u) => !b.unknowns.includes(u)),
  };
}

export default function RecommendationDetailPage() {
  const { missionId, recId } = useParams();
  const synthetic = useMode() === "synthetic";
  const live = useLiveInterval();
  const perms = useMissionPermissions(missionId);
  const mission = useMission(missionId);
  const rec = useMissionQuery(
    missionId,
    ["recommendation", recId],
    (p, _id, s) => p.recommendation(recId!, s),
    { refetchInterval: live },
  );
  const versions = useMissionQuery(
    missionId,
    ["recommendation", recId, "versions"],
    (p, _id, s) => p.recommendationVersions(recId!, s),
    { refetchInterval: live },
  );
  const history = useMissionQuery(
    missionId,
    ["recommendation", recId, "history"],
    (p, _id, s) => p.recommendationHistory(recId!, s),
    { refetchInterval: live },
  );
  const evidence = useMissionQuery(missionId, ["recommendation", recId, "evidence"], (p, _id, s) =>
    p.recommendationEvidence(recId!, s),
  );
  const incident = useMissionQuery(
    missionId,
    ["incident", rec.data?.incident_id],
    (p, _id, s) => p.incident(rec.data!.incident_id, s),
    { enabled: Boolean(rec.data), refetchInterval: live },
  );
  const decisions = useMissionQuery(
    missionId,
    ["decisions", "for-rec"],
    (p, id, s) => p.decisions(id, { limit: 200 }, s),
    { refetchInterval: live },
  );
  const [dialog, setDialog] = useState<DecisionTarget | null>(null);
  const [compareWith, setCompareWith] = useState("");
  const base = `/missions/${missionId}`;
  const now = mission.data?.last_sim_ms ?? 0;

  return (
    <QueryView query={rec} rows={6}>
      {(r) => {
        const inc = incident.data;
        const latest = versions.data?.reduce((a, b) => (b.version > a.version ? b : a), r);
        const outdated = (latest && latest.version > r.version) || (inc && inc.revision !== r.version);
        const pending = r.status === "pending";
        const other = versions.data?.find((v) => v.id === compareWith);
        const diff = other
          ? other.version < r.version
            ? diffRecommendations(other, r)
            : diffRecommendations(r, other)
          : null;
        const open = (action: RecommendationAction) =>
          setDialog({ kind: "recommendation", action, recommendation: r, incident: inc ?? null });
        const recDecisions = (decisions.data?.items ?? []).filter((d) => d.recommendation_id === r.id);
        return (
          <div className="stack">
            <PageHeader
              title={`Recommendation ${shortId(r.id)} · v${r.version}`}
              description={`${statusLabel(r.request)} for incident ${shortId(r.incident_id)}`}
              actions={
                <>
                  <SourceTag synthetic={synthetic} />
                  <Link to={`${base}/recommendations`}>All recommendations</Link>
                </>
              }
            />
            {outdated && (
              <AlertBox tone="warn" title="Newer version available.">
                Model 2 has revised this incident. Decisions on this version will be rejected as stale.{" "}
                {latest && latest.id !== r.id && (
                  <Link to={`${base}/recommendations/${latest.id}`}>Open v{latest.version}</Link>
                )}
              </AlertBox>
            )}
            {pending && mission.data?.status === "running" && (
              <AlertBox tone="info">
                The review deadline advances with simulation time (
                {formatDuration(Math.max(0, r.expires_ms - now))} left). Pausing the mission stops the clock.
              </AlertBox>
            )}
            <div className="grid main-side">
              <Panel title="Recommendation">
                <Kv
                  items={[
                    ["ID", <code key="i">{r.id}</code>],
                    ["Version", `v${r.version} (incident revision)`],
                    ["Request", statusLabel(r.request)],
                    ["Status", <StatusBadge key="s" status={r.status} />],
                    ["Human review required", "Yes — every recommendation requires a human decision"],
                    [
                      "Created",
                      `${formatSimTime(r.created_sim_ms)} (sim) · ${new Date(r.created_at).toLocaleString()}`,
                    ],
                    [
                      "Review deadline",
                      `${formatSimTime(r.expires_ms)}${pending ? ` · ${formatDuration(Math.max(0, r.expires_ms - now))} left` : ""}`,
                    ],
                    ["Unknowns / assumptions", r.unknowns.length ? r.unknowns.join("; ") : "none listed"],
                    [
                      "Constraints",
                      "Simulation decision support only; no physical drone control; Model 1 safety gates unaffected",
                    ],
                    ["Supporting evidence", `${r.evidence_ids.length} evidence item(s)`],
                    [
                      "Incident",
                      inc ? (
                        <Link key="inc" to={`${base}/incidents/${inc.id}`}>
                          {statusLabel(inc.category)} r{inc.revision} · {statusLabel(inc.disposition)}
                        </Link>
                      ) : (
                        shortId(r.incident_id)
                      ),
                    ],
                    [
                      "Incident evidence balance",
                      inc
                        ? `${inc.supporting_observations} supporting · ${inc.conflicting_observations} conflicting`
                        : "—",
                    ],
                    ["Estimated location", inc ? formatLocation(inc.location) : "—"],
                    [
                      "Model 2 urgency",
                      inc?.priority_level ? <StatusBadge key="p" status={inc.priority_level} /> : "—",
                    ],
                    ["Urgency rationale", inc?.priority_reason ?? "—"],
                  ]}
                />
              </Panel>
              <div className="stack">
                <Panel title="Human decision">
                  <div className="stack tight">
                    <Button
                      variant="ok"
                      disabled={!pending || !perms.has("recommendation.decide")}
                      title={
                        !perms.has("recommendation.decide")
                          ? deniedReason("recommendation.decide")
                          : undefined
                      }
                      onClick={() => open("approve")}
                    >
                      Approve review
                    </Button>
                    <Button
                      variant="warn"
                      disabled={
                        !pending || !perms.has("recommendation.confirm") || inc?.category === "hazard"
                      }
                      title={
                        !perms.has("recommendation.confirm")
                          ? deniedReason("recommendation.confirm")
                          : inc?.category === "hazard"
                            ? "Confirmation applies to sightings, not hazards"
                            : undefined
                      }
                      onClick={() => open("confirm")}
                    >
                      Confirm rescue need (simulated)
                    </Button>
                    <Button
                      variant="bad"
                      disabled={!pending || !perms.has("recommendation.decide")}
                      title={
                        !perms.has("recommendation.decide")
                          ? deniedReason("recommendation.decide")
                          : undefined
                      }
                      onClick={() => open("reject")}
                    >
                      Reject
                    </Button>
                    <Button
                      disabled={!pending || !perms.has("recommendation.decide")}
                      onClick={() => open("request-revision")}
                    >
                      Request revision
                    </Button>
                    {!pending && (
                      <p className="xs muted">
                        This version is {statusLabel(r.status)}; no decision can be submitted.
                      </p>
                    )}
                  </div>
                </Panel>
                <Panel title="Decision history">
                  {recDecisions.length === 0 ? (
                    <EmptyState title="No decisions on this version" />
                  ) : (
                    <ul className="timeline">
                      {recDecisions.map((d) => (
                        <li key={d.id}>
                          <span className="t">{formatSimTime(d.sim_time_ms)}</span>
                          <div>
                            {statusLabel(d.action)} · <StatusBadge status={d.status} />
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
            </div>
            <div className="grid cols-2">
              <Panel title="Version history">
                <QueryView query={versions} isEmpty={(v) => v.length === 0}>
                  {(list) => (
                    <div className="stack tight">
                      {[...list]
                        .sort((a, b) => b.version - a.version)
                        .map((v) => (
                          <div key={v.id} className="row between">
                            {v.id === r.id ? (
                              <b>v{v.version} (this)</b>
                            ) : (
                              <Link to={`${base}/recommendations/${v.id}`}>v{v.version}</Link>
                            )}
                            <span className="row" style={{ gap: 4 }}>
                              <span className="xs">{statusLabel(v.request)}</span>
                              <StatusBadge status={v.status} />
                            </span>
                          </div>
                        ))}
                      <SelectField
                        label="Compare this version with"
                        value={compareWith}
                        onChange={setCompareWith}
                        options={[
                          { value: "", label: "—" },
                          ...list
                            .filter((v) => v.id !== r.id)
                            .map((v) => ({ value: v.id, label: `v${v.version}` })),
                        ]}
                      />
                      {diff && other && (
                        <div className="small stack tight" aria-live="polite">
                          <b>
                            v{Math.min(other.version, r.version)} → v{Math.max(other.version, r.version)}
                          </b>
                          <span>
                            Request:{" "}
                            {diff.request ? (
                              <>
                                <span className="diff-del">{statusLabel(diff.request.from)}</span> →{" "}
                                <span className="diff-add">{statusLabel(diff.request.to)}</span>
                              </>
                            ) : (
                              "unchanged"
                            )}
                          </span>
                          <span>
                            Status:{" "}
                            {diff.status ? (
                              <>
                                <span className="diff-del">{statusLabel(diff.status.from)}</span> →{" "}
                                <span className="diff-add">{statusLabel(diff.status.to)}</span>
                              </>
                            ) : (
                              "unchanged"
                            )}
                          </span>
                          <span>
                            Evidence added: <span className="diff-add">{diff.added.length}</span> · removed:{" "}
                            <span className="diff-del">{diff.removed.length}</span>
                          </span>
                          {diff.unknownsAdded.length > 0 && (
                            <span>Unknowns added: {diff.unknownsAdded.join("; ")}</span>
                          )}
                          {diff.unknownsRemoved.length > 0 && (
                            <span>Unknowns removed: {diff.unknownsRemoved.join("; ")}</span>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </QueryView>
              </Panel>
              <Panel title="Status history">
                <QueryView
                  query={history}
                  isEmpty={(h) => h.length === 0}
                  empty={<EmptyState title="No status changes yet" />}
                >
                  {(h) => (
                    <ul className="timeline">
                      {h.map((x, i) => (
                        <li key={i}>
                          <span className="t">{formatSimTime(x.sim_time_ms)}</span>
                          <div>
                            {statusLabel(x.previous)} → <StatusBadge status={x.status} />
                            <div className="xs muted">{x.reason}</div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </QueryView>
              </Panel>
            </div>
            <Panel
              title="Supporting evidence"
              actions={<Link to={`${base}/evidence?incident=${r.incident_id}`}>Evidence center</Link>}
            >
              <QueryView
                query={evidence}
                isEmpty={(e) => e.length === 0}
                empty={<EmptyState title="No evidence references" />}
              >
                {(list) => (
                  <ul className="small">
                    {list.map((e) => (
                      <li key={e.evidence_id}>
                        {e.modality} from {e.origin} at {formatSimTime(e.captured_ms)} ·{" "}
                        <code>{shortId(e.evidence_id)}</code> ·{" "}
                        {e.object_id ? "stored object" : "reference only"}
                      </li>
                    ))}
                  </ul>
                )}
              </QueryView>
            </Panel>
            {dialog && (
              <DecisionDialog missionId={missionId!} target={dialog} onClose={() => setDialog(null)} />
            )}
          </div>
        );
      }}
    </QueryView>
  );
}
