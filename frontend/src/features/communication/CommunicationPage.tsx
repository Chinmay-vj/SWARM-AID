import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import type { Agent, MissionEvent } from "../../contracts/api";
import { Kv, Metric, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { EmptyState, QueryView } from "../../components/ui/states";
import { useLiveInterval, useMission, useMissionQuery, useMode } from "../../hooks/data";
import { formatDuration, formatFraction, formatNumber, formatSimTime } from "../../lib/format";
import { useActivity } from "../../stores/activity";
import { useConnection } from "../../stores/connection";
import { usePreferences } from "../../stores/preferences";
import { EventList } from "../events/EventList";

type LinkState = "known-ok" | "degraded" | "down" | "unknown";
const LINK_COLOR: Record<LinkState, string> = {
  "known-ok": "var(--ok)",
  degraded: "var(--warn)",
  down: "var(--bad)",
  unknown: "var(--unknown)",
};
const LINK_DASH: Record<LinkState, string | undefined> = {
  "known-ok": undefined,
  degraded: "6 3",
  down: "2 4",
  unknown: "1 5",
};

interface Pulse {
  id: number;
  from: string;
  to: string;
  color: string;
}

/** Build pulses only from events actually received (never invented). */
export function pulsesFor(
  events: Pick<MissionEvent, "event_type" | "payload" | "sequence">[],
): Omit<Pulse, "id">[] {
  const out: Omit<Pulse, "id">[] = [];
  for (const e of events) {
    if (e.event_type === "OBSERVATION_RECEIVED" && typeof e.payload.reporter === "string")
      out.push({ from: e.payload.reporter, to: "command", color: "var(--accent)" });
    else if (e.event_type === "HUMAN_REVIEW_REQUESTED" || e.event_type === "ALERT_RAISED")
      out.push({ from: "command", to: "operator", color: "var(--warn)" });
    else if (e.event_type === "HUMAN_DECISION_RESOLVED")
      out.push({ from: "operator", to: "command", color: "var(--ok)" });
    else if (e.event_type === "TASK_UPDATED" && typeof e.payload.member === "string")
      out.push({ from: "command", to: e.payload.member, color: "var(--violet)" });
  }
  return out;
}

export default function CommunicationPage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const live = useLiveInterval();
  const mission = useMission(missionId);
  const agents = useMissionQuery(missionId, ["agents"], (p, id, s) => p.agents(id, s), {
    refetchInterval: live,
  });
  const metrics = useMissionQuery(missionId, ["metrics"], (p, id, s) => p.metrics(id, s), {
    refetchInterval: live,
  });
  const degraded = useMissionQuery(
    missionId,
    ["metrics", "comm-history"],
    async (p, id, s) => {
      const [a, b] = await Promise.all([
        p.events(id, { after: 0, limit: 200, eventType: "COMMUNICATION_DEGRADED" }, s),
        p.events(id, { after: 0, limit: 200, eventType: "COMMUNICATION_RESTORED" }, s),
      ]);
      return [...a, ...b].sort((x, y) => y.sequence - x.sequence);
    },
    { refetchInterval: live },
  );
  const stream = useConnection((s) => s.stream);
  const events = useActivity((s) => s.events);
  const reduced = usePreferences((s) => s.reducedMotion);
  const [show, setShow] = useState({ peer: true, command: true, operator: true, dashboard: true });
  const [pulses, setPulses] = useState<Pulse[]>([]);
  const lastSeq = useRef(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    const previous = lastSeq.current;
    const fresh = events.filter((e) => e.sequence > previous);
    if (!fresh.length) return;
    lastSeq.current = fresh[0]!.sequence;
    if (reduced || previous === 0) return; // no pulses for history loaded on open
    const next = pulsesFor(fresh.slice(0, 12)).map((p, i) => ({ ...p, id: fresh[0]!.sequence * 100 + i }));
    const ids = new Set(next.map((p) => p.id));
    setPulses((ps) => [...ps, ...next].slice(-30));
    timers.current.push(setTimeout(() => setPulses((ps) => ps.filter((p) => !ids.has(p.id))), 1200));
  }, [events, reduced]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const comm =
    metrics.data?.live?.communication_full ??
    metrics.data?.live?.communication ??
    metrics.data?.runs.at(-1)?.operational_metrics?.communication_full ??
    null;
  const source = metrics.data?.live ? "live run" : metrics.data?.runs.length ? "last completed run" : null;
  const lastComm = degraded.data?.[0];
  const endpoints = (lastComm?.payload.endpoints ?? {}) as Record<string, string>;
  const operatorState: LinkState = endpoints.operator
    ? endpoints.operator === "connected"
      ? "known-ok"
      : "down"
    : lastComm
      ? "known-ok"
      : "unknown";
  const list = useMemo(() => agents.data ?? [], [agents.data]);

  const layout = useMemo(() => {
    const pos: Record<string, [number, number]> = {
      command: [320, 210],
      operator: [320, 400],
      dashboard: [560, 400],
    };
    list.forEach((a, i) => {
      const angle = (Math.PI * 2 * i) / Math.max(1, list.length) - Math.PI / 2;
      pos[a.agent_key] = [320 + 240 * Math.cos(angle), 175 + 135 * Math.sin(angle)];
    });
    return pos;
  }, [list]);
  const agentLink = (a: Agent): LinkState =>
    a.communication === "connected" ? "known-ok" : a.communication === "disconnected" ? "down" : "unknown";
  const streamLink: LinkState =
    stream === "open"
      ? "known-ok"
      : stream === "polling" || stream === "reconnecting" || stream === "connecting"
        ? "degraded"
        : stream === "failed"
          ? "down"
          : "unknown";

  return (
    <div className="stack">
      <PageHeader
        title="Communication network"
        description="Simulated Model 1 ↔ Model 1, Model 1 → Model 2, Model 2 → human operator, and the backend event stream to this dashboard. Link health is shown only where it is known."
        actions={<SourceTag synthetic={synthetic} />}
      />
      <div className="metrics">
        <Metric
          label="Link state"
          value={mission.data?.communication_state ?? "—"}
          tone={
            mission.data?.communication_state === "nominal"
              ? "ok"
              : mission.data?.communication_state === "degraded"
                ? "warn"
                : "muted"
          }
          hint="mission runtime"
        />
        <Metric
          label="Delivery ratio"
          value={formatFraction(comm?.delivery_ratio, 1)}
          hint={source ?? "no metrics yet"}
          synthetic={synthetic}
        />
        <Metric
          label="Messages generated"
          value={formatNumber(comm?.generated)}
          hint={`${formatNumber(comm?.delivered)} delivered`}
          synthetic={synthetic}
        />
        <Metric
          label="Mean latency"
          value={comm?.mean_ms === undefined || comm?.mean_ms === null ? "—" : formatDuration(comm.mean_ms)}
          hint={`p95 ${comm?.p95_ms ?? "—"} ms`}
          synthetic={synthetic}
        />
        <Metric
          label="Dropped / expired"
          value={`${formatNumber(comm?.dropped)} / ${formatNumber(comm?.expired)}`}
          hint="packet loss and staleness"
          tone="warn"
          synthetic={synthetic}
        />
        <Metric
          label="Duplicates"
          value={formatNumber(comm?.duplicate)}
          hint="detected duplicates"
          synthetic={synthetic}
        />
        <Metric
          label="Connection lost / restored"
          value={`${formatNumber(comm?.connection_lost)} / ${formatNumber(comm?.connection_restored)}`}
          hint="partitions and recoveries"
          synthetic={synthetic}
        />
        <Metric
          label="Dashboard stream"
          value={stream}
          tone={streamLink === "known-ok" ? "ok" : streamLink === "down" ? "bad" : "warn"}
          hint="backend → this browser"
        />
      </div>
      <div className="grid main-side">
        <Panel title="Topology">
          <fieldset className="row" style={{ border: 0, padding: 0, margin: "0 0 8px" }}>
            <legend className="sr-only">Link filters</legend>
            {(Object.keys(show) as (keyof typeof show)[]).map((k) => (
              <label key={k} className="check xs">
                <input
                  type="checkbox"
                  checked={show[k]}
                  onChange={() => setShow((s) => ({ ...s, [k]: !s[k] }))}
                />
                {k === "peer"
                  ? "Model 1 peer"
                  : k === "command"
                    ? "Model 1 → Model 2"
                    : k === "operator"
                      ? "Model 2 → human"
                      : "event stream"}
              </label>
            ))}
          </fieldset>
          <QueryView
            query={agents}
            isEmpty={(a) => a.length === 0}
            empty={<EmptyState title="No agents registered" />}
          >
            {() => (
              <svg
                viewBox="0 0 640 450"
                width="100%"
                role="img"
                aria-label={`Communication topology: ${list.length} agents, command agent, human operator and dashboard. ${list.filter((a) => a.communication === "disconnected").length} agent links down.`}
                style={{ background: "var(--map-bg)", borderRadius: 8 }}
              >
                {show.peer &&
                  list.map((a, i) => {
                    const b = list[(i + 1) % list.length]!;
                    if (b === a) return null;
                    const [x1, y1] = layout[a.agent_key]!;
                    const [x2, y2] = layout[b.agent_key]!;
                    return (
                      <line
                        key={`p${a.agent_key}`}
                        x1={x1}
                        y1={y1}
                        x2={x2}
                        y2={y2}
                        stroke={LINK_COLOR.unknown}
                        strokeDasharray={LINK_DASH.unknown}
                      />
                    );
                  })}
                {show.command &&
                  list.map((a) => {
                    const [x1, y1] = layout[a.agent_key]!;
                    const st = agentLink(a);
                    return (
                      <line
                        key={`c${a.agent_key}`}
                        x1={x1}
                        y1={y1}
                        x2={320}
                        y2={210}
                        stroke={LINK_COLOR[st]}
                        strokeWidth={1.6}
                        strokeDasharray={LINK_DASH[st]}
                      />
                    );
                  })}
                {show.operator && (
                  <line
                    x1={320}
                    y1={210}
                    x2={320}
                    y2={400}
                    stroke={LINK_COLOR[operatorState]}
                    strokeWidth={2}
                    strokeDasharray={LINK_DASH[operatorState]}
                  />
                )}
                {show.dashboard && (
                  <line
                    x1={320}
                    y1={400}
                    x2={560}
                    y2={400}
                    stroke={LINK_COLOR[streamLink]}
                    strokeWidth={2}
                    strokeDasharray={LINK_DASH[streamLink]}
                  />
                )}
                {pulses.map((p) => {
                  const a = layout[p.from];
                  const b = layout[p.to];
                  if (!a || !b) return null;
                  return (
                    <circle key={p.id} r={4} fill={p.color}>
                      <animateMotion dur="1s" path={`M${a[0]},${a[1]} L${b[0]},${b[1]}`} fill="freeze" />
                    </circle>
                  );
                })}
                {list.map((a) => {
                  const [x, y] = layout[a.agent_key]!;
                  const st = agentLink(a);
                  return (
                    <g key={a.agent_key}>
                      <circle
                        cx={x}
                        cy={y}
                        r={18}
                        fill="var(--surface)"
                        stroke={LINK_COLOR[st]}
                        strokeWidth={2}
                      />
                      <text
                        x={x}
                        y={y + 4}
                        textAnchor="middle"
                        fontSize={10}
                        fontWeight={700}
                        fill="var(--text-strong)"
                      >
                        {a.agent_key}
                      </text>
                      <text x={x} y={y + 31} textAnchor="middle" fontSize={8.5} fill="var(--muted)">
                        {a.communication}
                      </text>
                    </g>
                  );
                })}
                {[
                  ["command", "MODEL 2", "command agent", mission.data?.model2_state ?? "unknown"],
                  ["operator", "HUMAN", "operator endpoint", operatorState],
                  ["dashboard", "DASHBOARD", "event stream", stream],
                ].map(([k, l, sub, st]) => {
                  const [x, y] = layout[k!]!;
                  return (
                    <g key={k}>
                      <circle
                        cx={x}
                        cy={y}
                        r={30}
                        fill="var(--surface-2)"
                        stroke="var(--accent)"
                        strokeWidth={2}
                      />
                      <text
                        x={x}
                        y={y + 3}
                        textAnchor="middle"
                        fontSize={10}
                        fontWeight={800}
                        fill="var(--text-strong)"
                      >
                        {l}
                      </text>
                      <text x={x} y={y + 44} textAnchor="middle" fontSize={9} fill="var(--muted)">
                        {sub} · {String(st)}
                      </text>
                    </g>
                  );
                })}
              </svg>
            )}
          </QueryView>
          <div className="legend" style={{ marginTop: 6 }}>
            <span>
              <i className="swatch" style={{ background: "var(--ok)" }} />
              known connected
            </span>
            <span>
              <i className="swatch" style={{ background: "var(--warn)" }} />
              degraded
            </span>
            <span>
              <i className="swatch" style={{ background: "var(--bad)" }} />
              down
            </span>
            <span>
              <i className="swatch" style={{ background: "var(--unknown)" }} />
              unknown (not reported)
            </span>
          </div>
          <p className="xs muted">
            Per-link peer state is not reported by the backend, so peer links are drawn as unknown. Pulses
            animate only for events received by this dashboard{synthetic ? " (synthetic playback)" : ""};
            healthy communication is never inferred from an agent merely existing.
          </p>
        </Panel>
        <div className="stack">
          <Panel title={`Router metrics (${source ?? "none"})`}>
            {comm ? (
              <Kv
                items={Object.entries(comm)
                  .filter(([, v]) => typeof v === "number")
                  .map(([k, v]) => [k.replace(/_/g, " "), formatNumber(v as number, 3)])}
              />
            ) : (
              <EmptyState title="No communication metrics yet" />
            )}
          </Panel>
          <Panel title="Degradation and recovery history">
            <QueryView
              query={degraded}
              isEmpty={(d) => d.length === 0}
              empty={<EmptyState title="No degradation recorded" />}
            >
              {(d) => (
                <ul className="timeline">
                  {d.map((e) => (
                    <li key={e.sequence}>
                      <span className="t">{formatSimTime(e.sim_time_ms)}</span>
                      <div>
                        <StatusBadge
                          status={e.event_type === "COMMUNICATION_DEGRADED" ? "degraded" : "nominal"}
                          label={e.event_type === "COMMUNICATION_DEGRADED" ? "degraded" : "restored"}
                        />
                        <span className="xs muted">
                          {" "}
                          disconnected:{" "}
                          {Array.isArray(e.payload.disconnected)
                            ? e.payload.disconnected.join(", ") || "none"
                            : "—"}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </QueryView>
          </Panel>
        </div>
      </div>
      <Panel title="Communication events (this session)">
        <EventList
          events={events.filter(
            (e) => e.event_type.startsWith("COMMUNICATION") || e.event_type.startsWith("MODEL_2"),
          )}
          missionId={missionId!}
          maxHeight={240}
          synthetic={synthetic}
        />
      </Panel>
    </div>
  );
}
