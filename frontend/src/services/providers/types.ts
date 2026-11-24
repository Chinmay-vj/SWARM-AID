/**
 * The single data interface used by the UI. Two independent implementations exist:
 *   - ConnectedProvider: the Phase 7 backend (REST + WebSocket).
 *   - SyntheticProvider: deterministic in-browser demonstration playback.
 * They never share state or caches; query keys are prefixed with the provider mode.
 * Methods a source cannot support reject with ApiError kind "unavailable".
 */
import type {
  Agent,
  AgentReport,
  Alert,
  AuditEntry,
  CoordinationConflict,
  Coverage,
  Decision,
  DecisionBody,
  Environment,
  Evidence,
  EvidenceGroup,
  EvidenceObject,
  ExperimentDetail,
  ExperimentInfo,
  Hazard,
  Incident,
  IncidentAction,
  IncidentActionBody,
  IncidentRevision,
  IncidentTransition,
  LifecycleAction,
  Me,
  Mission,
  MissionCreateBody,
  MissionEvent,
  MissionMap,
  MissionMetrics,
  MissionSummary,
  Observation,
  Page,
  Recommendation,
  RecommendationStatusChange,
  ReviewItem,
  ScenarioInfo,
  Sector,
  Snapshot,
  StatusHistory,
  SystemHealth,
  SystemMetrics,
  Task,
  TaskEvent,
  User,
} from "../../contracts/api";

export type DataMode = "connected" | "synthetic";

export interface PageQuery {
  limit?: number;
  offset?: number;
}

export interface ObservationQuery extends PageQuery {
  kind?: string;
  reporter?: string;
  outcome?: string;
  since_ms?: number;
  sort?: "observed_ms" | "-observed_ms";
}

export interface IncidentQuery extends PageQuery {
  disposition?: string;
  category?: string;
  priority?: string;
}

export interface TaskQuery extends PageQuery {
  member?: string;
  state?: string;
}

export type StreamStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed" | "failed" | "polling";

export interface StreamHandlers {
  onEvent(event: MissionEvent): void;
  onStatus(status: StreamStatus, detail?: string): void;
  /** The server asked for (or a gap requires) a full snapshot refresh. */
  onResync(lastSequence: number): void;
}

export interface Subscription {
  close(): void;
  reconnect(): void;
}

export type ExportKind = "operational" | "research";
export type ExportFormat = "json" | "csv";

export interface HealthProbe {
  live: boolean;
  ready: boolean | null;
}

export interface DataProvider {
  readonly mode: DataMode;
  /** Shown in the UI next to every value from this source. */
  readonly sourceLabel: string;

  // auth
  login(username: string, password: string): Promise<Me>;
  logout(): Promise<void>;
  me(): Promise<Me>;

  // catalog
  scenarios(signal?: AbortSignal): Promise<ScenarioInfo[]>;
  experiments(signal?: AbortSignal): Promise<ExperimentInfo[]>;
  experiment(id: string, signal?: AbortSignal): Promise<ExperimentDetail>;
  users(signal?: AbortSignal): Promise<Page<User>>;

  // missions
  missions(q: PageQuery & { status?: string }, signal?: AbortSignal): Promise<Page<Mission>>;
  mission(id: string, signal?: AbortSignal): Promise<Mission>;
  createMission(body: MissionCreateBody): Promise<Mission>;
  controlMission(id: string, action: LifecycleAction, reason: string): Promise<Mission>;
  summary(id: string, signal?: AbortSignal): Promise<MissionSummary>;
  history(id: string, signal?: AbortSignal): Promise<StatusHistory[]>;
  metrics(id: string, signal?: AbortSignal): Promise<MissionMetrics>;
  events(
    id: string,
    q: { after: number; limit: number; eventType?: string },
    signal?: AbortSignal,
  ): Promise<MissionEvent[]>;
  addMember(id: string, userId: string, role: string): Promise<void>;
  audit(id: string, q: PageQuery, signal?: AbortSignal): Promise<Page<AuditEntry>>;
  snapshots(id: string, signal?: AbortSignal): Promise<Snapshot[]>;
  exportMission(id: string, kind: ExportKind, format: ExportFormat): Promise<string>;

