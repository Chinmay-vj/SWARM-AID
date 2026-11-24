/**
 * Connected data source: every method maps to one documented Phase 7 endpoint
 * (see docs/frontend/API_INTEGRATION.md for the inventory). No values are invented here.
 */
import { z } from "zod";
import {
  AgentReportSchema,
  AgentSchema,
  AlertSchema,
  AuditSchema,
  ConflictSchema,
  CoverageSchema,
  DecisionSchema,
  EnvironmentSchema,
  EventSchema,
  EvidenceGroupSchema,
  EvidenceObjectSchema,
  EvidenceSchema,
  ExperimentDetailSchema,
  ExperimentInfoSchema,
  HazardSchema,
  IncidentRevisionSchema,
  IncidentSchema,
  IncidentTransitionSchema,
  MapSchema,
  MeSchema,
  MembershipSchema,
  MissionMetricsSchema,
  MissionSchema,
  MissionSummarySchema,
  ObservationSchema,
  RecommendationSchema,
  RecommendationStatusSchema,
  ReviewItemSchema,
  ScenarioInfoSchema,
  SectorSchema,
  SnapshotSchema,
  StatusHistorySchema,
  SystemHealthSchema,
  SystemMetricsSchema,
  TaskEventSchema,
  TaskSchema,
  TokenResponseSchema,
  UserSchema,
  pageOf,
  type Me,
} from "../../contracts/api";
import { openMissionStream } from "../websocket/missionStream";
import type { DataProvider, HealthProbe, StreamHandlers } from "../providers/types";
import { ApiClient } from "./client";
import { ApiError } from "./errors";
import { sessionTokens } from "./tokens";

const V1 = "/api/v1";
const enc = encodeURIComponent;

export interface ConnectedOptions {
  baseUrl?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
  WebSocketImpl?: typeof WebSocket;
  observe?: ConstructorParameters<typeof ApiClient>[0]["observe"];
}

