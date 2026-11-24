/**
 * Synthetic Demo Mode data source. Fully isolated from the backend: it performs no network
 * requests, and decisions only change in-browser demonstration state.
 */
import type {
  Agent,
  Decision,
  Me,
  Mission,
  MissionEvent,
  MissionMap,
  MissionRole,
  Page,
  ScenarioInfo,
} from "../../../contracts/api";
import { ApiError, unavailable } from "../../api/errors";
import { can, type Permission } from "../../../lib/permissions";
import { toCsv } from "../../../lib/csv";
import type { DataProvider, PageQuery, StreamHandlers } from "../types";
import { SyntheticMission, HEIGHT, TICK_MS, WIDTH } from "./engine";
import { SYNTHETIC_PRESETS } from "./scenarios";

const SYNTHETIC_USER_ID = "00000000-0000-4000-8000-000000000000";

function page<T>(items: T[], q: PageQuery = {}): Page<T> {
  const limit = q.limit ?? 50;
  const offset = q.offset ?? 0;
  return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
}

export interface SyntheticOptions {
  /** Base real-time milliseconds per simulation tick at 1× speed. */
  tickIntervalMs?: number;
}

export class SyntheticProvider implements DataProvider {
  readonly mode = "synthetic" as const;
  readonly sourceLabel = "SYNTHETIC demonstration data";
  private missionsById = new Map<string, SyntheticMission>();
  private role: MissionRole = "coordinator";
  private signedIn = false;
  private timer: ReturnType<typeof setInterval> | null = null;
  private speed = 1;
  private readonly baseInterval: number;

  constructor(options: SyntheticOptions = {}) {
    this.baseInterval = options.tickIntervalMs ?? 400;
    this.reset();
  }

  /** Reset every demonstration mission to its initial state. */
  reset(): void {
    this.stopTimer();
    this.missionsById = new Map(SYNTHETIC_PRESETS.map((p) => [p.id, new SyntheticMission(p)]));
  }

  resetMission(id: string): void {
    const preset = SYNTHETIC_PRESETS.find((p) => p.id === id);
    if (!preset) return;
    this.missionsById.set(id, new SyntheticMission(preset));
    this.syncTimer();
  }

  setSpeed(speed: number): void {
    this.speed = Math.max(0.25, Math.min(8, speed));
    if (this.timer) {
      this.stopTimer();
      this.syncTimer();
    }
  }

  setRole(role: MissionRole): void {
    this.role = role;
  }

  /** Advance every running mission by n ticks (used by tests and step controls). */
  advance(ticks = 1): void {
    for (let i = 0; i < ticks; i++) this.missionsById.forEach((m) => m.step());
  }