  // agents
  agents(missionId: string, signal?: AbortSignal): Promise<Agent[]>;
  agent(agentId: string, signal?: AbortSignal): Promise<Agent>;
  agentReports(
    agentId: string,
    type: "status" | "health" | "location-history",
    q: PageQuery,
    signal?: AbortSignal,
  ): Promise<Page<AgentReport>>;
  agentObservations(agentId: string, q: PageQuery, signal?: AbortSignal): Promise<Page<Observation>>;

  // observations and evidence
  observations(missionId: string, q: ObservationQuery, signal?: AbortSignal): Promise<Page<Observation>>;
  observation(id: string, signal?: AbortSignal): Promise<Observation>;
  observationEvidence(id: string, signal?: AbortSignal): Promise<Evidence[]>;
  evidenceGroup(groupId: string, signal?: AbortSignal): Promise<EvidenceGroup>;
  evidenceObject(objectId: string, signal?: AbortSignal): Promise<EvidenceObject>;
  /** Authorized evidence content (backend-controlled reference; never an arbitrary URL). */
  evidenceContent(objectId: string, signal?: AbortSignal): Promise<Blob>;

  // incidents
  incidents(missionId: string, q: IncidentQuery, signal?: AbortSignal): Promise<Page<Incident>>;
  incident(id: string, signal?: AbortSignal): Promise<Incident>;
  incidentHistory(id: string, signal?: AbortSignal): Promise<IncidentTransition[]>;
  incidentAssessments(id: string, signal?: AbortSignal): Promise<IncidentRevision[]>;
  incidentAction(id: string, action: IncidentAction, body: IncidentActionBody): Promise<Decision>;
  feedback(
    missionId: string,
    body: IncidentActionBody & { incident_id: string; action: "correct" | "prioritize" },
  ): Promise<Decision>;

  // recommendations and oversight
  recommendations(
    missionId: string,
    q: PageQuery & { status?: string },
    signal?: AbortSignal,
  ): Promise<Page<Recommendation>>;
  recommendation(id: string, signal?: AbortSignal): Promise<Recommendation>;
  recommendationVersions(id: string, signal?: AbortSignal): Promise<Recommendation[]>;
  recommendationHistory(id: string, signal?: AbortSignal): Promise<RecommendationStatusChange[]>;
  recommendationEvidence(id: string, signal?: AbortSignal): Promise<Evidence[]>;
  approve(id: string, body: DecisionBody & { confirm_rescue_need?: boolean }): Promise<Decision>;
  reject(id: string, body: DecisionBody): Promise<Decision>;
  requestRevision(id: string, body: DecisionBody): Promise<Decision>;
  reviewQueue(missionId: string, signal?: AbortSignal): Promise<ReviewItem[]>;
  alerts(
    missionId: string,
    q: PageQuery & { unacknowledged?: boolean },
    signal?: AbortSignal,
  ): Promise<Page<Alert>>;
  acknowledgeAlert(alertId: string, reason: string): Promise<Alert>;
  decisions(missionId: string, q: PageQuery, signal?: AbortSignal): Promise<Page<Decision>>;
  override(
    missionId: string,
    body: { action: "pause" | "resume" | "end"; reason: string; idempotency_key?: string },
  ): Promise<Decision>;

  // coordination, environment, map
  tasks(missionId: string, q: TaskQuery, signal?: AbortSignal): Promise<Page<Task>>;
  taskHistory(taskId: string, signal?: AbortSignal): Promise<TaskEvent[]>;
  sectors(missionId: string, signal?: AbortSignal): Promise<Sector[]>;
  coverage(missionId: string, signal?: AbortSignal): Promise<Coverage>;
  conflicts(missionId: string, signal?: AbortSignal): Promise<CoordinationConflict[]>;
  environment(missionId: string, signal?: AbortSignal): Promise<Environment>;
  hazards(missionId: string, signal?: AbortSignal): Promise<Hazard[]>;
  map(missionId: string, signal?: AbortSignal): Promise<MissionMap>;

  // system
  probe(signal?: AbortSignal): Promise<HealthProbe>;
  systemHealth(signal?: AbortSignal): Promise<SystemHealth>;
  systemMetrics(signal?: AbortSignal): Promise<SystemMetrics>;

  // real-time
  subscribe(missionId: string, afterSequence: number, handlers: StreamHandlers): Subscription;
}