export function createConnectedProvider(
  options: ConnectedOptions = {},
): DataProvider & { client: ApiClient } {
  const client = new ApiClient({ ...options, tokens: sessionTokens });
  const get = <T>(
    path: string,
    schema: z.ZodType<T>,
    signal?: AbortSignal,
    query?: Record<string, string | number | boolean | undefined>,
  ) => client.request(path, { schema, signal, query });
  const post = <T>(path: string, body: unknown, schema: z.ZodType<T>) =>
    client.request(path, { method: "POST", body, schema });

  const wsUrl = (missionId: string) => {
    const base = client.baseUrl || window.location.origin;
    return `${base.replace(/^http/, "ws")}/ws/v1/missions/${enc(missionId)}`;
  };

  return {
    mode: "connected",
    sourceLabel: "Connected · Phase 7 backend",
    client,

    async login(username, password) {
      const tokens = await client.request("/api/v1/auth/login", {
        method: "POST",
        body: { username, password },
        schema: TokenResponseSchema,
        auth: false,
      });
      sessionTokens.update(tokens);
      return get(`${V1}/auth/me`, MeSchema);
    },
    async logout() {
      const refresh = sessionTokens.refresh();
      try {
        if (refresh && sessionTokens.access()) {
          await client.request(`${V1}/auth/logout`, { method: "POST", body: { refresh_token: refresh } });
        }
      } finally {
        sessionTokens.clear();
      }
    },
    async me(): Promise<Me> {
      if (!sessionTokens.access() && sessionTokens.refresh()) {
        if (!(await client.refreshTokens())) throw new ApiError("unauthenticated", "Session expired", 401);
      }
      return get(`${V1}/auth/me`, MeSchema);
    },

    scenarios: (signal) => get(`${V1}/scenarios`, z.array(ScenarioInfoSchema), signal),
    experiments: (signal) => get(`${V1}/experiments`, z.array(ExperimentInfoSchema), signal),
    experiment: (id, signal) => get(`${V1}/experiments/${enc(id)}`, ExperimentDetailSchema, signal),
    users: (signal) => get(`${V1}/users`, pageOf(UserSchema), signal, { limit: 500 }),

    missions: (q, signal) => get(`${V1}/missions`, pageOf(MissionSchema), signal, { ...q }),
    mission: (id, signal) => get(`${V1}/missions/${enc(id)}`, MissionSchema, signal),
    createMission: (body) => post(`${V1}/missions`, body, MissionSchema),
    controlMission: (id, action, reason) =>
      post(`${V1}/missions/${enc(id)}/${action}`, { reason }, MissionSchema),
    summary: (id, signal) => get(`${V1}/missions/${enc(id)}/summary`, MissionSummarySchema, signal),
    history: (id, signal) => get(`${V1}/missions/${enc(id)}/history`, z.array(StatusHistorySchema), signal),
    metrics: (id, signal) => get(`${V1}/missions/${enc(id)}/metrics`, MissionMetricsSchema, signal),
    events: (id, q, signal) =>
      get(`${V1}/missions/${enc(id)}/events`, z.array(EventSchema), signal, {
        after_sequence: q.after,
        limit: q.limit,
        event_type: q.eventType,
      }),
    async addMember(id, userId, role) {
      await post(`${V1}/missions/${enc(id)}/members`, { user_id: userId, role }, MembershipSchema);
    },
    audit: (id, q, signal) => get(`${V1}/missions/${enc(id)}/audit`, pageOf(AuditSchema), signal, { ...q }),
    snapshots: (id, signal) => get(`${V1}/missions/${enc(id)}/snapshots`, z.array(SnapshotSchema), signal),
    async exportMission(id, kind, format) {
      if (format === "csv")
        return client.request<string>(`${V1}/missions/${enc(id)}/exports/${kind}`, {
          query: { format },
          text: true,
        });
      const json = await client.request<unknown>(`${V1}/missions/${enc(id)}/exports/${kind}`, {
        query: { format },
      });
      return JSON.stringify(json, null, 2);
    },

    agents: (missionId, signal) =>
      get(`${V1}/missions/${enc(missionId)}/agents`, z.array(AgentSchema), signal),
    agent: (agentId, signal) => get(`${V1}/agents/${enc(agentId)}`, AgentSchema, signal),
    agentReports: (agentId, type, q, signal) =>
      get(`${V1}/agents/${enc(agentId)}/${type}`, pageOf(AgentReportSchema), signal, { ...q }),
    agentObservations: (agentId, q, signal) =>
      get(`${V1}/agents/${enc(agentId)}/observations`, pageOf(ObservationSchema), signal, { ...q }),

    observations: (missionId, q, signal) =>
      get(`${V1}/missions/${enc(missionId)}/observations`, pageOf(ObservationSchema), signal, { ...q }),
    observation: (id, signal) => get(`${V1}/observations/${enc(id)}`, ObservationSchema, signal),
    observationEvidence: (id, signal) =>
      get(`${V1}/observations/${enc(id)}/evidence`, z.array(EvidenceSchema), signal),
    evidenceGroup: (id, signal) => get(`${V1}/evidence-groups/${enc(id)}`, EvidenceGroupSchema, signal),
    evidenceObject: (id, signal) => get(`${V1}/evidence-objects/${enc(id)}`, EvidenceObjectSchema, signal),
    evidenceContent: (id, signal) =>
      client.request<Blob>(`${V1}/evidence-objects/${enc(id)}/content`, { blob: true, signal }),

    incidents: (missionId, q, signal) =>
      get(`${V1}/missions/${enc(missionId)}/incidents`, pageOf(IncidentSchema), signal, { ...q }),
    incident: (id, signal) => get(`${V1}/incidents/${enc(id)}`, IncidentSchema, signal),
    incidentHistory: (id, signal) =>
      get(`${V1}/incidents/${enc(id)}/history`, z.array(IncidentTransitionSchema), signal),
    incidentAssessments: (id, signal) =>
      get(`${V1}/incidents/${enc(id)}/assessments`, z.array(IncidentRevisionSchema), signal),
    incidentAction: (id, action, body) => post(`${V1}/incidents/${enc(id)}/${action}`, body, DecisionSchema),
    feedback: (missionId, body) =>
      post(`${V1}/missions/${enc(missionId)}/human-feedback`, body, DecisionSchema),

    recommendations: (missionId, q, signal) =>
      get(`${V1}/missions/${enc(missionId)}/recommendations`, pageOf(RecommendationSchema), signal, { ...q }),
    recommendation: (id, signal) => get(`${V1}/recommendations/${enc(id)}`, RecommendationSchema, signal),
    recommendationVersions: (id, signal) =>
      get(`${V1}/recommendations/${enc(id)}/versions`, z.array(RecommendationSchema), signal),
    recommendationHistory: (id, signal) =>
      get(`${V1}/recommendations/${enc(id)}/history`, z.array(RecommendationStatusSchema), signal),
    recommendationEvidence: (id, signal) =>
      get(`${V1}/recommendations/${enc(id)}/evidence`, z.array(EvidenceSchema), signal),
    approve: (id, body) => post(`${V1}/recommendations/${enc(id)}/approve`, body, DecisionSchema),
    reject: (id, body) => post(`${V1}/recommendations/${enc(id)}/reject`, body, DecisionSchema),
    requestRevision: (id, body) =>
      post(`${V1}/recommendations/${enc(id)}/request-revision`, body, DecisionSchema),
    reviewQueue: (missionId, signal) =>
      get(`${V1}/missions/${enc(missionId)}/review-queue`, z.array(ReviewItemSchema), signal),
    alerts: (missionId, q, signal) =>
      get(`${V1}/missions/${enc(missionId)}/alerts`, pageOf(AlertSchema), signal, { ...q }),
    acknowledgeAlert: (alertId, reason) =>
      post(`${V1}/alerts/${enc(alertId)}/acknowledge`, { reason }, AlertSchema),
    decisions: (missionId, q, signal) =>
      get(`${V1}/missions/${enc(missionId)}/human-decisions`, pageOf(DecisionSchema), signal, { ...q }),
    override: (missionId, body) => post(`${V1}/missions/${enc(missionId)}/override`, body, DecisionSchema),

    tasks: (missionId, q, signal) =>
      get(`${V1}/missions/${enc(missionId)}/tasks`, pageOf(TaskSchema), signal, { ...q }),
    taskHistory: (taskId, signal) =>
      get(`${V1}/tasks/${enc(taskId)}/history`, z.array(TaskEventSchema), signal),
    sectors: (missionId, signal) =>
      get(`${V1}/missions/${enc(missionId)}/sectors`, z.array(SectorSchema), signal),
    coverage: (missionId, signal) => get(`${V1}/missions/${enc(missionId)}/coverage`, CoverageSchema, signal),
    conflicts: (missionId, signal) =>
      get(`${V1}/missions/${enc(missionId)}/coordination-conflicts`, z.array(ConflictSchema), signal),
    environment: (missionId, signal) =>
      get(`${V1}/missions/${enc(missionId)}/environment`, EnvironmentSchema, signal),
    hazards: (missionId, signal) =>
      get(`${V1}/missions/${enc(missionId)}/hazards`, z.array(HazardSchema), signal),
    map: (missionId, signal) => get(`${V1}/missions/${enc(missionId)}/map`, MapSchema, signal),

    async probe(signal): Promise<HealthProbe> {
      try {
        await client.request("/health/live", { auth: false, signal, retries: 0 });
      } catch (e) {
        if (e instanceof ApiError && e.kind === "aborted") throw e;
        return { live: false, ready: null };
      }
      try {
        await client.request("/health/ready", { auth: false, signal, retries: 0 });
        return { live: true, ready: true };
      } catch (e) {
        if (e instanceof ApiError && e.status === 503) return { live: true, ready: false };
        return { live: true, ready: null };
      }
    },
    systemHealth: (signal) => get(`${V1}/system/health`, SystemHealthSchema, signal),
    systemMetrics: (signal) => get(`${V1}/system/metrics`, SystemMetricsSchema, signal),

    subscribe(missionId: string, afterSequence: number, handlers: StreamHandlers) {
      return openMissionStream(afterSequence, handlers, {
        url: wsUrl(missionId),
        token: () => sessionTokens.access(),
        refresh: () => client.refreshTokens(),
        poll: (after) =>
          client.request(`${V1}/missions/${enc(missionId)}/events`, {
            query: { after_sequence: after, limit: 500 },
            schema: z.array(EventSchema),
          }),
        WebSocketImpl: options.WebSocketImpl,
      });
    },
  };
}
