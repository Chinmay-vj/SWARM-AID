import { useNavigate, useParams, Link } from "react-router-dom";
import { MissionMap, useTrails, type MapSelection } from "../../components/maps/MissionMap";
import { Kv, Metric, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { AlertBox, EmptyState, QueryView } from "../../components/ui/states";
import { useLiveInterval, useMission, useMissionQuery, useMode } from "../../hooks/data";
import { agentCondition } from "../../lib/freshness";
import { formatDuration, formatFraction, formatSimTime, formatWallTime, humanize } from "../../lib/format";
import { statusLabel } from "../../lib/status";
import { useActivity } from "../../stores/activity";
import { useConnection } from "../../stores/connection";
import { usePreferences } from "../../stores/preferences";
import { EventList } from "../events/EventList";
import { MissionControls } from "./MissionControls";

export default function OverviewPage() {
  const { missionId } = useParams();
  const mode = useMode();
  const synthetic = mode === "synthetic";
  const navigate = useNavigate();
  const live = useLiveInterval();
  const timeDisplay = usePreferences((s) => s.timeDisplay);
  const mission = useMission(missionId);
  const summary = useMissionQuery(missionId, ["summary"], (p, id, s) => p.summary(id, s), {
    refetchInterval: live,
  });
  const map = useMissionQuery(missionId, ["map"], (p, id, s) => p.map(id, s), { refetchInterval: live });
  const coverage = useMissionQuery(missionId, ["coverage"], (p, id, s) => p.coverage(id, s), {
    refetchInterval: live,
  });
  const agents = useMissionQuery(missionId, ["agents"], (p, id, s) => p.agents(id, s), {
    refetchInterval: live,
  });
  const review = useMissionQuery(missionId, ["review"], (p, id, s) => p.reviewQueue(id, s), {
    refetchInterval: live,
  });
  const hazards = useMissionQuery(missionId, ["hazards"], (p, id, s) => p.hazards(id, s), {
    refetchInterval: live,
  });
  const incidents = useMissionQuery(
    missionId,
    ["incidents", "overview"],
    (p, id, s) => p.incidents(id, { limit: 6 }, s),
    { refetchInterval: live },
  );
  const sightings = useMissionQuery(
    missionId,
    ["observations", "sightings"],
    (p, id, s) => p.observations(id, { kind: "possible_human", limit: 1 }, s),
    { refetchInterval: live },
  );
  const events = useActivity((s) => s.events);
  const lastSync = useConnection((s) => s.lastSyncAt);
  const trails = useTrails(map.data);
  const m = mission.data;
  if (!m || !missionId) return null;
  const base = `/missions/${missionId}`;
  const onSelect = (sel: MapSelection) => {
    if (sel.layer === "agents") {
      const agent = agents.data?.find((a) => a.agent_key === sel.id);
      if (agent) navigate(`${base}/fleet/${agent.id}`);
    } else if (sel.layer === "incidents") navigate(`${base}/incidents/${sel.id}`);
    else if (sel.layer === "hazards") navigate(`${base}/environment?hazard=${sel.id}`);
  };
  const s = summary.data;
  const openIncidents = s
    ? Object.entries(s.incidents_by_disposition)
        .filter(([d]) => !["closed", "rejected", "expired"].includes(d))
        .reduce((a, [, n]) => a + n, 0)
    : null;
  const available = agents.data?.filter((a) => a.availability === "available").length;

  return (
    <div className="stack">
      <PageHeader
        title={m.name}
        description={
          <>
            {m.scenario_id} · seed {String(m.config.seed ?? "—")} · {String(m.config.agents ?? "—")} agents ·{" "}
            {humanize(String(m.config.coordination ?? ""))} coordination · Model 2{" "}
            {String(m.config.command_mode ?? "—")} · created {formatWallTime(m.created_at, timeDisplay)}
          </>
        }
        actions={<MissionControls mission={m} />}
      />
      {m.status === "running" && (review.data?.length ?? 0) > 0 && (
        <AlertBox tone="info" title="Reviews are waiting.">
          Model 2 review deadlines run on simulation time. Pause the mission to give reviewers time;
          recommendations do not expire while paused. <Link to={`${base}/review`}>Open human review</Link>
        </AlertBox>
      )}
      <div className="metrics" aria-label="Mission metrics">
        <Metric
          label="Agents"
          value={s?.agents ?? "—"}
          hint={`${available ?? "?"} available · ${s?.agents_connected ?? "?"} connected`}
          to={`${base}/fleet`}
          synthetic={synthetic}
        />
        <Metric
          label="Possible human sightings"
          value={sightings.data?.total ?? "—"}
          hint="reports, unverified"
          tone="warn"
          to={`${base}/observations?kind=possible_human`}
          synthetic={synthetic}
        />
        <Metric
          label="Open incidents"
          value={openIncidents ?? "—"}
          hint="Model 2 assessments"
          tone="bad"
          to={`${base}/incidents`}
          synthetic={synthetic}
        />
        <Metric
          label="Pending reviews"
          value={s?.pending_recommendations ?? "—"}
          hint={`${s?.open_alerts ?? "?"} unacknowledged alerts`}
          tone="warn"
          to={`${base}/review`}
          synthetic={synthetic}
        />
        <Metric
          label="Observations"
          value={s?.observations ?? "—"}
          hint="reported by Model 1"
          to={`${base}/observations`}
          synthetic={synthetic}
        />
        <Metric
          label="Reported coverage"
          value={formatFraction(coverage.data?.reported_fraction)}
          hint="agent-reported, not verified"
          tone="ok"
          to={`${base}/coordination`}
          synthetic={synthetic}
        />
        <Metric
          label="Hazards"
          value={s?.hazards ?? "—"}
          hint="reported; absence ≠ safety"
          tone="info"
          to={`${base}/environment`}
          synthetic={synthetic}
        />
        <Metric
          label="Communication"
          value={statusLabel(m.communication_state)}
          hint={`Model 2 ${statusLabel(m.model2_state)}`}
          tone={
            m.communication_state === "nominal"
              ? "ok"
              : m.communication_state === "degraded"
                ? "warn"
                : "muted"
          }
          to={`${base}/communication`}
          synthetic={synthetic}
        />
        <Metric
          label="Simulation time"
          value={
            <span className="mono" style={{ fontSize: 18 }}>
              {formatSimTime(m.last_sim_ms)}
            </span>
          }
          hint={lastSync ? `synced ${formatDuration(Date.now() - lastSync)} ago` : "not yet synced"}
          tone="muted"
        />
      </div>
      <div className="grid main-side">
        <Panel
          title="Live simulation map"
          actions={
            <>
              <SourceTag synthetic={synthetic} />
              <Link className="small" to={`${base}/map`}>
                Full map
              </Link>
            </>
          }
        >
          <QueryView query={map} rows={8}>
            {(data) => (
              <MissionMap
                data={data}
                coverage={coverage.data}
                trails={trails}
                onSelect={onSelect}
                height={400}
                synthetic={synthetic}
              />
            )}
          </QueryView>
        </Panel>
        <div className="stack">
          <Panel
            title="Human review queue"
            actions={
              <Link className="small" to={`${base}/review`}>
                Open
              </Link>
            }
          >
            <QueryView
              query={review}
              isEmpty={(r) => r.length === 0}
              empty={<EmptyState title="Nothing awaiting review" />}
            >
              {(items) => (
                <ul className="timeline">
                  {items.slice(0, 4).map((r) => (
                    <li key={r.recommendation.id}>
                      <span className="t">{formatDuration(r.remaining_ms)} left</span>
                      <div>
                        <Link to={`${base}/recommendations/${r.recommendation.id}`}>
                          {statusLabel(r.recommendation.request)} · v{r.recommendation.version}
                        </Link>
                        <div className="row" style={{ gap: 4 }}>
                          <StatusBadge status={r.incident.priority_level} />
                          <span className="xs muted">
                            {statusLabel(r.incident.category)} · {r.incident.supporting_observations}{" "}
                            supporting / {r.incident.conflicting_observations} conflicting
                          </span>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </QueryView>
          </Panel>
          <Panel
            title="Recent events"
            actions={
              <Link className="small" to={`${base}/events`}>
                Timeline
              </Link>
            }
          >
            <EventList
              events={events}
              missionId={missionId}
              maxHeight={260}
              limit={30}
              synthetic={synthetic}
            />
          </Panel>
        </div>
      </div>
      <div className="grid cols-3">
        <Panel
          title="Drone fleet (Model 1)"
          actions={
            <Link className="small" to={`${base}/fleet`}>
              Fleet
            </Link>
          }
        >
          <QueryView
            query={agents}
            isEmpty={(a) => a.length === 0}
            empty={<EmptyState title="No agents registered" />}
          >
            {(list) => (
              <div className="stack tight">
                {list.slice(0, 8).map((a) => {
                  const c = agentCondition(a, m.last_sim_ms);
                  return (
                    <div key={a.id} className="row between">
                      <Link to={`${base}/fleet/${a.id}`}>{a.agent_key}</Link>
                      <span className="row" style={{ gap: 4 }}>
                        <StatusBadge status={c === "nominal" ? "available" : c} label={c} />
                        <StatusBadge status={a.communication} />
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </QueryView>
        </Panel>
        <Panel
          title="Incidents (Model 2)"
          actions={
            <Link className="small" to={`${base}/incidents`}>
              All
            </Link>
          }
        >
          <QueryView
            query={incidents}
            isEmpty={(p) => p.items.length === 0}
            empty={<EmptyState title="No incidents assessed" />}
          >
            {(page) => (
              <div className="stack tight">
                {page.items.map((i) => (
                  <div key={i.id} className="row between">
                    <Link to={`${base}/incidents/${i.id}`}>
                      {statusLabel(i.category)} r{i.revision}
                    </Link>
                    <span className="row" style={{ gap: 4 }}>
                      <StatusBadge status={i.priority_level} />
                      <StatusBadge status={i.disposition} />
                    </span>
                  </div>
                ))}
              </div>
            )}
          </QueryView>
        </Panel>
        <Panel
          title="Hazards & mission"
          actions={
            <Link className="small" to={`${base}/environment`}>
              Environment
            </Link>
          }
        >
          <Kv
            items={[
              ["Reported hazards", hazards.data ? hazards.data.length : "—"],
              [
                "Hazard labels",
                hazards.data
                  ? [...new Set(hazards.data.map((h) => h.label))].join(", ") || "none reported"
                  : "—",
              ],
              ["Model 2", <StatusBadge key="m2" status={m.model2_state} />],
              ["Communication", <StatusBadge key="c" status={m.communication_state} />],
              ["Last event", `#${m.last_event_sequence}`],
              ["Run", m.current_run_id ? <code key="r">{m.current_run_id.slice(0, 8)}</code> : "not started"],
            ]}
          />
          <p className="xs muted" style={{ marginTop: 8 }}>
            No reported hazard does not mean an area is safe.
          </p>
        </Panel>
      </div>
    </div>
  );
}
