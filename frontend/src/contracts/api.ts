/**
 * Runtime contracts for the Phase 7 backend (backend/schemas.py, OpenAPI at /openapi.json).
 *
 * Every response is validated before use. Unknown keys are allowed (forward compatible
 * additions) but required fields, types and enums are enforced; a mismatch surfaces as a
 * schema-incompatibility error instead of silently rendering wrong data.
 *
 * Nullable fields stay nullable: unknown confidence is never coerced to 0 and missing
 * coordinates are never coerced to (0,0).
 */
import { z } from "zod";

const uuid = z.string().uuid();
const isoDate = z.string().min(10);

export const LocationSchema = z.object({
  crs: z.string(),
  x: z.number(),
  y: z.number(),
  units: z.string(),
  uncertainty: z.number().nonnegative().nullable().optional(),
  map_ref: z.string().nullable().optional(),
});
export type Location = z.infer<typeof LocationSchema>;

export const pageOf = <T extends z.ZodTypeAny>(item: T) =>
  z.object({
    items: z.array(item),
    total: z.number().int(),
    limit: z.number().int(),
    offset: z.number().int(),
  });
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export const ErrorResponseSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    request_id: z.string(),
    details: z.unknown().optional(),
  }),
});

// ----- auth ----------------------------------------------------------------------------------
export const GLOBAL_ROLES = ["administrator", "coordinator", "operator", "researcher", "observer"] as const;
export const MISSION_ROLES = ["coordinator", "operator", "researcher", "observer"] as const;
export type GlobalRole = (typeof GLOBAL_ROLES)[number];
export type MissionRole = (typeof MISSION_ROLES)[number];

export const TokenResponseSchema = z.object({
  access_token: z.string().min(1),
  refresh_token: z.string().min(1),
  token_type: z.literal("bearer"),
  access_expires_at: isoDate,
  refresh_expires_at: isoDate,
});
export type TokenResponse = z.infer<typeof TokenResponseSchema>;

export const MeSchema = z.object({
  subject: z.string(),
  kind: z.string(),
  user_id: uuid.nullable(),
  global_role: z.enum(GLOBAL_ROLES).nullable(),
  memberships: z.array(z.object({ mission_id: uuid, role: z.enum(MISSION_ROLES) })),
  machine_mission: uuid.nullable(),
});
export type Me = z.infer<typeof MeSchema>;

export const UserSchema = z.object({
  id: uuid,
  username: z.string(),
  display_name: z.string(),
  global_role: z.string(),
  is_active: z.boolean(),
  created_at: isoDate,
});
export type User = z.infer<typeof UserSchema>;

export const MembershipSchema = z.object({
  id: uuid,
  mission_id: uuid,
  user_id: uuid,
  role: z.string(),
  granted_by: z.string(),
  created_at: isoDate,
});

// ----- catalog -------------------------------------------------------------------------------
export const ScenarioInfoSchema = z.object({
  scenario_id: z.string(),
  disaster: z.string(),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  default_agents: z.number().int().positive(),
  default_seed: z.number().int(),
  horizon: z.number().int().positive(),
  tick_ms: z.number().int().positive(),
  modalities: z.array(z.string()),
  faults: z.array(z.string()),
});
export type ScenarioInfo = z.infer<typeof ScenarioInfoSchema>;

const cell = z.union([z.string(), z.number()]);
export const ExperimentInfoSchema = z.object({
  experiment_id: z.string(),
  family: z.enum(["coordination", "command"]),
  collection: z.string(),
  created_at: isoDate,
  episodes: z.number().int(),
  columns: z.array(z.string()),
  rows: z.number().int(),
  simulator_version: z.string().nullable().optional(),
  definitions: z.record(z.string()).nullable().optional(),
});
export type ExperimentInfo = z.infer<typeof ExperimentInfoSchema>;
export const ExperimentDetailSchema = ExperimentInfoSchema.extend({ data: z.array(z.record(cell)) });
export type ExperimentDetail = z.infer<typeof ExperimentDetailSchema>;

// ----- missions ------------------------------------------------------------------------------
export const MISSION_STATUSES = ["draft", "running", "paused", "completed", "stopped", "failed"] as const;
export type MissionStatus = (typeof MISSION_STATUSES)[number];
export const COORDINATION_POLICIES = ["independent", "fixed_sector", "shared_information"] as const;
export const COMMAND_MODES = ["direct", "rules", "fusion"] as const;

