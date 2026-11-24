/**
 * Deterministic synthetic mission playback (ported from the Phase 8 presentation MVP).
 *
 * Produces records shaped exactly like the Phase 7 backend contracts so the dashboard renders
 * both sources through the same code. Hidden synthetic "truth" (people and hazard cells) is
 * used only to generate agent reports and is never exposed through any query.
 *
 * Mechanics are intentionally simple and are NOT a re-implementation of Model 1 or Model 2:
 * a fixed sector sweep, a proximity sensor model, and cell-based report grouping that mimics
 * the shape of Model 2 output for demonstration only.
 */
import type {
  Agent,
  AgentReport,
  Alert,
  CoordinationConflict,
  Decision,
  Evidence,
  Hazard,
  Incident,
  IncidentRevision,
  IncidentTransition,
  Location,
  Mission,
  MissionEvent,
  Observation,
  Recommendation,
  RecommendationStatusChange,
  StatusHistory,
  Task,
  TaskEvent,
} from "../../../contracts/api";
import { ApiError } from "../../api/errors";
import type { SyntheticPreset } from "./scenarios";

export const WIDTH = 12;
export const HEIGHT = 10;
export const TICK_MS = 100;
const BASE: [number, number] = [0, 4];
const REVIEW_WINDOW_MS = 9000;
const FRESHNESS_MS = 1500;
const CRS = "swarm-aid:grid";

type Cell = [number, number];
const key = (x: number, y: number) => `${x},${y}`;

