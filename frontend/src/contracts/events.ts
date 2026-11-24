/**
 * Domain event vocabulary (backend/services/events.py). Topic names match the WebSocket
 * subscription topics. Unknown event types are kept and shown generically, never dropped.
 */
import type { MissionEvent } from "./api";

export const EVENT_TOPICS: Record<string, string> = {
  MISSION_CREATED: "mission",
  MISSION_STARTED: "mission",
  MISSION_PAUSED: "mission",
  MISSION_RESUMED: "mission",
  MISSION_STOPPED: "mission",
  MISSION_COMPLETED: "mission",
  AGENT_REGISTERED: "agents",
  AGENT_STATUS_UPDATED: "agents",
  AGENT_HEALTH_UPDATED: "agents",
  OBSERVATION_RECEIVED: "observations",
  EVIDENCE_GROUP_UPDATED: "incidents",
  INCIDENT_CREATED: "incidents",
  INCIDENT_UPDATED: "incidents",
  INCIDENT_ESCALATED: "incidents",
  HAZARD_REPORTED: "hazards",
  RECOMMENDATION_CREATED: "recommendations",
  RECOMMENDATION_REVISED: "recommendations",
  RECOMMENDATION_APPROVED: "recommendations",
  RECOMMENDATION_REJECTED: "recommendations",
  HUMAN_REVIEW_REQUESTED: "review",
  HUMAN_DECISION_RESOLVED: "review",
  HUMAN_OVERRIDE_RECORDED: "review",
  ALERT_RAISED: "alerts",
  TASK_UPDATED: "coverage",
  COMMUNICATION_DEGRADED: "communication",
  COMMUNICATION_RESTORED: "communication",
  MODEL_2_UNAVAILABLE: "model2",
  MODEL_2_RECOVERED: "model2",
  METRICS_UPDATED: "metrics",
};

export const ALL_TOPICS = Array.from(new Set(Object.values(EVENT_TOPICS))).sort();

export type Severity = "critical" | "warning" | "info" | "success";

const SEVERITY: Record<string, Severity> = {
  INCIDENT_ESCALATED: "critical",
  MODEL_2_UNAVAILABLE: "critical",
  MISSION_STOPPED: "warning",
  COMMUNICATION_DEGRADED: "warning",
  ALERT_RAISED: "warning",
  HUMAN_REVIEW_REQUESTED: "warning",
  RECOMMENDATION_REJECTED: "warning",
  INCIDENT_CREATED: "warning",
  HAZARD_REPORTED: "warning",
  RECOMMENDATION_APPROVED: "success",
  MODEL_2_RECOVERED: "success",
  COMMUNICATION_RESTORED: "success",
  MISSION_COMPLETED: "success",
  MISSION_STARTED: "success",
};

export function eventSeverity(event: Pick<MissionEvent, "event_type" | "payload">): Severity {
  if (event.event_type === "HUMAN_DECISION_RESOLVED") {
    return event.payload.status === "accepted" ? "success" : "warning";
  }
  if (event.event_type === "MISSION_STOPPED" && event.payload.status === "failed") return "critical";
  return SEVERITY[event.event_type] ?? "info";
}

export function eventTopic(eventType: string): string {
  return EVENT_TOPICS[eventType] ?? "other";
}

const str = (v: unknown): string => (typeof v === "string" || typeof v === "number" ? String(v) : "");