export const MissionConfigSchema = z.object({
  scenario_id: z.string(),
  agents: z.number().int().min(1).max(20),
  seed: z.number().int().min(0),
  horizon: z.number().int().positive().nullable().optional(),
  coordination: z.enum(COORDINATION_POLICIES),
  command_mode: z.enum(COMMAND_MODES),
  outage_steps: z.array(z.number().int().nonnegative()).optional(),
});
export type MissionConfig = z.infer<typeof MissionConfigSchema>;

export const MissionSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  scenario_id: z.string(),
  sim_mission_id: z.string(),
  config: z.record(z.unknown()),
  status: z.enum(MISSION_STATUSES),
  version: z.number().int(),
  created_by: z.string(),
  created_at: isoDate,
  updated_at: isoDate,
  last_sim_ms: z.number().int(),
  model2_state: z.string(),
  communication_state: z.string(),
  last_event_sequence: z.number().int(),
  current_run_id: z.string().nullable().optional(),
});
export type Mission = z.infer<typeof MissionSchema>;

export const MissionSummarySchema = z.object({
  mission: MissionSchema,
  agents: z.number().int(),
  agents_connected: z.number().int(),
  observations: z.number().int(),
  incidents_by_disposition: z.record(z.number().int()),
  pending_recommendations: z.number().int(),
  open_alerts: z.number().int(),
  hazards: z.number().int(),
  tasks_by_state: z.record(z.number().int()),
});
export type MissionSummary = z.infer<typeof MissionSummarySchema>;

export const StatusHistorySchema = z.object({
  previous: z.string(),
  status: z.string(),
  actor: z.string(),
  reason: z.string(),
  sim_time_ms: z.number().int().nullable(),
  created_at: isoDate,
});
export type StatusHistory = z.infer<typeof StatusHistorySchema>;

const CommunicationMetricsSchema = z
  .object({
    generated: z.number().optional(),
    delivered: z.number().optional(),
    dropped: z.number().optional(),
    expired: z.number().optional(),
    pending: z.number().optional(),
    delivery_ratio: z.number().nullable().optional(),
    rejected: z.number().optional(),
    duplicate: z.number().optional(),
    overflow: z.number().optional(),
    acknowledged: z.number().optional(),
    connection_lost: z.number().optional(),
    connection_restored: z.number().optional(),
    mean_ms: z.number().nullable().optional(),
    median_ms: z.number().nullable().optional(),
    p95_ms: z.number().nullable().optional(),
    recovery_ms: z.array(z.number()).optional(),
    availability: z.number().nullable().optional(),
  })
  .passthrough();
export type CommunicationMetrics = z.infer<typeof CommunicationMetricsSchema>;

const OperationalMetricsSchema = z
  .object({
    sim_time_ms: z.number().optional(),
    model2_counts: z.record(z.number()).optional(),
    incidents: z.number().optional(),
    admitted_findings: z.number().optional(),
    communication: CommunicationMetricsSchema.optional(),
    communication_full: CommunicationMetricsSchema.nullable().optional(),
    tasks_issued: z.number().optional(),
    reported_cells: z.number().optional(),
  })
  .passthrough();
export type OperationalMetrics = z.infer<typeof OperationalMetricsSchema>;

export const MissionMetricsSchema = z.object({
  mission_id: z.string(),
  sim_time_ms: z.number(),
  live: OperationalMetricsSchema.nullable(),
  human_decisions: z.record(z.number()),
  runs: z.array(
    z.object({
      run_id: z.string(),
      started_at: isoDate,
      ended_at: isoDate.nullable(),
      end_reason: z.string().nullable(),
      final_sim_ms: z.number().nullable(),
      operational_metrics: OperationalMetricsSchema.nullable().optional(),
    }),
  ),
});
export type MissionMetrics = z.infer<typeof MissionMetricsSchema>;