export function seeded(seed: number): () => number {
  let s = seed >>> 0 || 1;
  return () => (s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 2 ** 32;
}

function uuidFrom(rand: () => number): string {
  const hex = Array.from({ length: 32 }, () => Math.floor(rand() * 16).toString(16)).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-8${hex.slice(17, 20)}-${hex.slice(20, 32)}`;
}

const loc = (x: number, y: number, uncertainty: number | null = 0.5): Location => ({
  crs: CRS,
  x,
  y,
  units: "cell",
  uncertainty,
  map_ref: null,
});

interface DroneState {
  agent: Agent;
  index: number;
  pos: Cell;
  path: Cell[];
  wp: number;
  battery: number;
  sensors: string[];
  statusReports: AgentReport[];
  healthReports: AgentReport[];
  sector: Cell[];
  lastState: string;
}

interface PendingReport {
  observation: Observation;
  evidence: Evidence[];
  drone: string;
}

export interface SeriesPoint {
  sim_ms: number;
  reported_fraction: number;
  observations: number;
  agents_available: number;
  messages: number;
  delivered: number;
  incidents: number;
  pending_reviews: number;
}

export class SyntheticMission {
  readonly preset: SyntheticPreset;
  mission: Mission;
  tick = 0;
  private rand: () => number;
  private idRand: () => number;
  private readonly hazardCells = new Map<string, string>(); // hidden synthetic truth
  private readonly buildings = new Set<string>(); // hidden synthetic truth
  private readonly people: Cell[]; // hidden synthetic truth
  readonly drones: DroneState[] = [];
  readonly statusHistory: StatusHistory[] = [];
  readonly observations: Observation[] = [];
  readonly evidence = new Map<string, Evidence[]>(); // observation pk -> evidence
  readonly incidents: Incident[] = [];
  readonly revisions = new Map<string, IncidentRevision[]>();
  readonly transitions = new Map<string, IncidentTransition[]>();
  readonly incidentObservations = new Map<string, string[]>(); // incident -> observation pks
  readonly recommendations: Recommendation[] = [];
  readonly recHistory = new Map<string, RecommendationStatusChange[]>();
  readonly decisions: Decision[] = [];
  readonly alerts: Alert[] = [];
  readonly tasks: Task[] = [];
  readonly taskEvents = new Map<string, TaskEvent[]>();
  readonly hazards: Hazard[] = [];
  readonly coverage = new Map<string, number>(); // cell -> last reported ms
  readonly conflicts: CoordinationConflict[] = [];
  readonly events: MissionEvent[] = [];
  readonly series: SeriesPoint[] = [];
  readonly comm = {
    generated: 0,
    delivered: 0,
    queued: 0,
    peer: 0,
    recoveries: 0,
    duplicates: 0,
    expired: 0,
    latencies: [] as number[],
  };
  readonly model2Counts: Record<string, number> = {};
  private model2Queue: PendingReport[] = [];
  private linkQueue: PendingReport[] = [];
  private pendingDecisions: Decision[] = [];
  private versionConflictArmed: boolean;
  private seenHazard = new Set<string>();
  private listeners = new Set<(e: MissionEvent) => void>();
  commDown = false;
  model2Down = false;

  constructor(
    preset: SyntheticPreset,
    private readonly actor = "synthetic-coordinator",
  ) {
    this.preset = preset;
    this.rand = seeded(preset.seed);
    this.idRand = seeded(preset.seed * 7919 + 17);
    this.versionConflictArmed = Boolean(preset.versionConflict);
    const now = new Date().toISOString();
    this.mission = {
      id: preset.id,
      name: preset.name,
      description: preset.description,
      scenario_id: preset.scenarioId,
      sim_mission_id: this.id(),
      config: {
        scenario_id: preset.scenarioId,
        agents: preset.agents,
        seed: preset.seed,
        horizon: preset.horizon,
        coordination: "fixed_sector",
        command_mode: "fusion",
        outage_steps: [],
        synthetic: true,
      },
      status: "draft",
      version: 1,
      created_by: "synthetic",
      created_at: now,
      updated_at: now,
      last_sim_ms: 0,
      model2_state: preset.empty ? "inactive" : "available",
      communication_state: preset.empty ? "unknown" : "nominal",
      last_event_sequence: 0,
      current_run_id: null,
    };
    const hazard =
      preset.disaster === "wildfire" ? "fire" : preset.disaster === "earthquake" ? "debris" : "water";
    [
      [2, 1],
      [3, 1],
      [2, 2],
      [6, 6],
      [7, 6],
      [6, 7],
      [10, 1],
      [10, 2],
      [4, 5],
    ].forEach(([x, y]) => this.buildings.add(key(x!, y!)));
    [
      [7, 2],
      [8, 3],
      [8, 4],
      [9, 4],
      [9, 5],
      [3, 7],
      [4, 7],
      [3, 8],
      [10, 8],
    ].forEach(([x, y]) => this.hazardCells.set(key(x!, y!), hazard));
    if (preset.disaster === "earthquake")
      [
        [5, 2],
        [5, 3],
      ].forEach(([x, y]) => this.hazardCells.set(key(x!, y!), "structural_damage"));
    if (preset.disaster === "wildfire")
      [
        [1, 8],
        [2, 8],
      ].forEach(([x, y]) => this.hazardCells.set(key(x!, y!), "smoke"));
    this.people = [
      [8, 2],
      [9, 7],
      [5, 8],
    ];
    this.emit(
      "MISSION_CREATED",
      "mission",
      this.mission.id,
      { name: preset.name, scenario_id: preset.scenarioId, synthetic: true },
      null,
    );
    for (let i = 0; i < preset.agents; i++) this.addDrone(i);
  }

  private id(): string {
    return uuidFrom(this.idRand);
  }

  private addDrone(i: number): void {
    const n = this.preset.agents;
    const x0 = Math.floor((i * WIDTH) / n);
    const x1 = Math.floor(((i + 1) * WIDTH) / n) - 1;
    const path: Cell[] = [];
    const sector: Cell[] = [];
    for (let x = x0; x <= x1; x++)
      for (let k = 0; k < HEIGHT; k++) {
        const y = x % 2 ? HEIGHT - 1 - k : k;
        path.push([x, y]);
        sector.push([x, y]);
      }
    const agentKey = `d${i}`;
    const sensors = ["image", "thermal", "gps", "imu", "environment", "text"].filter(
      (s) => !(s === "thermal" && this.preset.missingThermal?.includes(i)),
    );
    const agent: Agent = {
      id: this.id(),
      mission_id: this.mission.id,
      agent_key: agentKey,
      kind: "drone",
      availability: "unknown",
      reported_state: null,
      communication: "unknown",
      battery_fraction: null,
      degraded_sensors: this.preset.missingThermal?.includes(i) ? ["thermal"] : [],
      last_report_ms: null,
      location: null,
      last_location_ms: null,
    };
    this.drones.push({
      agent,
      index: i,
      pos: [...BASE],
      path,
      wp: 0,
      battery: 1,
      sensors,
      statusReports: [],
      healthReports: [],
      sector,
      lastState: "",
    });
    this.emit("AGENT_REGISTERED", "agent", agent.id, { agent_key: agentKey, synthetic: true }, null);
  }

  // ----- events ----------------------------------------------------------------------------
  onEvent(listener: (e: MissionEvent) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(
    type: string,
    resourceType: string,
    resourceId: string,
    payload: Record<string, unknown>,
    simMs: number | null = this.now,
  ): MissionEvent {
    const event: MissionEvent = {
      id: this.id(),
      mission_id: this.mission.id,
      sequence: this.events.length + 1,
      event_type: type,
      schema_version: "1",
      source: "synthetic",
      occurred_at: new Date().toISOString(),
      sim_time_ms: simMs,
      correlation_id: `synthetic-${this.tick}`,
      resource_type: resourceType,
      resource_id: resourceId,
      payload,
    };
    this.events.push(event);
    if (this.events.length > 5000) this.events.splice(0, this.events.length - 5000);
    this.mission.last_event_sequence = event.sequence;
    this.listeners.forEach((l) => l(event));
    return event;
  }

  get now(): number {
    return this.tick * TICK_MS;
  }

  get finished(): boolean {
    return this.tick >= this.preset.horizon;
  }

  // ----- lifecycle -------------------------------------------------------------------------
  control(action: "start" | "pause" | "resume" | "stop", reason: string): void {
    const s = this.mission.status;
    const allowed: Record<string, string[]> = {
      start: ["draft"],
      pause: ["running"],
      resume: ["paused"],
      stop: ["running", "paused"],
    };
    if (!allowed[action]!.includes(s)) {
      throw new ApiError("conflict", `cannot ${action} a ${s} mission`, 409, "invalid_transition");
    }
    const next = { start: "running", pause: "paused", resume: "running", stop: "stopped" }[
      action
    ] as Mission["status"];
    this.setStatus(next, reason);
    if (action === "start") this.mission.current_run_id = this.id();
  }

  private setStatus(next: Mission["status"], reason: string): void {
    const previous = this.mission.status;
    this.mission.status = next;
    this.mission.version++;
    this.mission.updated_at = new Date().toISOString();
    this.statusHistory.push({
      previous,
      status: next,
      actor: this.actor,
      reason,
      sim_time_ms: this.now,
      created_at: this.mission.updated_at,
    });
    const type = {
      running: previous === "paused" ? "MISSION_RESUMED" : "MISSION_STARTED",
      paused: "MISSION_PAUSED",
      stopped: "MISSION_STOPPED",
      completed: "MISSION_COMPLETED",
    }[next as "running" | "paused" | "stopped" | "completed"];
    if (type) this.emit(type, "mission", this.mission.id, { previous, status: next, reason });
  }

  // ----- simulation step -------------------------------------------------------------------
  step(): void {
    if (this.mission.status !== "running") return;
    if (this.finished) {
      this.setStatus("completed", "horizon reached");
      return;
    }
    this.tick++;
    const t = this.tick;
    const now = this.now;
    this.mission.last_sim_ms = now;
    const out = this.preset.outage;
    const down = Boolean(out && t >= out[0] && t < out[1]);
    if (down && !this.commDown) {
      this.commDown = true;
      this.mission.communication_state = "degraded";
      this.emit("COMMUNICATION_DEGRADED", "mission", this.mission.id, {
        endpoints: { command: "disconnected" },
        disconnected: this.drones.map((d) => d.agent.agent_key),
      });
    }
    if (!down && this.commDown) {
      this.commDown = false;
      this.comm.recoveries++;
      this.mission.communication_state = "nominal";
      this.emit("COMMUNICATION_RESTORED", "mission", this.mission.id, {
        endpoints: { command: "connected" },
        disconnected: [],
        queued_reports: this.linkQueue.length,
      });
    }
    const m2 = this.preset.model2Down;
    const m2Down = Boolean(m2 && t >= m2[0] && t < m2[1]);
    if (m2Down && !this.model2Down) {
      this.model2Down = true;
      this.mission.model2_state = "unavailable";
      this.emit("MODEL_2_UNAVAILABLE", "mission", this.mission.id, { state: "offline" });
    }
    if (!m2Down && this.model2Down) {
      this.model2Down = false;
      this.mission.model2_state = "available";
      this.emit("MODEL_2_RECOVERED", "mission", this.mission.id, {
        state: "active",
        queued_reports: this.model2Queue.length,
      });
    }

    for (const d of this.drones) this.moveAndSense(d, t, down);
    if (!down) {
      const queued = this.linkQueue.splice(0);
      for (const r of queued) this.deliver(r, true);
    }
    if (!this.model2Down) {
      const work = this.model2Queue.splice(0);
      for (const r of work) this.assess(r);
    }
    this.resolveDecisions();
    this.expireReviews();
    if (t % 10 === 0) this.emit("METRICS_UPDATED", "mission", this.mission.id, this.operationalMetrics());
    this.series.push({
      sim_ms: now,
      reported_fraction: this.coverage.size / (WIDTH * HEIGHT),
      observations: this.observations.length,
      agents_available: this.drones.filter((d) => d.agent.availability === "available").length,
      messages: this.comm.generated,
      delivered: this.comm.delivered,
      incidents: this.incidents.length,
      pending_reviews: this.recommendations.filter((r) => r.status === "pending").length,
    });
    if (this.series.length > 2000) this.series.shift();
  }

  private moveAndSense(d: DroneState, t: number, down: boolean): void {
    const a = d.agent;
    if (d.battery <= 0.08) {
      if (d.lastState !== "return") this.status(d, "return");
    } else {
      const target = d.path[d.wp % d.path.length]!;
      if (d.pos[0] === target[0] && d.pos[1] === target[1]) d.wp++;
      const next = d.path[d.wp % d.path.length]!;
      d.pos = [d.pos[0] + Math.sign(next[0] - d.pos[0]), d.pos[1]];
      if (d.pos[0] === next[0]) d.pos = [d.pos[0], d.pos[1] + Math.sign(next[1] - d.pos[1])];
      d.battery = Math.max(0, d.battery - 0.0055);
      if (d.lastState !== "active") this.status(d, "active");
    }
    a.availability = d.battery <= 0.08 ? "unavailable" : "available";
    a.communication = down ? "disconnected" : "connected";
    for (let dx = -1; dx <= 1; dx++)
      for (let dy = -1; dy <= 1; dy++) {
        const cx = d.pos[0] + dx;
        const cy = d.pos[1] + dy;
        if (cx >= 0 && cy >= 0 && cx < WIDTH && cy < HEIGHT && !down)
          this.coverage.set(key(cx, cy), this.now);
      }
    if (t % 2 === 0 && !down) this.health(d);
    if (t % 4 === 0) this.report(d, "environment", d.pos, "clear", 0.9);
    const h = this.hazardCells.get(key(d.pos[0], d.pos[1]));
    if (h && !this.seenHazard.has(d.agent.agent_key + key(...d.pos))) {
      this.seenHazard.add(d.agent.agent_key + key(...d.pos));
      this.report(d, "hazard", d.pos, h, 0.7 + this.rand() * 0.25);
    }
    for (const p of this.people) {
      if (Math.abs(p[0] - d.pos[0]) <= 1 && Math.abs(p[1] - d.pos[1]) <= 1 && this.rand() < 0.35) {
        const thermal = d.sensors.includes("thermal");
        this.report(
          d,
          "possible_human",
          p,
          null,
          +(thermal ? 0.5 + this.rand() * 0.4 : 0.35 + this.rand() * 0.25).toFixed(2),
        );
      }
    }
    if (this.preset.conflict && t % 9 === 0 && this.rand() < 0.5) {
      const p = this.people[Math.floor(this.rand() * this.people.length)]!;
      if (Math.abs(p[0] - d.pos[0]) <= 2 && Math.abs(p[1] - d.pos[1]) <= 2)
        this.report(d, "environment", p, "no_person_detected", 0.6);
    }
    if (this.rand() < 0.2 && this.drones.length > 1 && !down) this.comm.peer++;
  }

  private status(d: DroneState, state: string): void {
    d.lastState = state;
    const a = d.agent;
    a.reported_state = state;
    a.last_report_ms = this.now;
    d.statusReports.unshift({
      report_type: "status",
      sim_time_ms: this.now,
      state,
      battery_fraction: null,
      location: null,
      details: {},
    });
    this.emit("AGENT_STATUS_UPDATED", "agent", a.id, { agent_key: a.agent_key, reported_state: state });
  }

  private health(d: DroneState): void {
    const a = d.agent;
    const location = loc(d.pos[0], d.pos[1]);
    const previous = a.battery_fraction;
    a.battery_fraction = +d.battery.toFixed(2);
    a.location = location;
    a.last_location_ms = this.now;
    a.last_report_ms = this.now;
    d.healthReports.unshift({
      report_type: "health",
      sim_time_ms: this.now,
      state: null,
      battery_fraction: a.battery_fraction,
      location,
      details: { degraded_sensors: [...a.degraded_sensors] },
    });
    if (d.healthReports.length > 400) d.healthReports.pop();
    if (previous === null || Math.abs(previous - a.battery_fraction) >= 0.05)
      this.emit("AGENT_HEALTH_UPDATED", "agent", a.id, {
        agent_key: a.agent_key,
        battery_fraction: a.battery_fraction,
        degraded_sensors: [...a.degraded_sensors],
        reported_cell: [d.pos[0], d.pos[1]],
      });
  }

  private report(d: DroneState, kind: string, cell: Cell, label: string | null, confidence: number): void {
    this.comm.generated++;
    const pk = this.id();
    const observation: Observation = {
      id: pk,
      mission_id: this.mission.id,
      observation_id: this.id(),
      message_id: this.id(),
      reporter: d.agent.agent_key,
      kind,
      label,
      confidence: +confidence.toFixed(2),
      observed_ms: this.now,
      received_ms: this.now,
      age_ms: 0,
      stale: false,
      outcome: "pending",
      source: "synthetic",
      location: loc(cell[0], cell[1]),
    };
    const modalities =
      kind === "possible_human"
        ? ["image", "thermal", "gps"]
        : kind === "hazard"
          ? ["image", "environment", "gps"]
          : ["environment", "gps"];
    const evidence: Evidence[] = modalities
      .filter((m) => d.sensors.includes(m))
      .map((modality) => {
        const evidenceId = this.id();
        return {
          evidence_id: evidenceId,
          origin: d.agent.agent_key,
          captured_ms: this.now,
          modality,
          artifact_key: `synthetic:${evidenceId.replace(/-/g, "")}`,
          object_id: null,
        };
      });
    const pending = { observation, evidence, drone: d.agent.agent_key };
    if (this.commDown) {
      this.comm.queued++;
      this.linkQueue.push(pending);
      return;
    }
    this.deliver(pending, false);
  }

  private deliver(r: PendingReport, delayed: boolean): void {
    this.comm.delivered++;
    const latency = delayed ? this.now - r.observation.observed_ms : TICK_MS;
    this.comm.latencies.push(latency);
    if (this.comm.latencies.length > 1000) this.comm.latencies.shift();
    r.observation.received_ms = this.now;
    this.observations.push(r.observation);
    this.evidence.set(r.observation.id, r.evidence);
    if (this.observations.length > 4000) this.observations.shift();
    if (this.model2Down) {
      r.observation.outcome = "queued";
      this.model2Queue.push(r);
    } else this.assess(r);
  }

  // ----- Model 2-shaped grouping (demonstration only) --------------------------------------
  private count(k: string): void {
    this.model2Counts[k] = (this.model2Counts[k] ?? 0) + 1;
  }

  private assess(r: PendingReport): void {
    const o = r.observation;
    o.outcome = "admitted";
    this.count("admitted");
    this.emit("OBSERVATION_RECEIVED", "observation", o.id, {
      observation_id: o.observation_id,
      kind: o.kind,
      label: o.label,
      reporter: o.reporter,
      outcome: o.outcome,
    });
    if (o.kind === "hazard" && o.location) this.hazard(o);
    if (o.kind === "environment" && o.label === "no_person_detected" && o.location) {
      const inc = this.incidents.find(
        (i) => i.location && i.location.x === o.location!.x && i.location.y === o.location!.y,
      );
      if (inc) {
        inc.conflicting_observations++;
        this.incidentObservations.get(inc.id)!.push(o.id);
        this.count("contradicted");
        this.emit("EVIDENCE_GROUP_UPDATED", "incident", inc.id, {
          incident_id: inc.id,
          added_observations: [o.id],
          contradicting: true,
        });
      }
    }
    if (o.kind !== "possible_human" || !o.location) return;
    let inc = this.incidents.find(
      (i) =>
        i.location &&
        Math.abs(i.location.x - o.location!.x) + Math.abs(i.location.y - o.location!.y) <= 1 &&
        i.disposition !== "closed",
    );
    const created = !inc;
    if (!inc) {
      inc = {
        id: this.id(),
        mission_id: this.mission.id,
        revision: 0,
        category: "possible_human",
        disposition: "reported",
        priority_level: null,
        priority_reason: null,
        operator_priority: null,
        location: { ...o.location },
        opened_sim_ms: this.now,
        updated_sim_ms: this.now,
        freshness_ms: 0,
        current_recommendation_id: null,
        supporting_observations: 0,
        conflicting_observations: 0,
      };
      this.incidents.push(inc);
      this.incidentObservations.set(inc.id, []);
      this.revisions.set(inc.id, []);
      this.transitions.set(inc.id, []);
      this.count("incident_opened");
    }
    const members = this.incidentObservations.get(inc.id)!;
    const reportersBefore = new Set(
      members.map((id) => this.observations.find((x) => x.id === id)?.reporter),
    );
    members.push(o.id);
    if (o.confidence !== null && o.confidence < 0.45 && this.preset.conflict) inc.conflicting_observations++;
    else inc.supporting_observations++;
    inc.updated_sim_ms = this.now;
    this.emit("EVIDENCE_GROUP_UPDATED", "incident", inc.id, {
      incident_id: inc.id,
      added_observations: [o.id],
      distinct_reporters: [...reportersBefore, o.reporter],
    });
    const newSource = !reportersBefore.has(o.reporter);
    if (created || newSource) this.revise(inc, created);
    else this.count("corroborated");
  }

  private hazard(o: Observation): void {
    const existing = this.hazards.find(
      (h) =>
        h.label === o.label && h.location && h.location.x === o.location!.x && h.location.y === o.location!.y,
    );
    if (existing) {
      existing.report_count++;
      existing.last_reported_ms = o.observed_ms;
      if (!existing.reporters.includes(o.reporter)) existing.reporters.push(o.reporter);
      return;
    }
    const h: Hazard = {
      id: this.id(),
      label: o.label ?? "unknown",
      location: { ...o.location! },
      first_reported_ms: o.observed_ms,
      last_reported_ms: o.observed_ms,
      report_count: 1,
      reporters: [o.reporter],
      stale: false,
    };
    this.hazards.push(h);
    this.emit("HAZARD_REPORTED", "hazard", h.id, {
      label: h.label,
      cell: [h.location!.x, h.location!.y],
      reporter: o.reporter,
    });
  }

  private reportersOf(inc: Incident): string[] {
    const ids = this.incidentObservations.get(inc.id) ?? [];
    return [
      ...new Set(
        ids
          .map((id) => this.observations.find((x) => x.id === id)?.reporter)
          .filter((r): r is string => Boolean(r)),
      ),
    ];
  }

  private nearHazard(inc: Incident): boolean {
    return this.hazards.some(
      (h) =>
        h.location &&
        inc.location &&
        Math.abs(h.location.x - inc.location.x) + Math.abs(h.location.y - inc.location.y) <= 2,
    );
  }

  private revise(inc: Incident, created: boolean): void {
    const previous = inc.disposition;
    inc.revision++;
    const sources = this.reportersOf(inc).length;
    const priority =
      sources >= 2
        ? this.nearHazard(inc)
          ? "potentially_urgent"
          : "elevated"
        : this.nearHazard(inc)
          ? "elevated"
          : "review_required";
    const escalated = inc.priority_level !== null && rank(priority) > rank(inc.priority_level);
    inc.priority_level = priority;
    inc.priority_reason =
      sources >= 2
        ? `Corroborated by ${sources} independent agents (synthetic)`
        : "Single-source possible human report requires verification";
    if (!["acknowledged", "confirmed", "resolution_reported", "closed"].includes(inc.disposition))
      inc.disposition = "human_review_pending";
    this.count(created ? "opened" : "revised");
    const ids = this.incidentObservations.get(inc.id)!;
    this.revisions.get(inc.id)!.push({
      revision: inc.revision,
      category: inc.category,
      report_message_ids: ids.map((id) => this.observations.find((x) => x.id === id)?.message_id ?? id),
      uncertainties: [
        "synthetic report; human verification required",
        ...(inc.conflicting_observations ? ["contradicting observations present"] : []),
      ],
      confirmation_id: null,
      priority_level: priority,
      priority_reason: inc.priority_reason,
      sim_time_ms: this.now,
      created_at: new Date().toISOString(),
    });
    if (previous !== inc.disposition) this.transition(inc, previous, inc.disposition, "command");
    this.emit(
      created ? "INCIDENT_CREATED" : escalated ? "INCIDENT_ESCALATED" : "INCIDENT_UPDATED",
      "incident",
      inc.id,
      {
        revision: inc.revision,
        category: inc.category,
        disposition: inc.disposition,
        priority,
        priority_reason: inc.priority_reason,
      },
    );
    if (inc.disposition !== "human_review_pending") return;
    for (const r of this.recommendations) {
      if (r.incident_id === inc.id && r.status === "pending")
        this.setRecStatus(r, "superseded", `superseded by revision ${inc.revision}`);
    }
    const rec: Recommendation = {
      id: this.id(),
      mission_id: this.mission.id,
      incident_id: inc.id,
      version: inc.revision,
      request: sources >= 2 ? "review_rescue_need" : "inspect_evidence",
      evidence_ids: ids.flatMap((id) => (this.evidence.get(id) ?? []).map((e) => e.evidence_id)).slice(-12),
      unknowns: ["synthetic report; human verification required"],
      expires_ms: this.now + REVIEW_WINDOW_MS,
      status: "pending",
      created_sim_ms: this.now,
      created_at: new Date().toISOString(),
    };
    this.recommendations.push(rec);
    this.recHistory.set(rec.id, []);
    inc.current_recommendation_id = rec.id;
    const payload = {
      recommendation_id: rec.id,
      incident_id: inc.id,
      version: rec.version,
      request: rec.request,
      expires_ms: rec.expires_ms,
    };
    this.emit(
      inc.revision > 1 ? "RECOMMENDATION_REVISED" : "RECOMMENDATION_CREATED",
      "recommendation",
      rec.id,
      payload,
    );
    this.emit("HUMAN_REVIEW_REQUESTED", "recommendation", rec.id, payload);
    const alert: Alert = {
      id: this.id(),
      incident_id: inc.id,
      incident_revision: inc.revision,
      priority,
      priority_reason: inc.priority_reason,
      review_state: "human_review_pending",
      supporting_evidence: rec.evidence_ids.slice(0, 4),
      sent_sim_ms: this.now,
      acknowledged_at: null,
      acknowledged_by: null,
    };
    this.alerts.push(alert);
    this.emit("ALERT_RAISED", "alert", alert.id, {
      alert_id: alert.id,
      incident_id: inc.id,
      revision: inc.revision,
      priority,
      priority_reason: alert.priority_reason,
      review_state: alert.review_state,
    });
  }

  private transition(inc: Incident, previous: string, state: string, actor: string): void {
    this.transitions.get(inc.id)!.push({
      revision: inc.revision,
      previous,
      state,
      actor,
      reference: this.id(),
      sim_time_ms: this.now,
      created_at: new Date().toISOString(),
    });
  }

  private setRecStatus(rec: Recommendation, status: string, reason: string): void {
    this.recHistory.get(rec.id)!.push({
      previous: rec.status,
      status,
      reason,
      sim_time_ms: this.now,
      created_at: new Date().toISOString(),
    });
    rec.status = status;
  }

  private expireReviews(): void {
    for (const rec of this.recommendations) {
      if (rec.status === "pending" && rec.expires_ms <= this.now) {
        this.setRecStatus(rec, "expired", "review deadline passed");
        const inc = this.incidents.find((i) => i.id === rec.incident_id);
        if (inc && inc.disposition === "human_review_pending" && inc.current_recommendation_id === rec.id) {
          this.transition(inc, inc.disposition, "expired", "command");
          inc.disposition = "expired";
          this.count("expired");
          this.emit("INCIDENT_UPDATED", "incident", inc.id, {
            revision: inc.revision,
            category: inc.category,
            disposition: inc.disposition,
            priority: inc.priority_level,
          });
        }
      }
    }
  }

  // ----- human decisions (synthetic only; never sent to the backend) -----------------------
  submitRecommendationDecision(
    recId: string,
    action: "approve_review" | "confirm_rescue_need" | "reject" | "correct",
    version: number,
    reason: string,
    idempotencyKey?: string,
  ): Decision {
    const prior = idempotencyKey ? this.decisions.find((d) => d.message_id === idempotencyKey) : undefined;
    if (prior) {
      if (prior.action !== action)
        throw new ApiError(
          "conflict",
          "idempotency key reused for a different request",
          409,
          "idempotency_conflict",
        );
      return prior;
    }
    const rec = this.recommendations.find((r) => r.id === recId);
    if (!rec) throw new ApiError("not_found", "recommendation not found", 404, "not_found");
    const inc = this.incidents.find((i) => i.id === rec.incident_id)!;
    if (this.versionConflictArmed && rec.status === "pending") {
      this.versionConflictArmed = false;
      this.revise(inc, false); // a new Model 2 revision lands just before the decision
    }
    if (rec.version !== version || inc.revision !== rec.version) {
      throw new ApiError("conflict", "recommendation version is outdated", 409, "stale_version", null, {
        submitted_version: version,
        recommendation_version: rec.version,
        incident_revision: inc.revision,
      });
    }
    if (rec.status !== "pending")
      throw new ApiError("conflict", `recommendation is ${rec.status}`, 409, "recommendation_not_pending");
    if (rec.expires_ms <= this.now)
      throw new ApiError("conflict", "recommendation has expired", 409, "expired");
    if (this.mission.status !== "running" && this.mission.status !== "paused")
      throw new ApiError("conflict", "mission is not active", 409, "mission_not_active");
    const decision = this.decision(
      action === "correct" ? "incident_review" : "approval",
      action,
      inc.id,
      rec.id,
      rec.version,
      reason,
      idempotencyKey,
    );
    return decision;
  }

  submitIncidentAction(
    incId: string,
    action: "approve_review" | "prioritize" | "resolve" | "close" | "correct",
    revision: number,
    reason: string,
    idempotencyKey?: string,
  ): Decision {
    const inc = this.incidents.find((i) => i.id === incId);
    if (!inc) throw new ApiError("not_found", "incident not found", 404, "not_found");
    if (action === "approve_review") {
      const rec = this.recommendations.find((r) => r.incident_id === incId && r.status === "pending");
      if (!rec)
        throw new ApiError(
          "conflict",
          "incident has no recommendation awaiting review",
          409,
          "no_pending_review",
        );
      return this.submitRecommendationDecision(rec.id, "approve_review", revision, reason, idempotencyKey);
    }
    if (inc.revision !== revision)
      throw new ApiError("conflict", "incident revision is outdated", 409, "stale_version", null, {
        submitted: revision,
        current: inc.revision,
      });
    if (inc.disposition === "closed")
      throw new ApiError("conflict", "incident is closed", 409, "incident_closed");
    if (action === "close" && inc.disposition !== "resolution_reported")
      throw new ApiError(
        "conflict",
        "closure requires a prior human resolution report",
        409,
        "resolution_required",
      );
    if (this.mission.status !== "running" && this.mission.status !== "paused")
      throw new ApiError("conflict", "mission is not active", 409, "mission_not_active");
    return this.decision("incident_review", action, inc.id, null, revision, reason, idempotencyKey);
  }

  private decision(
    kind: string,
    action: string,
    incidentId: string | null,
    recId: string | null,
    revision: number | null,
    reason: string,
    key?: string,
  ): Decision {
    const d: Decision = {
      id: this.id(),
      mission_id: this.mission.id,
      kind,
      action,
      incident_id: incidentId,
      recommendation_id: recId,
      expected_revision: revision,
      actor_user_id: "00000000-0000-4000-8000-000000000000",
      actor_role: "synthetic",
      reason,
      message_id: key ?? null,
      status: "submitted",
      outcome_reason: null,
      sim_time_ms: this.now,
      submitted_at: new Date().toISOString(),
      resolved_at: null,
    };
    this.decisions.unshift(d);
    this.pendingDecisions.push(d);
    return d;
  }

  /** Synthetic validator: resolves on the next tick (as Model 2 does on the next cycle). */
  private resolveDecisions(): void {
    if (this.model2Down) return;
    for (const d of this.pendingDecisions.splice(0)) {
      const inc = this.incidents.find((i) => i.id === d.incident_id);
      const rec = this.recommendations.find((r) => r.id === d.recommendation_id);
      let status: "accepted" | "rejected" = "accepted";
      let reason = "validated (synthetic)";
      if (!inc || inc.revision !== d.expected_revision || (rec && rec.status !== "pending")) {
        status = "rejected";
        reason = "validation_stale_revision";
      }
      if (status === "accepted" && inc) {
        const previous = inc.disposition;
        if (d.action === "approve_review" || d.action === "confirm_rescue_need" || d.action === "reject") {
          const recStatus =
            d.action === "approve_review"
              ? "approved"
              : d.action === "confirm_rescue_need"
                ? "confirmed"
                : "rejected";
          inc.disposition =
            d.action === "approve_review"
              ? "acknowledged"
              : d.action === "confirm_rescue_need"
                ? "confirmed"
                : "rejected";
          if (rec) this.setRecStatus(rec, recStatus, `operator decision ${d.id}`);
          this.emit(
            recStatus === "rejected" ? "RECOMMENDATION_REJECTED" : "RECOMMENDATION_APPROVED",
            "recommendation",
            rec?.id ?? "",
            { recommendation_id: rec?.id, status: recStatus, decision: d.id },
          );
        } else if (d.action === "correct") {
          inc.disposition = "corrected";
          if (rec) this.setRecStatus(rec, "revision_requested", `operator correction ${d.id}`);
          this.requestRevisit(inc);
        } else if (d.action === "prioritize") {
          inc.operator_priority = "prioritized";
        } else if (d.action === "resolve") {
          inc.disposition = "resolution_reported";
        } else if (d.action === "close") {
          inc.disposition = "closed";
        }
        if (previous !== inc.disposition) {
          inc.revision++;
          this.transition(inc, previous, inc.disposition, "operator");
          this.emit("INCIDENT_UPDATED", "incident", inc.id, {
            revision: inc.revision,
            category: inc.category,
            disposition: inc.disposition,
            priority: inc.priority_level,
          });
        }
      }
      d.status = status;
      d.outcome_reason = reason;
      d.resolved_at = new Date().toISOString();
      this.emit("HUMAN_DECISION_RESOLVED", "human_decision", d.id, {
        decision_id: d.id,
        kind: d.kind,
        action: d.action,
        status,
        reason,
        incident_id: d.incident_id,
        recommendation_id: d.recommendation_id,
      });
    }
  }

  private requestRevisit(inc: Incident): void {
    if (!inc.location || this.drones.length === 0) return;
    const target = inc.location;
    const nearest = this.drones.reduce((a, b) =>
      Math.abs(a.pos[0] - target.x) + Math.abs(a.pos[1] - target.y) <=
      Math.abs(b.pos[0] - target.x) + Math.abs(b.pos[1] - target.y)
        ? a
        : b,
    );
    nearest.path.splice(nearest.wp % nearest.path.length, 0, [target.x, target.y]);
    const task: Task = {
      id: this.id(),
      member: nearest.agent.agent_key,
      target: loc(target.x, target.y, null),
      category: "verify_location",
      coordinator_state: "assigned",
      reported_status: null,
      reported_ms: null,
      knowledge: "coordinator_known",
      created_ms: this.now,
      expires_ms: this.now + 3000,
      updated_ms: this.now,
    };
    this.tasks.unshift(task);
    this.taskEvents.set(task.id, [
      {
        sim_time_ms: this.now,
        state: "assigned",
        reason: "human requested additional observation",
        source: "coordinator",
      },
    ]);
    this.emit("TASK_UPDATED", "task", task.id, {
      task_id: task.id,
      member: task.member,
      coordinator_state: "assigned",
      reported_status: null,
      target: [target.x, target.y],
    });
  }

  acknowledgeAlert(alertId: string): Alert {
    const alert = this.alerts.find((a) => a.id === alertId);
    if (!alert) throw new ApiError("not_found", "alert not found", 404, "not_found");
    if (!alert.acknowledged_at) {
      alert.acknowledged_at = new Date().toISOString();
      alert.acknowledged_by = "00000000-0000-4000-8000-000000000000";
    }
    return alert;
  }

  // ----- derived read models ---------------------------------------------------------------
  sectorTasks(): Task[] {
    const sectorTasks: Task[] = this.drones.map((d) => ({
      id: `${this.mission.id}-sector-${d.index}`,
      member: d.agent.agent_key,
      target: loc(d.sector[0]![0], d.sector[0]![1], null),
      category: "search_sector",
      coordinator_state:
        this.mission.status === "draft"
          ? "pending"
          : d.agent.availability === "unavailable"
            ? "expired"
            : "assigned",
      reported_status: d.lastState === "active" ? "accepted" : null,
      reported_ms: d.agent.last_report_ms,
      knowledge:
        d.agent.communication === "disconnected"
          ? "stale"
          : d.agent.last_report_ms === null
            ? "unknown"
            : "reported",
      created_ms: 0,
      expires_ms: this.preset.horizon * TICK_MS,
      updated_ms: d.agent.last_report_ms ?? 0,
    }));
    return [...this.tasks, ...sectorTasks];
  }

  sectorCells(): { member: string; cells: [number, number][] }[] {
    return this.drones.map((d) => ({
      member: d.agent.agent_key,
      cells: d.sector.map(([x, y]) => [x, y] as [number, number]),
    }));
  }

  freshen(): void {
    const now = this.now;
    for (const o of this.observations) {
      o.age_ms = Math.max(0, now - o.observed_ms);
      o.stale = o.age_ms >= FRESHNESS_MS;
    }
    for (const h of this.hazards) h.stale = now - h.last_reported_ms >= FRESHNESS_MS;
    for (const i of this.incidents) i.freshness_ms = Math.max(0, now - i.updated_sim_ms);
    for (const d of this.drones) {
      if (
        d.agent.last_report_ms !== null &&
        now - d.agent.last_report_ms >= FRESHNESS_MS &&
        d.agent.availability === "available"
      )
        d.agent.availability = "stale";
    }
  }

  operationalMetrics(): Record<string, unknown> {
    const lat = [...this.comm.latencies].sort((a, b) => a - b);
    return {
      sim_time_ms: this.now,
      model2_counts: { ...this.model2Counts },
      incidents: this.incidents.length,
      admitted_findings: this.observations.filter((o) => o.outcome === "admitted").length,
      communication: {
        generated: this.comm.generated,
        delivered: this.comm.delivered,
        dropped: 0,
        expired: this.comm.expired,
        pending: this.linkQueue.length,
        delivery_ratio: this.comm.generated ? this.comm.delivered / this.comm.generated : null,
        duplicate: this.comm.duplicates,
        connection_lost: this.preset.outage && this.tick >= this.preset.outage[0] ? 1 : 0,
        connection_restored: this.comm.recoveries,
        mean_ms: lat.length ? lat.reduce((a, b) => a + b, 0) / lat.length : null,
        median_ms: lat.length ? lat[Math.floor(lat.length / 2)]! : null,
        p95_ms: lat.length ? lat[Math.floor(lat.length * 0.95)]! : null,
        peer_messages: this.comm.peer,
      },
      tasks_issued: this.tasks.length + this.drones.length,
      reported_cells: this.coverage.size,
      synthetic: true,
    };
  }
}

function rank(priority: string | null): number {
  return priority === "potentially_urgent" ? 2 : priority === "elevated" ? 1 : 0;
}