/** Plain-text description built only from structured payload fields (rendered as text). */
export function describeEvent(e: Pick<MissionEvent, "event_type" | "payload" | "source">): string {
  const p = e.payload;
  switch (e.event_type) {
    case "MISSION_CREATED":
      return `Mission created (${str(p.scenario_id)})`;
    case "MISSION_STARTED":
    case "MISSION_PAUSED":
    case "MISSION_RESUMED":
    case "MISSION_STOPPED":
    case "MISSION_COMPLETED":
      return `Mission ${str(p.previous)} → ${str(p.status)}${p.reason ? ` · ${str(p.reason)}` : ""}`;
    case "AGENT_REGISTERED":
      return `Agent ${str(p.agent_key)} registered`;
    case "AGENT_STATUS_UPDATED":
      return `Agent ${str(p.agent_key)} reports state ${str(p.reported_state)}`;
    case "AGENT_HEALTH_UPDATED": {
      const battery =
        typeof p.battery_fraction === "number" ? ` battery ${Math.round(p.battery_fraction * 100)}%` : "";
      const sensors =
        Array.isArray(p.degraded_sensors) && p.degraded_sensors.length
          ? ` · degraded: ${p.degraded_sensors.join(", ")}`
          : "";
      return `Agent ${str(p.agent_key)} health report${battery}${sensors}`;
    }
    case "OBSERVATION_RECEIVED":
      return `Observation ${str(p.kind)}${p.label ? ` (${str(p.label)})` : ""} from ${str(p.reporter)} · ${str(p.outcome)}`;
    case "EVIDENCE_GROUP_UPDATED":
      return `Evidence group updated (${Array.isArray(p.distinct_reporters) ? p.distinct_reporters.length : "?"} reporters)`;
    case "INCIDENT_CREATED":
      return `Model 2 opened ${str(p.category)} incident (revision ${str(p.revision)})`;
    case "INCIDENT_UPDATED":
      return `Model 2 revised incident to revision ${str(p.revision)} · ${str(p.disposition)}`;
    case "INCIDENT_ESCALATED":
      return `Model 2 escalated ${str(p.category)} incident (revision ${str(p.revision)}) · ${str(p.priority) || "priority unknown"}`;
    case "HAZARD_REPORTED":
      return `Hazard reported: ${str(p.label)}`;
    case "RECOMMENDATION_CREATED":
      return `Model 2 recommendation v${str(p.version)}: ${str(p.request)}`;
    case "RECOMMENDATION_REVISED":
      return `Recommendation revised to v${str(p.version)}: ${str(p.request)}`;
    case "RECOMMENDATION_APPROVED":
      return `Recommendation ${str(p.status)} after human decision`;
    case "RECOMMENDATION_REJECTED":
      return `Recommendation rejected after human decision`;
    case "HUMAN_REVIEW_REQUESTED":
      return `Human review requested for recommendation v${str(p.version)} (${str(p.request)})`;
    case "HUMAN_DECISION_RESOLVED":
      return `Human decision ${str(p.action)} ${str(p.status)} by Model 2 validator (${str(p.reason)})`;
    case "HUMAN_OVERRIDE_RECORDED":
      return `Simulated assignment override ${str(p.action)} recorded`;
    case "ALERT_RAISED":
      return `Alert: ${str(p.priority)} · ${str(p.priority_reason)}`;
    case "TASK_UPDATED":
      return `Task for ${str(p.member)}: coordinator ${str(p.coordinator_state)}${p.reported_status ? ` · reported ${str(p.reported_status)}` : ""}`;
    case "COMMUNICATION_DEGRADED":
      return "Communication degraded";
    case "COMMUNICATION_RESTORED":
      return "Communication restored";
    case "MODEL_2_UNAVAILABLE":
      return "Model 2 command agent unavailable";
    case "MODEL_2_RECOVERED":
      return "Model 2 command agent recovered";
    case "METRICS_UPDATED":
      return "Operational metrics updated";
    default:
      return `${e.event_type.toLowerCase().replace(/_/g, " ")}`;
  }
}

/** Dashboard route for the resource an event refers to, when one exists. */
export function eventResourcePath(
  missionId: string,
  e: Pick<MissionEvent, "resource_type" | "resource_id" | "payload">,
): string | null {
  switch (e.resource_type) {
    case "incident":
      return `/missions/${missionId}/incidents/${e.resource_id}`;
    case "recommendation":
      return `/missions/${missionId}/recommendations/${e.resource_id}`;
    case "agent":
      return `/missions/${missionId}/fleet/${e.resource_id}`;
    case "observation":
      return `/missions/${missionId}/observations?focus=${encodeURIComponent(e.resource_id)}`;
    case "hazard":
      return `/missions/${missionId}/environment`;
    case "alert":
    case "human_decision":
      return `/missions/${missionId}/review`;
    case "task":
      return `/missions/${missionId}/coordination`;
    default:
      return null;
  }
}

/** Events that become user notifications (others only appear in the timeline). */
export const NOTIFY_EVENTS = new Set([
  "INCIDENT_CREATED",
  "INCIDENT_ESCALATED",
  "HUMAN_REVIEW_REQUESTED",
  "RECOMMENDATION_REVISED",
  "HAZARD_REPORTED",
  "COMMUNICATION_DEGRADED",
  "COMMUNICATION_RESTORED",
  "MODEL_2_UNAVAILABLE",
  "MODEL_2_RECOVERED",
  "MISSION_STARTED",
  "MISSION_PAUSED",
  "MISSION_STOPPED",
  "MISSION_COMPLETED",
  "HUMAN_DECISION_RESOLVED",
]);