// ----- agents --------------------------------------------------------------------------------
export const AgentSchema = z.object({
  id: z.string(),
  mission_id: z.string(),
  agent_key: z.string(),
  kind: z.string(),
  availability: z.string(),
  reported_state: z.string().nullable(),
  communication: z.string(),
  battery_fraction: z.number().min(0).max(1).nullable(),
  degraded_sensors: z.array(z.string()),
  last_report_ms: z.number().int().nullable(),
  location: LocationSchema.nullable(),
  last_location_ms: z.number().int().nullable(),
});
export type Agent = z.infer<typeof AgentSchema>;

export const AgentReportSchema = z.object({
  report_type: z.string(),
  sim_time_ms: z.number().int(),
  state: z.string().nullable(),
  battery_fraction: z.number().nullable(),
  location: LocationSchema.nullable(),
  details: z.record(z.unknown()),
});
export type AgentReport = z.infer<typeof AgentReportSchema>;

// ----- observations and evidence -------------------------------------------------------------
export const OBSERVATION_KINDS = ["environment", "hazard", "possible_human"] as const;
export const ObservationSchema = z.object({
  id: z.string(),
  mission_id: z.string(),
  observation_id: z.string(),
  message_id: z.string(),
  reporter: z.string(),
  kind: z.string(),
  label: z.string().nullable(),
  confidence: z.number().min(0).max(1).nullable(),
  observed_ms: z.number().int(),
  received_ms: z.number().int(),
  age_ms: z.number().int(),
  stale: z.boolean(),
  outcome: z.string(),
  source: z.string(),
  location: LocationSchema.nullable(),
});
export type Observation = z.infer<typeof ObservationSchema>;

export const EVIDENCE_MODALITIES = [
  "image",
  "video",
  "thermal",
  "text",
  "gps",
  "imu",
  "environment",
  "peer",
] as const;
export const EvidenceSchema = z.object({
  evidence_id: z.string(),
  origin: z.string(),
  captured_ms: z.number().int(),
  modality: z.string(),
  artifact_key: z.string(),
  object_id: z.string().nullable(),
});
export type Evidence = z.infer<typeof EvidenceSchema>;

export const EvidenceGroupSchema = z.object({
  evidence_group_id: z.string(),
  incident_id: z.string(),
  observations: z.array(ObservationSchema),
  distinct_reporters: z.array(z.string()),
});
export type EvidenceGroup = z.infer<typeof EvidenceGroupSchema>;

export const EvidenceObjectSchema = z.object({
  id: z.string(),
  mission_id: z.string(),
  sha256: z.string(),
  media_type: z.string(),
  size_bytes: z.number().int(),
  source_subject: z.string(),
  created_at: isoDate,
});
export type EvidenceObject = z.infer<typeof EvidenceObjectSchema>;

// ----- incidents and recommendations ---------------------------------------------------------
export const PRIORITY_LEVELS = ["review_required", "elevated", "potentially_urgent"] as const;
export const IncidentSchema = z.object({
  id: z.string(),
  mission_id: z.string(),
  revision: z.number().int(),
  category: z.string(),
  disposition: z.string(),
  priority_level: z.string().nullable(),
  priority_reason: z.string().nullable(),
  operator_priority: z.string().nullable(),
  location: LocationSchema.nullable(),
  opened_sim_ms: z.number().int(),
  updated_sim_ms: z.number().int(),
  freshness_ms: z.number().int(),
  current_recommendation_id: z.string().nullable(),
  supporting_observations: z.number().int(),
  conflicting_observations: z.number().int(),
});
export type Incident = z.infer<typeof IncidentSchema>;

export const IncidentRevisionSchema = z.object({
  revision: z.number().int(),
  category: z.string(),
  report_message_ids: z.array(z.string()),
  uncertainties: z.array(z.string()),
  confirmation_id: z.string().nullable(),
  priority_level: z.string().nullable(),
  priority_reason: z.string().nullable(),
  sim_time_ms: z.number().int(),
  created_at: isoDate,
});
export type IncidentRevision = z.infer<typeof IncidentRevisionSchema>;

export const IncidentTransitionSchema = z.object({
  revision: z.number().int(),
  previous: z.string(),
  state: z.string(),
  actor: z.string(),
  reference: z.string(),
  sim_time_ms: z.number().int(),
  created_at: isoDate,
});
export type IncidentTransition = z.infer<typeof IncidentTransitionSchema>;

