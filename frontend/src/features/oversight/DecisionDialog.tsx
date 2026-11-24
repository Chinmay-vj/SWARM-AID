/**
 * Consequential human decisions on recommendations and incidents.
 *
 * - Shows the exact resource identity and version being decided.
 * - Requires a reason and an explicit confirmation.
 * - One idempotency key per opened dialog; retries reuse it, so a duplicate submission returns
 *   the original decision instead of recording a second one.
 * - The UI never shows an outcome before the backend confirms it: a 202 response means
 *   "submitted"; Model 2's validator accepts or rejects it afterwards.
 * - A 409 stale_version conflict blocks submission until the updated version is reviewed.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Decision, Incident, IncidentAction, Recommendation } from "../../contracts/api";
import { ConfirmDialog } from "../../components/ui/dialogs";
import { TextField } from "../../components/ui/data";
import { Kv, StatusBadge } from "../../components/ui/primitives";
import { AlertBox } from "../../components/ui/states";
import { keys, useMissionMutation, useMode } from "../../hooks/data";
import { formatLocation, shortId } from "../../lib/format";
import { newIdempotencyKey } from "../../lib/idempotency";
import { statusLabel } from "../../lib/status";
import { asApiError } from "../../services/api/errors";

export type RecommendationAction = "approve" | "confirm" | "reject" | "request-revision";
export type IncidentDecision = IncidentAction | "correct";

export type DecisionTarget =
  | {
      kind: "recommendation";
      action: RecommendationAction;
      recommendation: Recommendation;
      incident?: Incident | null;
    }
  | { kind: "incident"; action: IncidentDecision; incident: Incident };

const DESCRIPTIONS: Record<
  string,
  { title: string; consequence: string; tone: "ok" | "bad" | "warn" | "primary" }
> = {
  approve: {
    title: "Approve review",
    consequence:
      "Records that you reviewed this recommendation version and agree further rescue-need review is warranted. It does not confirm a person, dispatch anyone, or move any drone.",
    tone: "ok",
  },
  confirm: {
    title: "Confirm rescue need (simulated)",
    consequence:
      "Records a human-confirmed rescue need for this simulated sighting. Model 2 validates whether confirmation is allowed (sightings only, not hazards). No physical action follows.",
    tone: "warn",
  },
  reject: {
    title: "Reject recommendation",
    consequence:
      "Records that this recommendation version should not be acted on. Model 2 keeps the incident record and may raise new versions if new evidence arrives.",
    tone: "bad",
  },
  "request-revision": {
    title: "Request revision",
    consequence:
      "Sends a human correction to Model 2, which revises the incident and withdraws this recommendation version.",
    tone: "warn",
  },
  acknowledge: {
    title: "Acknowledge incident review",
    consequence:
      "Acknowledges the pending review of the current recommendation for this incident (Model 2 'approve review').",
    tone: "ok",
  },
  "request-review": {
    title: "Request priority review",
    consequence:
      "Flags this incident for priority human review (Model 2 'prioritize'). It does not change the Model 2 urgency assessment itself.",
    tone: "primary",
  },
  "resolution-report": {
    title: "Submit simulated resolution report",
    consequence:
      "Reports that this simulated incident was resolved. It is not a claim of physical rescue. A coordinator may close the incident afterwards.",
    tone: "primary",
  },
  close: {
    title: "Close incident",
    consequence:
      "Closes the incident after a prior resolution report. Coordinator only. Model 2 rejects closure without a resolution report.",
    tone: "bad",
  },
  correct: {
    title: "Submit correction feedback",
    consequence:
      "Sends human correction feedback for this incident revision to Model 2, which may revise its assessment.",
    tone: "warn",
  },
};

export function DecisionDialog({
  missionId,
  target,
  onClose,
  onSubmitted,
}: {
  missionId: string;
  target: DecisionTarget;
  onClose: () => void;
  onSubmitted?: (d: Decision) => void;
}) {
  const mode = useMode();
  const client = useQueryClient();
  const key = useMemo(() => newIdempotencyKey(mode === "synthetic" ? "syn" : "ui"), [mode]);
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<Decision | null>(null);
  const meta = DESCRIPTIONS[target.action]!;
  const version = target.kind === "recommendation" ? target.recommendation.version : target.incident.revision;

  const mutation = useMissionMutation(missionId, (p, v: { reason: string }) => {
    const body = { reason: v.reason, idempotency_key: key };
    if (target.kind === "recommendation") {
      const id = target.recommendation.id;
      const decision = { ...body, version };
      if (target.action === "approve") return p.approve(id, decision);
      if (target.action === "confirm") return p.approve(id, { ...decision, confirm_rescue_need: true });
      if (target.action === "reject") return p.reject(id, decision);
      return p.requestRevision(id, decision);
    }
    if (target.action === "correct")
      return p.feedback(missionId, {
        ...body,
        revision: version,
        incident_id: target.incident.id,
        action: "correct",
      });
    return p.incidentAction(target.incident.id, target.action, { ...body, revision: version });
  });

  const error = mutation.error ? asApiError(mutation.error) : null;
  const stale = error?.code === "stale_version";
  const submit = () =>
    mutation.mutate(
      { reason: reason.trim() },
      {
        onSuccess: (d) => {
          setResult(d);
          onSubmitted?.(d);
        },
      },
    );
  const reload = () => {
    void client.invalidateQueries({ queryKey: keys.scoped(mode, missionId) });
    onClose();
  };
  const incident = target.kind === "incident" ? target.incident : target.incident;

  if (result)
    return (
      <ConfirmDialog
        open
        title={`${meta.title}: submitted`}
        confirmLabel="Close"
        onConfirm={onClose}
        onCancel={onClose}
      >
        <AlertBox tone="info" title="Decision recorded and sent to Model 2.">
          Status <StatusBadge status={result.status} />. Model 2's validator decides whether it is accepted;
          the outcome appears in the decision history and the event timeline.
        </AlertBox>
        <Kv
          items={[
            ["Decision", <code key="d">{result.id}</code>],
            ["Action", statusLabel(result.action)],
            ["Expected version", result.expected_revision ?? "—"],
            ["Submitted", result.submitted_at],
          ]}
        />
        <Link to={`/missions/${missionId}/review?tab=decisions`} onClick={onClose}>
          View decision history
        </Link>
      </ConfirmDialog>
    );

  return (
    <ConfirmDialog
      open
      title={meta.title}
      confirmLabel={meta.title}
      tone={meta.tone}
      busy={mutation.isPending}
      disabled={!confirmed || !reason.trim() || stale}
      onConfirm={submit}
      onCancel={onClose}
    >
      <Kv
        items={[
          [
            target.kind === "recommendation" ? "Recommendation" : "Incident",
            <code key="id">
              {target.kind === "recommendation" ? target.recommendation.id : target.incident.id}
            </code>,
          ],
          [target.kind === "recommendation" ? "Version shown" : "Revision shown", <b key="v">v{version}</b>],
          ...(target.kind === "recommendation"
            ? ([
                ["Request", statusLabel(target.recommendation.request)],
                ["Status", <StatusBadge key="s" status={target.recommendation.status} />],
                ["Evidence", `${target.recommendation.evidence_ids.length} item(s)`],
                ["Unknowns", target.recommendation.unknowns.join("; ") || "none listed"],
              ] as [string, ReactNode][])
            : []),
          ...(incident
            ? ([
                [
                  "Incident",
                  `${statusLabel(incident.category)} · ${shortId(incident.id)} · r${incident.revision}`,
                ],
                ["Priority (Model 2)", <StatusBadge key="p" status={incident.priority_level} />],
                ["Location", formatLocation(incident.location)],
                [
                  "Evidence balance",
                  `${incident.supporting_observations} supporting · ${incident.conflicting_observations} conflicting`,
                ],
              ] as [string, ReactNode][])
            : []),
        ]}
      />
      <AlertBox tone="info">{meta.consequence}</AlertBox>
      <TextField
        label="Reason (required, recorded with the decision)"
        value={reason}
        onChange={setReason}
        required
        maxLength={100}
        help={`${reason.length}/100 characters`}
      />
      <label className="check">
        <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I
        reviewed version v{version}, its evidence and uncertainty, and understand this is a simulated
        decision-support action.
      </label>
      {stale && (
        <AlertBox
          tone="warn"
          title="This version is outdated."
          actions={
            <button className="btn sm" onClick={reload}>
              Load updated version
            </button>
          }
        >
          Model 2 revised this item after it was shown (submitted v{version}). Review the updated version
          before deciding. Details: {JSON.stringify(error?.details ?? {})}
        </AlertBox>
      )}
      {error && !stale && (
        <AlertBox tone="bad" title={error.kind === "forbidden" ? "Not permitted." : "Not submitted."}>
          {error.userMessage} {error.code ? `(${error.code})` : ""}
        </AlertBox>
      )}
      <p className="xs muted">
        Idempotency key <code>{key}</code> · retrying reuses this key so the decision is recorded at most
        once.
      </p>
    </ConfirmDialog>
  );
}
