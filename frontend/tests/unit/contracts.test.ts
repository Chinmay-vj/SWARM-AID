import { describe, expect, it } from "vitest";
import {
  AgentSchema,
  IncidentSchema,
  MapSchema,
  MissionSchema,
  ObservationSchema,
  ReviewItemSchema,
  pageOf,
} from "../../src/contracts/api";
import { describeEvent, eventResourcePath, eventSeverity, eventTopic } from "../../src/contracts/events";
import { pulsesFor } from "../../src/features/communication/CommunicationPage";
import { diffRecommendations } from "../../src/features/recommendations/RecommendationDetailPage";
import { scopesForEvents } from "../../src/hooks/useMissionStream";
import { clientApiStats } from "../../src/features/system-health/HealthPage";
import { normalizePath } from "../../src/stores/connection";

// Shapes captured from the running Phase 7 backend (see docs/frontend/API_INTEGRATION.md).
const location = { crs: "swarm-aid:grid", x: 6, y: 6, units: "cell", uncertainty: 0.5, map_ref: null };
const mission = {
  id: "3375d81f-5ae3-4eec-948f-fc753c12730b",
  name: "Probe flood",
  description: "",
  scenario_id: "flood_basic",
  sim_mission_id: "fb7096a0-e6c7-5d76-99ac-09a4f148eb3c",
  config: { scenario_id: "flood_basic", agents: 6, seed: 42 },
  status: "stopped",
  version: 3,
  created_by: "387ea4b3-243d-4324-94da-d3afa8eb696d",
  created_at: "2026-11-24T13:25:42.924589Z",
  updated_at: "2026-11-24T13:25:51.962210Z",
  last_sim_ms: 4400,
  model2_state: "available",
  communication_state: "nominal",
  last_event_sequence: 739,
  current_run_id: null,
};
const incident = {
  id: "eb7da302-506b-5acd-9cde-958b9c5fe955",
  mission_id: mission.id,
  revision: 4,
  category: "possible_human",
  disposition: "human_review_pending",
  priority_level: "elevated",
  priority_reason: "Possible human presence requires verification",
  operator_priority: null,
  location,
  opened_sim_ms: 2500,
  updated_sim_ms: 4100,
  freshness_ms: 300,
  current_recommendation_id: "09ae460c-983b-5672-8716-1bd75a972ab7",
  supporting_observations: 4,
  conflicting_observations: 0,
};
const rec = {
  id: "09ae460c-983b-5672-8716-1bd75a972ab7",
  mission_id: mission.id,
  incident_id: incident.id,
  version: 4,
  request: "inspect_evidence",
  evidence_ids: ["a", "b"],
  unknowns: ["synthetic report; human verification required"],
  expires_ms: 5100,
  status: "pending",
  created_sim_ms: 4100,
  created_at: "2026-11-24T13:25:51.173088Z",
};

describe("runtime contract validation", () => {
  it("accepts real backend shapes", () => {
    expect(MissionSchema.safeParse(mission).success).toBe(true);
    expect(ReviewItemSchema.safeParse({ incident, recommendation: rec, remaining_ms: 700 }).success).toBe(
      true,
    );
    expect(
      pageOf(IncidentSchema).safeParse({ items: [incident], total: 1, limit: 50, offset: 0 }).success,
    ).toBe(true);
  });
  it("rejects incompatible responses instead of rendering wrong data", () => {
    expect(MissionSchema.safeParse({ ...mission, status: "exploded" }).success).toBe(false);
    expect(IncidentSchema.safeParse({ ...incident, revision: "4" }).success).toBe(false);
    expect(ObservationSchema.safeParse({ id: "x" }).success).toBe(false);
  });
  it("keeps unknown values unknown", () => {
    const agent = AgentSchema.parse({
      id: "a",
      mission_id: "m",
      agent_key: "d0",
      kind: "drone",
      availability: "unknown",
      reported_state: null,
      communication: "unknown",
      battery_fraction: null,
      degraded_sensors: [],
      last_report_ms: null,
      location: null,
      last_location_ms: null,
    });
    expect(agent.battery_fraction).toBeNull();
    expect(agent.location).toBeNull();
  });
  it("validates map responses", () => {
    expect(
      MapSchema.safeParse({
        crs: "swarm-aid:grid",
        units: "cell",
        width: 12,
        height: 10,
        map_ref: "flood_basic",
        sim_time_ms: 0,
        layers: [],
      }).success,
    ).toBe(true);
    expect(
      MapSchema.safeParse({
        crs: "swarm-aid:grid",
        units: "cell",
        width: 0,
        height: 10,
        map_ref: "f",
        sim_time_ms: 0,
        layers: [],
      }).success,
    ).toBe(false);
  });
});

describe("event vocabulary", () => {
  const e = (event_type: string, payload: Record<string, unknown> = {}) => ({
    event_type,
    payload,
    source: "s",
    resource_type: "incident",
    resource_id: "i1",
    sequence: 1,
  });
  it("describes events from structured payloads only", () => {
    expect(
      describeEvent(
        e("HUMAN_DECISION_RESOLVED", {
          action: "approve_review",
          status: "accepted",
          reason: "validated by Model 2",
        }),
      ),
    ).toBe("Human decision approve_review accepted by Model 2 validator (validated by Model 2)");
    expect(describeEvent(e("SOMETHING_NEW"))).toBe("something new");
  });
  it("maps severity, topics, routes and invalidation scopes", () => {
    expect(eventSeverity(e("MODEL_2_UNAVAILABLE"))).toBe("critical");
    expect(eventSeverity(e("HUMAN_DECISION_RESOLVED", { status: "rejected" }))).toBe("warning");
    expect(eventTopic("TASK_UPDATED")).toBe("coverage");
    expect(eventResourcePath("m", e("INCIDENT_CREATED"))).toBe("/missions/m/incidents/i1");
    expect(scopesForEvents([{ event_type: "HUMAN_DECISION_RESOLVED" }]).has("review")).toBe(true);
  });
  it("animates communication pulses only for received events", () => {
    expect(
      pulsesFor([{ event_type: "OBSERVATION_RECEIVED", payload: { reporter: "d1" }, sequence: 1 }]),
    ).toEqual([{ from: "d1", to: "command", color: "var(--accent)" }]);
    expect(pulsesFor([{ event_type: "METRICS_UPDATED", payload: {}, sequence: 2 }])).toEqual([]);
  });
});

describe("recommendation versions", () => {
  it("diffs two versions", () => {
    const d = diffRecommendations(rec, {
      ...rec,
      version: 5,
      request: "review_rescue_need",
      evidence_ids: ["b", "c"],
    });
    expect(d.request).toEqual({ from: "inspect_evidence", to: "review_rescue_need" });
    expect(d.added).toEqual(["c"]);
    expect(d.removed).toEqual(["a"]);
    expect(d.status).toBeNull();
  });
});

describe("client metrics", () => {
  it("computes latency percentiles and error rate", () => {
    const s = clientApiStats([
      { status: 200, ms: 10 },
      { status: 500, ms: 30 },
      { status: null, ms: 50 },
      { status: 404, ms: 20 },
    ]);
    expect(s.p50).toBe(30);
    expect(s.errorRate).toBe(0.5);
    expect(s.clientErrors).toBe(1);
    expect(normalizePath("/api/v1/missions/3375d81f-5ae3-4eec-948f-fc753c12730b/map")).toBe(
      "/api/v1/missions/{id}/map",
    );
  });
});