export const RecommendationSchema = z.object({
  id: z.string(),
  mission_id: z.string(),
  incident_id: z.string(),
  version: z.number().int(),
  request: z.string(),
  evidence_ids: z.array(z.string()),
  unknowns: z.array(z.string()),
  expires_ms: z.number().int(),
  status: z.string(),
  created_sim_ms: z.number().int(),
  created_at: isoDate,
});
export type Recommendation = z.infer<typeof RecommendationSchema>;

export const RecommendationStatusSchema = z.object({
  previous: z.string(),
  status: z.string(),
  reason: z.string(),
  sim_time_ms: z.number().int(),
  created_at: isoDate,
});
export type RecommendationStatusChange = z.infer<typeof RecommendationStatusSchema>;

export const DecisionSchema = z.object({
  id: z.string(),
  mission_id: z.string(),
  kind: z.string(),
  action: z.string(),
  incident_id: z.string().nullable(),
  recommendation_id: z.string().nullable(),
  expected_revision: z.number().int().nullable(),
  actor_user_id: z.string(),
  actor_role: z.string(),
  reason: z.string(),
  message_id: z.string().nullable(),
  status: z.string(),
  outcome_reason: z.string().nullable(),
  sim_time_ms: z.number().int().nullable(),
  submitted_at: isoDate,
  resolved_at: isoDate.nullable(),
});
export type Decision = z.infer<typeof DecisionSchema>;

export const AlertSchema = z.object({
  id: z.string(),
  incident_id: z.string(),
  incident_revision: z.number().int(),
  priority: z.string(),
  priority_reason: z.string(),
  review_state: z.string(),
  supporting_evidence: z.array(z.string()),
  sent_sim_ms: z.number().int(),
  acknowledged_at: isoDate.nullable(),
  acknowledged_by: z.string().nullable(),
});
export type Alert = z.infer<typeof AlertSchema>;

export const ReviewItemSchema = z.object({
  incident: IncidentSchema,
  recommendation: RecommendationSchema,
  remaining_ms: z.number().int(),
});
export type ReviewItem = z.infer<typeof ReviewItemSchema>;

// ----- coordination, environment, map --------------------------------------------------------
export const TaskSchema = z.object({
  id: z.string(),
  member: z.string(),
  target: LocationSchema,
  category: z.string(),
  coordinator_state: z.string(),
  reported_status: z.string().nullable(),
  reported_ms: z.number().int().nullable(),
  knowledge: z.enum(["coordinator_known", "reported", "conflicting", "stale", "unknown"]),
  created_ms: z.number().int(),
  expires_ms: z.number().int(),
  updated_ms: z.number().int(),
});
export type Task = z.infer<typeof TaskSchema>;

export const TaskEventSchema = z.object({
  sim_time_ms: z.number().int(),
  state: z.string(),
  reason: z.string(),
  source: z.string(),
});
export type TaskEvent = z.infer<typeof TaskEventSchema>;

export const HazardSchema = z.object({
  id: z.string(),
  label: z.string(),
  location: LocationSchema.nullable(),
  first_reported_ms: z.number().int(),
  last_reported_ms: z.number().int(),
  report_count: z.number().int(),
  reporters: z.array(z.string()),
  stale: z.boolean(),
});
export type Hazard = z.infer<typeof HazardSchema>;

const CellTuple = z.tuple([z.number().int(), z.number().int()]);
export const SectorSchema = z.object({ member: z.string(), cells: z.array(CellTuple) });
export type Sector = z.infer<typeof SectorSchema>;

export const CoverageSchema = z.object({
  crs: z.string(),
  units: z.string(),
  width: z.number().int(),
  height: z.number().int(),
  sim_time_ms: z.number().int(),
  reported_cells: z.array(
    z.object({ cell: CellTuple, last_reported_ms: z.number().int(), stale: z.boolean() }),
  ),
  reported_fraction: z.number().nullable(),
  unknown_cells: z.number().int(),
  note: z.string().optional(),
});
export type Coverage = z.infer<typeof CoverageSchema>;

export const ConflictSchema = z.object({
  source: z.string(),
  sim_time_ms: z.number().int().nullable(),
  message_id: z.string().nullable().optional(),
  reason: z.string(),
});
export type CoordinationConflict = z.infer<typeof ConflictSchema>;

