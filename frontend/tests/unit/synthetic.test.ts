import { describe, expect, it, vi } from "vitest";
import { SyntheticProvider } from "../../src/services/providers/synthetic/provider";
import { SyntheticMission } from "../../src/services/providers/synthetic/engine";
import { SYNTHETIC_PRESETS } from "../../src/services/providers/synthetic/scenarios";
import {
  MissionSchema,
  MapSchema,
  ReviewItemSchema,
  pageOf,
  IncidentSchema,
  EventSchema,
} from "../../src/contracts/api";

const preset = (id: string) => SYNTHETIC_PRESETS.find((p) => p.id === id)!;

async function running(id: string, ticks: number) {
  const p = new SyntheticProvider();
  await p.login("x", "y");
  await p.controlMission(id, "start", "test");
  p.advance(ticks);
  return p;
}

describe("synthetic engine", () => {
  it("is deterministic for a preset", () => {
    const a = new SyntheticMission(preset("syn-flood-6"));
    const b = new SyntheticMission(preset("syn-flood-6"));
    a.control("start", "t");
    b.control("start", "t");
    for (let i = 0; i < 80; i++) {
      a.step();
      b.step();
    }
    expect(a.observations.length).toBe(b.observations.length);
    expect(a.incidents.map((i) => [i.location?.x, i.location?.y, i.revision])).toEqual(
      b.incidents.map((i) => [i.location?.x, i.location?.y, i.revision]),
    );
  });

  it("produces records that satisfy the backend contracts", async () => {
    const p = await running("syn-flood-6", 120);
    expect(MissionSchema.safeParse(await p.mission("syn-flood-6")).success).toBe(true);
    expect(MapSchema.safeParse(await p.map("syn-flood-6")).success).toBe(true);
    expect(pageOf(IncidentSchema).safeParse(await p.incidents("syn-flood-6", {})).success).toBe(true);
    const queue = await p.reviewQueue("syn-flood-6");
    queue.forEach((q) => expect(ReviewItemSchema.safeParse(q).success).toBe(true));
    (await p.events("syn-flood-6", { after: 0, limit: 50 })).forEach((e) =>
      expect(EventSchema.safeParse(e).success).toBe(true),
    );
  });

  it("never exposes hidden synthetic truth through the map", async () => {
    const p = await running("syn-flood-6", 10);
    const map = await p.map("syn-flood-6");
    expect(map.layers.map((l) => l.name)).not.toContain("people");
    expect(JSON.stringify(map)).not.toMatch(/building|people|truth/i);
  });

  it("degrades communication, marks agents disconnected and recovers", async () => {
    const p = await running("syn-comms", 40);
    expect((await p.mission("syn-comms")).communication_state).toBe("degraded");
    expect((await p.agents("syn-comms")).every((a) => a.communication === "disconnected")).toBe(true);
    p.advance(40);
    expect((await p.mission("syn-comms")).communication_state).toBe("nominal");
    const types = (await p.events("syn-comms", { after: 0, limit: 5000 })).map((e) => e.event_type);
    expect(types).toContain("COMMUNICATION_DEGRADED");
    expect(types).toContain("COMMUNICATION_RESTORED");
  });

  it("reports Model 2 unavailability and recovery", async () => {
    const p = await running("syn-model2-down", 45);
    expect((await p.mission("syn-model2-down")).model2_state).toBe("unavailable");
    p.advance(40);
    expect((await p.mission("syn-model2-down")).model2_state).toBe("available");
  });

  it("accepts a decision only after validation and rejects stale versions", async () => {
    const p = await running("syn-flood-6", 120);
    await p.controlMission("syn-flood-6", "pause", "review");
    const [item] = await p.reviewQueue("syn-flood-6");
    expect(item).toBeDefined();
    await expect(
      p.approve(item!.recommendation.id, { version: item!.recommendation.version + 1, reason: "r" }),
    ).rejects.toMatchObject({ code: "stale_version" });
    const d = await p.approve(item!.recommendation.id, {
      version: item!.recommendation.version,
      reason: "r",
      idempotency_key: "syn:key-0001",
    });
    expect(d.status).toBe("submitted");
    const again = await p.approve(item!.recommendation.id, {
      version: item!.recommendation.version,
      reason: "r",
      idempotency_key: "syn:key-0001",
    });
    expect(again.id).toBe(d.id);
    await p.controlMission("syn-flood-6", "resume", "go");
    p.advance(1);
    const decisions = await p.decisions("syn-flood-6", {});
    expect(decisions.items[0]!.status).toBe("accepted");
    expect((await p.recommendation(item!.recommendation.id)).status).toBe("approved");
  });

  it("simulates the version-conflict scenario", async () => {
    const p = await running("syn-version", 120);
    const [item] = await p.reviewQueue("syn-version");
    await expect(
      p.approve(item!.recommendation.id, { version: item!.recommendation.version, reason: "r" }),
    ).rejects.toMatchObject({ code: "stale_version" });
  });

  it("enforces the permission matrix for the synthetic role", async () => {
    const p = new SyntheticProvider();
    p.setRole("observer");
    await p.login("x", "y");
    await expect(p.controlMission("syn-flood-6", "start", "t")).rejects.toMatchObject({ kind: "forbidden" });
  });

  it("represents backend failure and empty missions", async () => {
    const p = new SyntheticProvider();
    await p.login("x", "y");
    await expect(p.summary("syn-backend-failure")).rejects.toMatchObject({ kind: "network" });
    expect((await p.agents("syn-empty")).length).toBe(0);
    await expect(p.experiments()).rejects.toMatchObject({ kind: "unavailable" });
  });

  it("does not use the network", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    const p = await running("syn-flood-6", 30);
    await p.summary("syn-flood-6");
    await p.exportMission("syn-flood-6", "operational", "csv");
    expect(spy).not.toHaveBeenCalled();
  });

  it("labels synthetic exports and keeps research exports unavailable", async () => {
    const p = await running("syn-flood-6", 30);
    expect(await p.exportMission("syn-flood-6", "operational", "json")).toContain("SYNTHETIC");
    await expect(p.exportMission("syn-flood-6", "research", "json")).rejects.toMatchObject({
      kind: "unavailable",
    });
  });
});
