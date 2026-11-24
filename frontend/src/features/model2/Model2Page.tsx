/**
 * Model 2 (central command agent) monitoring. Shows only what the backend exposes: state,
 * counters, incidents with their evidence groups, assessments and recommendations. The
 * dashboard does not reconstruct or replace Model 2 reasoning.
 */
import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { Kv, Metric, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { EmptyState, QueryView } from "../../components/ui/states";
import { useLiveInterval, useMission, useMissionQuery, useMode } from "../../hooks/data";
import { formatSimTime, humanize, shortId } from "../../lib/format";
import { statusLabel } from "../../lib/status";
import { useActivity } from "../../stores/activity";
import { EventList } from "../events/EventList";

const MODEL2_TOPICS = new Set([
  "INCIDENT_CREATED",
  "INCIDENT_UPDATED",
  "INCIDENT_ESCALATED",
  "EVIDENCE_GROUP_UPDATED",
  "RECOMMENDATION_CREATED",
  "RECOMMENDATION_REVISED",
  "HUMAN_DECISION_RESOLVED",
  "MODEL_2_UNAVAILABLE",
  "MODEL_2_RECOVERED",
]);

export default function Model2Page() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const live = useLiveInterval();
  const mission = useMission(missionId);
  const metrics = useMissionQuery(missionId, ["metrics"], (p, id, s) => p.metrics(id, s), {
    refetchInterval: live,
  });
  const incidents = useMissionQuery(
    missionId,
    ["incidents", "model2"],
    (p, id, s) => p.incidents(id, { limit: 12 }, s),
    { refetchInterval: live },
  );
  const groups = useMissionQuery(
    missionId,
    ["incidents", "model2-groups", incidents.data?.items.map((i) => `${i.id}:${i.revision}`).join(",")],
    (p, _id, s) => Promise.all((incidents.data?.items ?? []).map((i) => p.evidenceGroup(i.id, s))),
    { enabled: Boolean(incidents.data?.items.length) },
  );
  const allEvents = useActivity((s) => s.events);
  const events = useMemo(() => allEvents.filter((e) => MODEL2_TOPICS.has(e.event_type)), [allEvents]);
  const m = mission.data;
  const counts =
    metrics.data?.live?.model2_counts ??
    metrics.data?.runs.at(-1)?.operational_metrics?.model2_counts ??
    null;
  const countSource = metrics.data?.live
    ? "live run"
    : metrics.data?.runs.length
      ? "last completed run"
      : null;
  const base = `/missions/${missionId}`;

  return (
    <div className="stack">
      <PageHeader
        title="Command agent · Model 2"
        description="Central rescue command agent outputs: how Model 1 reports are grouped, assessed and turned into recommendations for human review."
        actions={<SourceTag synthetic={synthetic} />}
      />
      <div className="metrics">
        <Metric
          label="Availability"
          value={m ? statusLabel(m.model2_state) : "—"}
          tone={m?.model2_state === "available" ? "ok" : m?.model2_state === "unavailable" ? "bad" : "muted"}
          hint="reported by runtime"
        />
        <Metric
          label="Reports admitted"
          value={counts?.admitted ?? "—"}
          hint={countSource ?? "no metrics yet"}
          synthetic={synthetic}
        />
        <Metric
          label="Incidents opened"
          value={counts?.incident_opened ?? counts?.opened ?? "—"}
          hint="Model 2 counter"
          synthetic={synthetic}
        />
        <Metric
          label="Revisions"
          value={counts?.revised ?? "—"}
          hint="assessment updates"
          synthetic={synthetic}
        />
        <Metric
          label="Corroborations"
          value={counts?.corroborated ?? "—"}
          hint="additional supporting reports"
          synthetic={synthetic}
        />
        <Metric
          label="Expired reviews"
          value={counts?.expired ?? "—"}
          hint="deadline passed without decision"
          tone="warn"
          synthetic={synthetic}
        />
      </div>
      {m?.model2_state === "unavailable" && (
        <Panel title="Degraded state">
          <p className="small">
            Model 2 is unavailable. Reports are retained and assessed after recovery; existing incidents are
            shown as last known.
          </p>
        </Panel>
      )}
      <div className="grid main-side">
        <Panel title="From Model 1 reports to Model 2 assessments">
          <QueryView
            query={incidents}
            isEmpty={(p) => p.items.length === 0}
            empty={<EmptyState title="No incidents assessed yet" />}
          >
            {(p) => (
              <div className="stack tight">
                {p.items.map((i, idx) => {
                  const g = groups.data?.[idx];
                  const perAgent: Record<string, number> = {};
                  g?.observations.forEach((o) => (perAgent[o.reporter] = (perAgent[o.reporter] ?? 0) + 1));
                  return (
                    <div key={i.id} className="entity-card">
                      <div className="row between">
                        <Link to={`${base}/incidents/${i.id}`}>
                          {statusLabel(i.category)} · {shortId(i.id)} · r{i.revision}
                        </Link>
                        <span className="row" style={{ gap: 4 }}>
                          <StatusBadge status={i.priority_level} />
                          <StatusBadge status={i.disposition} />
                        </span>
                      </div>
                      <div className="small">
                        {g ? (
                          <>
                            {g.observations.length} Model 1 report(s) from{" "}
                            <b>{g.distinct_reporters.length}</b> independent agent(s):{" "}
                            {Object.entries(perAgent)
                              .map(([a, n]) => `${a}×${n}`)
                              .join(", ") || "—"}
                          </>
                        ) : (
                          "loading evidence group…"
                        )}
                      </div>
                      <div className="xs muted">
                        {i.supporting_observations} supporting · {i.conflicting_observations} conflicting ·
                        Model 2 reason: {i.priority_reason ?? "—"}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </QueryView>
        </Panel>
        <div className="stack">
          <Panel title="Model 2 counters">
            {counts ? (
              <Kv items={Object.entries(counts).map(([k, v]) => [humanize(k), v])} />
            ) : (
              <EmptyState title="No counters yet">
                Counters are published with METRICS_UPDATED events while a run is active.
              </EmptyState>
            )}
            <p className="xs muted" style={{ marginTop: 6 }}>
              Mode: {String(m?.config.command_mode ?? "—")} · sim {formatSimTime(m?.last_sim_ms)}
            </p>
          </Panel>
          <Panel title="Model 2 activity (this session)">
            <EventList events={events} missionId={missionId!} maxHeight={320} synthetic={synthetic} />
          </Panel>
        </div>
      </div>
    </div>
  );
}