export const EnvironmentSchema = z.object({
  crs: z.string(),
  units: z.string(),
  snapshot_sim_ms: z.number().int().nullable(),
  source: z.string(),
  cells: z.array(
    z.object({
      cell: z.object({ x: z.number().int(), y: z.number().int() }),
      observations: z.record(z.tuple([z.number(), z.string()])),
    }),
  ),
  hazards: z.array(HazardSchema),
});
export type Environment = z.infer<typeof EnvironmentSchema>;

export const MapFeatureSchema = z.object({
  id: z.string(),
  layer: z.string(),
  location: LocationSchema.nullable(),
  properties: z.record(z.unknown()),
});
export type MapFeature = z.infer<typeof MapFeatureSchema>;
export const MapSchema = z.object({
  crs: z.string(),
  units: z.string(),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  map_ref: z.string(),
  sim_time_ms: z.number().int(),
  layers: z.array(
    z.object({ name: z.string(), description: z.string(), features: z.array(MapFeatureSchema) }),
  ),
});
export type MissionMap = z.infer<typeof MapSchema>;

export const EventSchema = z.object({
  id: z.string(),
  mission_id: z.string(),
  sequence: z.number().int().nonnegative(),
  event_type: z.string(),
  schema_version: z.string(),
  source: z.string(),
  occurred_at: isoDate,
  sim_time_ms: z.number().int().nullable(),
  correlation_id: z.string(),
  resource_type: z.string(),
  resource_id: z.string(),
  payload: z.record(z.unknown()),
});
export type MissionEvent = z.infer<typeof EventSchema>;

export const SnapshotSchema = z.object({
  id: z.string(),
  kind: z.string(),
  schema_version: z.string(),
  sim_time_ms: z.number().int(),
  sha256: z.string(),
  complete: z.boolean(),
  created_at: isoDate,
});
export type Snapshot = z.infer<typeof SnapshotSchema>;

export const AuditSchema = z.object({
  id: z.string(),
  occurred_at: isoDate,
  actor: z.string(),
  actor_type: z.string(),
  action: z.string(),
  resource_type: z.string(),
  resource_id: z.string().nullable(),
  mission_id: z.string().nullable(),
  request_id: z.string(),
  outcome: z.string(),
  details: z.record(z.unknown()),
});
export type AuditEntry = z.infer<typeof AuditSchema>;

// ----- system health (administrator only, loosely typed by design) ---------------------------
export const SystemHealthSchema = z
  .object({
    status: z.string(),
    version: z.string(),
    environment: z.string(),
    database: z
      .object({
        dialect: z.string(),
        reachable: z.boolean(),
        migration_revision: z.string().nullable(),
        expected_revision: z.string(),
        transaction_failures: z.number(),
      })
      .passthrough(),
    simulations: z
      .object({
        active: z.number(),
        limit: z.number(),
        persistence_failures: z.number(),
        missions: z.record(z.record(z.unknown())),
      })
      .passthrough(),
    websocket: z.record(z.number()),
    authentication_failures: z.number(),
    process_peak_memory_mb: z.number().nullable(),
  })
  .passthrough();
export type SystemHealth = z.infer<typeof SystemHealthSchema>;

export const SystemMetricsSchema = z
  .object({
    api: z.record(z.unknown()),
    websocket_delivery_latency_ms: z.object({
      samples: z.number(),
      p50: z.number().nullable(),
      p95: z.number().nullable(),
    }),
    health: SystemHealthSchema,
  })
  .passthrough();
export type SystemMetrics = z.infer<typeof SystemMetricsSchema>;

// ----- request bodies ------------------------------------------------------------------------
export interface MissionCreateBody {
  name: string;
  description?: string;
  config: MissionConfig;
}
export interface DecisionBody {
  version: number;
  reason: string;
  idempotency_key?: string;
}
export interface IncidentActionBody {
  revision: number;
  reason: string;
  idempotency_key?: string;
}
export type LifecycleAction = "start" | "pause" | "resume" | "stop";
export type IncidentAction = "acknowledge" | "request-review" | "resolution-report" | "close";
export type RecommendationDecision = "approve" | "reject" | "request-revision";