  private stopTimer(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  private syncTimer(): void {
    const anyRunning = [...this.missionsById.values()].some((m) => m.mission.status === "running");
    if (anyRunning && !this.timer)
      this.timer = setInterval(() => this.advance(1), this.baseInterval / this.speed);
    if (!anyRunning) this.stopTimer();
  }

  private identity(): Me {
    return {
      subject: `synthetic-${this.role}`,
      kind: "human",
      user_id: SYNTHETIC_USER_ID,
      global_role: this.role === "coordinator" ? "coordinator" : this.role,
      memberships: SYNTHETIC_PRESETS.map((p) => ({ mission_id: p.id, role: this.role })),
      machine_mission: null,
    };
  }

  private m(id: string): SyntheticMission {
    if (!this.signedIn) throw new ApiError("unauthenticated", "Not signed in", 401);
    const mission = this.missionsById.get(id);
    if (!mission) throw new ApiError("not_found", "mission not found", 404, "not_found");
    if (mission.preset.backendFailure)
      throw new ApiError("network", "Synthetic backend failure (demonstration)");
    mission.freshen();
    return mission;
  }

  private require(permission: Permission, missionId: string): void {
    if (!can(this.identity(), permission, missionId))
      throw new ApiError("forbidden", "not permitted for this mission", 403, "permission_denied");
  }

  private find<T>(
    pick: (m: SyntheticMission) => T | undefined,
    what: string,
  ): { mission: SyntheticMission; item: T } {
    for (const mission of this.missionsById.values()) {
      if (mission.preset.backendFailure) continue;
      const item = pick(mission);
      if (item !== undefined) {
        mission.freshen();
        return { mission, item };
      }
    }
    throw new ApiError("not_found", `${what} not found`, 404, "not_found");
  }

  private async run<T>(fn: () => T): Promise<T> {
    await Promise.resolve();
    return fn();
  }

  // ----- auth ------------------------------------------------------------------------------
  login = (_username: string, _password: string) =>
    this.run(() => {
      this.signedIn = true;
      return this.identity();
    });
  logout = () =>
    this.run(() => {
      this.signedIn = false;
      this.stopTimer();
    });
  me = () =>
    this.run(() => {
      if (!this.signedIn) throw new ApiError("unauthenticated", "Not signed in", 401);
      return this.identity();
    });

  // ----- catalog ---------------------------------------------------------------------------
  scenarios = () =>
    this.run((): ScenarioInfo[] =>
      [...new Map(SYNTHETIC_PRESETS.map((p) => [p.scenarioId, p])).values()].map((p) => ({
        scenario_id: p.scenarioId,
        disaster: p.disaster,
        width: WIDTH,
        height: HEIGHT,
        default_agents: 6,
        default_seed: p.seed,
        horizon: p.horizon,
        tick_ms: TICK_MS,
        modalities: ["image", "thermal", "gps", "imu", "environment", "text"],
        faults: [],
      })),
    );
  experiments = () => Promise.reject(unavailable("Stored experiment results (measured research data)"));
  experiment = () => Promise.reject(unavailable("Stored experiment results (measured research data)"));
  users = () => Promise.reject(unavailable("User administration"));

  // ----- missions --------------------------------------------------------------------------
  missions = (q: PageQuery & { status?: string }) =>
    this.run(() => {
      if (!this.signedIn) throw new ApiError("unauthenticated", "Not signed in", 401);
      const items = [...this.missionsById.values()]
        .map((m) => m.mission)
        .filter((m) => !q.status || m.status === q.status);
      return page(items, q);
    });
  mission = (id: string) => this.run(() => ({ ...this.m(id).mission }));
  createMission = () => Promise.reject(unavailable("Creating missions (synthetic presets are fixed)"));
  controlMission = (id: string, action: "start" | "pause" | "resume" | "stop", reason: string) =>
    this.run((): Mission => {
      this.require("mission.control", id);
      const m = this.m(id);
      m.control(action, reason);
      this.syncTimer();
      return { ...m.mission };
    });
  summary = (id: string) =>
    this.run(() => {
      const m = this.m(id);
      const byDisposition: Record<string, number> = {};
      m.incidents.forEach((i) => (byDisposition[i.disposition] = (byDisposition[i.disposition] ?? 0) + 1));
      const tasks = m.sectorTasks();
      const byState: Record<string, number> = {};
      tasks.forEach((t) => (byState[t.coordinator_state] = (byState[t.coordinator_state] ?? 0) + 1));
      return {
        mission: { ...m.mission },
        agents: m.drones.length,
        agents_connected: m.drones.filter((d) => d.agent.communication === "connected").length,
        observations: m.observations.length,
        incidents_by_disposition: byDisposition,
        pending_recommendations: m.recommendations.filter((r) => r.status === "pending").length,
        open_alerts: m.alerts.filter((a) => !a.acknowledged_at).length,
        hazards: m.hazards.length,
        tasks_by_state: byState,
      };
    });
  history = (id: string) => this.run(() => [...this.m(id).statusHistory].reverse());
  metrics = (id: string) =>
    this.run(() => {
      const m = this.m(id);
      const decisions: Record<string, number> = {};
      m.decisions.forEach((d) => (decisions[d.status] = (decisions[d.status] ?? 0) + 1));
      return {
        mission_id: id,
        sim_time_ms: m.now,
        live: m.mission.status === "draft" ? null : m.operationalMetrics(),
        human_decisions: decisions,
        runs: [],
      };
    });
  events = (id: string, q: { after: number; limit: number; eventType?: string }) =>
    this.run(() =>
      this.m(id)
        .events.filter((e) => e.sequence > q.after && (!q.eventType || e.event_type === q.eventType))
        .slice(0, q.limit),
    );
  addMember = () => Promise.reject(unavailable("Mission membership management"));
  audit = () => Promise.reject(unavailable("Audit log"));
  snapshots = () => Promise.reject(unavailable("Model 2 snapshots"));
  exportMission = (id: string, kind: "operational" | "research", format: "json" | "csv") =>
    this.run(() => {
      if (kind === "research") throw unavailable("Research export with evaluator ground truth");
      this.require("export.operational", id);
      const m = this.m(id);
      const record = {
        export_kind: "operational",
        data_source: "SYNTHETIC demonstration — not measured research data",
        exported_at: new Date().toISOString(),
        reproducibility: {
          mission_id: id,
          scenario_id: m.preset.scenarioId,
          seed: m.preset.seed,
          agents: m.preset.agents,
          coordination_policy: "fixed_sector (synthetic sweep)",
          software_version: "dashboard synthetic playback 0.8.0",
        },
        observation_statistics: { total: m.observations.length },
        incident_metrics: { total: m.incidents.length },
        recommendation_metrics: { total: m.recommendations.length },
        communication_metrics: m.operationalMetrics().communication,
      };
      if (format === "json") return JSON.stringify(record, null, 2);
      const rows: unknown[][] = [];
      const walk = (prefix: string, v: unknown) => {
        if (v && typeof v === "object" && !Array.isArray(v))
          Object.entries(v).forEach(([k, x]) => walk(prefix ? `${prefix}.${k}` : k, x));
        else {
          const [section, ...rest] = prefix.split(".");
          rows.push([section, rest.join("."), v]);
        }
      };
      walk("", record);
      return toCsv(["section", "key", "value"], rows);
    });

  // ----- agents ----------------------------------------------------------------------------
  agents = (missionId: string) =>
    this.run((): Agent[] => this.m(missionId).drones.map((d) => ({ ...d.agent })));
  agent = (agentId: string) =>
    this.run(() => ({
      ...this.find((m) => m.drones.find((d) => d.agent.id === agentId)?.agent, "agent").item,
    }));
  agentReports = (agentId: string, type: "status" | "health" | "location-history", q: PageQuery) =>
    this.run(() => {
      const d = this.find((m) => m.drones.find((x) => x.agent.id === agentId), "agent").item;
      const items = type === "status" ? d.statusReports : d.healthReports;
      return page(type === "location-history" ? items.filter((r) => r.location) : items, q);
    });
  agentObservations = (agentId: string, q: PageQuery) =>
    this.run(() => {
      const { mission, item } = this.find((m) => m.drones.find((x) => x.agent.id === agentId), "agent");
      return page(mission.observations.filter((o) => o.reporter === item.agent.agent_key).reverse(), q);
    });

  // ----- observations and evidence ---------------------------------------------------------
  observations = (
    missionId: string,
    q: { kind?: string; reporter?: string; outcome?: string; since_ms?: number; sort?: string } & PageQuery,
  ) =>
    this.run(() => {
      const items = this.m(missionId).observations.filter(
        (o) =>
          (!q.kind || o.kind === q.kind) &&
          (!q.reporter || o.reporter === q.reporter) &&
          (!q.outcome || o.outcome === q.outcome) &&
          (q.since_ms === undefined || o.observed_ms >= q.since_ms),
      );
      const sorted = q.sort === "observed_ms" ? items : [...items].reverse();
      return page(sorted, q);
    });
  observation = (id: string) =>
    this.run(() => ({ ...this.find((m) => m.observations.find((o) => o.id === id), "observation").item }));
  observationEvidence = (id: string) =>
    this.run(() => this.find((m) => m.evidence.get(id), "observation").item);
  evidenceGroup = (groupId: string) =>
    this.run(() => {
      const { mission, item } = this.find((m) => m.incidents.find((i) => i.id === groupId), "evidence group");
      const observations = (mission.incidentObservations.get(item.id) ?? [])
        .map((id) => mission.observations.find((o) => o.id === id))
        .filter((o): o is NonNullable<typeof o> => Boolean(o));
      return {
        evidence_group_id: item.id,
        incident_id: item.id,
        observations,
        distinct_reporters: [...new Set(observations.map((o) => o.reporter))].sort(),
      };
    });
  evidenceObject = () => Promise.reject(unavailable("Stored evidence objects"));
  evidenceContent = () => Promise.reject(unavailable("Stored evidence content"));

  // ----- incidents -------------------------------------------------------------------------
  incidents = (
    missionId: string,
    q: { disposition?: string; category?: string; priority?: string } & PageQuery,
  ) =>
    this.run(() =>
      page(
        this.m(missionId)
          .incidents.filter(
            (i) =>
              (!q.disposition || i.disposition === q.disposition) &&
              (!q.category || i.category === q.category) &&
              (!q.priority || i.priority_level === q.priority),
          )
          .map((i) => ({ ...i }))
          .reverse(),
        q,
      ),
    );
  incident = (id: string) =>
    this.run(() => ({ ...this.find((m) => m.incidents.find((i) => i.id === id), "incident").item }));
  incidentHistory = (id: string) => this.run(() => this.find((m) => m.transitions.get(id), "incident").item);
  incidentAssessments = (id: string) =>
    this.run(() => this.find((m) => m.revisions.get(id), "incident").item);
  incidentAction = (
    id: string,
    action: "acknowledge" | "request-review" | "resolution-report" | "close",
    body: { revision: number; reason: string; idempotency_key?: string },
  ) =>
    this.run((): Decision => {
      const { mission } = this.find((m) => m.incidents.find((i) => i.id === id), "incident");
      const permission: Permission = {
        acknowledge: "incident.acknowledge",
        "request-review": "incident.request_review",
        "resolution-report": "incident.resolution_report",
        close: "incident.close",
      }[action] as Permission;
      this.require(permission, mission.mission.id);
      const mapped = {
        acknowledge: "approve_review",
        "request-review": "prioritize",
        "resolution-report": "resolve",
        close: "close",
      } as const;
      return mission.submitIncidentAction(
        id,
        mapped[action],
        body.revision,
        body.reason,
        body.idempotency_key,
      );
    });
  feedback = (
    missionId: string,
    body: {
      incident_id: string;
      action: "correct" | "prioritize";
      revision: number;
      reason: string;
      idempotency_key?: string;
    },
  ) =>
    this.run(() => {
      this.require(body.action === "correct" ? "feedback.correct" : "incident.request_review", missionId);
      return this.m(missionId).submitIncidentAction(
        body.incident_id,
        body.action,
        body.revision,
        body.reason,
        body.idempotency_key,
      );
    });

  // ----- recommendations and oversight -----------------------------------------------------
  recommendations = (missionId: string, q: { status?: string } & PageQuery) =>
    this.run(() =>
      page(
        this.m(missionId)
          .recommendations.filter((r) => !q.status || r.status === q.status)
          .map((r) => ({ ...r }))
          .reverse(),
        q,
      ),
    );
  recommendation = (id: string) =>
    this.run(() => ({
      ...this.find((m) => m.recommendations.find((r) => r.id === id), "recommendation").item,
    }));
  recommendationVersions = (id: string) =>
    this.run(() => {
      const { mission, item } = this.find(
        (m) => m.recommendations.find((r) => r.id === id),
        "recommendation",
      );
      return mission.recommendations.filter((r) => r.incident_id === item.incident_id).map((r) => ({ ...r }));
    });
  recommendationHistory = (id: string) =>
    this.run(() => this.find((m) => m.recHistory.get(id), "recommendation").item);
  recommendationEvidence = (id: string) =>
    this.run(() => {
      const { mission, item } = this.find(
        (m) => m.recommendations.find((r) => r.id === id),
        "recommendation",
      );
      const wanted = new Set(item.evidence_ids);
      return [...mission.evidence.values()].flat().filter((e) => wanted.has(e.evidence_id));
    });
  private decide(
    id: string,
    action: "approve_review" | "confirm_rescue_need" | "reject" | "correct",
    body: { version: number; reason: string; idempotency_key?: string },
  ) {
    return this.run(() => {
      const { mission } = this.find((m) => m.recommendations.find((r) => r.id === id), "recommendation");
      this.require(
        action === "confirm_rescue_need"
          ? "recommendation.confirm"
          : action === "correct"
            ? "feedback.correct"
            : "recommendation.decide",
        mission.mission.id,
      );
      return mission.submitRecommendationDecision(
        id,
        action,
        body.version,
        body.reason,
        body.idempotency_key,
      );
    });
  }
  approve = (
    id: string,
    body: { version: number; reason: string; idempotency_key?: string; confirm_rescue_need?: boolean },
  ) => this.decide(id, body.confirm_rescue_need ? "confirm_rescue_need" : "approve_review", body);
  reject = (id: string, body: { version: number; reason: string; idempotency_key?: string }) =>
    this.decide(id, "reject", body);
  requestRevision = (id: string, body: { version: number; reason: string; idempotency_key?: string }) =>
    this.decide(id, "correct", body);
  reviewQueue = (missionId: string) =>
    this.run(() => {
      const m = this.m(missionId);
      return m.recommendations
        .filter((r) => r.status === "pending")
        .map((r) => ({
          incident: { ...m.incidents.find((i) => i.id === r.incident_id)! },
          recommendation: { ...r },
          remaining_ms: Math.max(0, r.expires_ms - m.now),
        }))
        .sort((a, b) => a.remaining_ms - b.remaining_ms);
    });
  alerts = (missionId: string, q: { unacknowledged?: boolean } & PageQuery) =>
    this.run(() =>
      page(
        this.m(missionId)
          .alerts.filter((a) => !q.unacknowledged || !a.acknowledged_at)
          .map((a) => ({ ...a }))
          .reverse(),
        q,
      ),
    );
  acknowledgeAlert = (alertId: string) =>
    this.run(() => {
      const { mission } = this.find((m) => m.alerts.find((a) => a.id === alertId), "alert");
      this.require("alert.acknowledge", mission.mission.id);
      return { ...mission.acknowledgeAlert(alertId) };
    });
  decisions = (missionId: string, q: PageQuery) =>
    this.run(() =>
      page(
        this.m(missionId).decisions.map((d) => ({ ...d })),
        q,
      ),
    );
  override = () => Promise.reject(unavailable("Simulated assignment overrides"));

  // ----- coordination, environment, map ----------------------------------------------------
  tasks = (missionId: string, q: { member?: string; state?: string } & PageQuery) =>
    this.run(() =>
      page(
        this.m(missionId)
          .sectorTasks()
          .filter(
            (t) => (!q.member || t.member === q.member) && (!q.state || t.coordinator_state === q.state),
          ),
        q,
      ),
    );
  taskHistory = (taskId: string) =>
    this.run(
      () =>
        this.find(
          (m) => m.taskEvents.get(taskId) ?? (m.sectorTasks().some((t) => t.id === taskId) ? [] : undefined),
          "task",
        ).item,
    );
  sectors = (missionId: string) => this.run(() => this.m(missionId).sectorCells());
  coverage = (missionId: string) =>
    this.run(() => {
      const m = this.m(missionId);
      const cells = [...m.coverage.entries()].map(([k, ms]) => {
        const [x, y] = k.split(",").map(Number) as [number, number];
        return { cell: [x, y] as [number, number], last_reported_ms: ms, stale: m.now - ms >= 1500 };
      });
      return {
        crs: "swarm-aid:grid",
        units: "cell",
        width: WIDTH,
        height: HEIGHT,
        sim_time_ms: m.now,
        reported_cells: cells,
        reported_fraction: cells.length / (WIDTH * HEIGHT),
        unknown_cells: WIDTH * HEIGHT - cells.length,
        note: "Synthetic reported cells; not verified coverage.",
      };
    });
  conflicts = (missionId: string) => this.run(() => [...this.m(missionId).conflicts]);
  environment = (missionId: string) =>
    this.run(() => {
      const m = this.m(missionId);
      return {
        crs: "swarm-aid:grid",
        units: "cell",
        snapshot_sim_ms: m.now,
        source: "Synthetic demonstration world model",
        cells: [],
        hazards: m.hazards.map((h) => ({ ...h })),
      };
    });
  hazards = (missionId: string) => this.run(() => this.m(missionId).hazards.map((h) => ({ ...h })));
  map = (missionId: string) =>
    this.run((): MissionMap => {
      const m = this.m(missionId);
      return {
        crs: "swarm-aid:grid",
        units: "cell",
        width: WIDTH,
        height: HEIGHT,
        map_ref: m.preset.scenarioId,
        sim_time_ms: m.now,
        layers: [
          {
            name: "agents",
            description: "Last reported agent positions (synthetic)",
            features: m.drones.map((d) => ({
              id: d.agent.agent_key,
              layer: "agents",
              location: d.agent.location,
              properties: {
                communication: d.agent.communication,
                availability: d.agent.availability,
                last_location_ms: d.agent.last_location_ms,
                stale: d.agent.last_location_ms === null || m.now - d.agent.last_location_ms >= 1500,
              },
            })),
          },
          {
            name: "incidents",
            description: "Synthetic incidents",
            features: m.incidents.map((i) => ({
              id: i.id,
              layer: "incidents",
              location: i.location,
              properties: { category: i.category, disposition: i.disposition, priority: i.priority_level },
            })),
          },
          {
            name: "hazards",
            description: "Reported hazards (synthetic)",
            features: m.hazards.map((h) => ({
              id: h.id,
              layer: "hazards",
              location: h.location,
              properties: { label: h.label, reports: h.report_count, stale: h.stale },
            })),
          },
          {
            name: "stale_observations",
            description: "Sightings older than the freshness window",
            features: m.observations
              .filter((o) => o.kind === "possible_human" && o.stale)
              .slice(-40)
              .map((o) => ({
                id: o.id,
                layer: "stale_observations",
                location: o.location,
                properties: { observed_ms: o.observed_ms, reporter: o.reporter },
              })),
          },
          {
            name: "sectors",
            description: "Search sectors",
            features: m.sectorCells().map((s) => ({
              id: s.member,
              layer: "sectors",
              location: null,
              properties: { cells: s.cells },
            })),
          },
        ],
      };
    });

  // ----- system ----------------------------------------------------------------------------
  probe = () => Promise.resolve({ live: true, ready: true });
  systemHealth = () => Promise.reject(unavailable("Backend system health"));
  systemMetrics = () => Promise.reject(unavailable("Backend system metrics"));

  // ----- real-time -------------------------------------------------------------------------
  subscribe(missionId: string, afterSequence: number, handlers: StreamHandlers) {
    const mission = this.missionsById.get(missionId);
    if (!mission || mission.preset.backendFailure) {
      handlers.onStatus("failed", "synthetic backend failure");
      return { close: () => handlers.onStatus("closed"), reconnect: () => undefined };
    }
    handlers.onStatus("open", "synthetic playback");
    mission.events
      .filter((e) => e.sequence > afterSequence)
      .forEach((e: MissionEvent) => handlers.onEvent(e));
    const off = mission.onEvent((e) => handlers.onEvent(e));
    return {
      close: () => {
        off();
        handlers.onStatus("closed");
      },
      reconnect: () => handlers.onStatus("open", "synthetic playback"),
    };
  }
}
