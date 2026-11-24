import { describe, expect, it } from "vitest";
import { escapeCsvCell, sanitizeCsvText, toCsv } from "../../src/lib/csv";
import { EventBuffer } from "../../src/lib/eventBuffer";
import { formatConfidence, formatLocation, formatSimTime, formatWallTime } from "../../src/lib/format";
import { agentCondition, classifySimAge, classifySync } from "../../src/lib/freshness";
import { drawable, fitView, toCell, toScreen, zoomAt } from "../../src/lib/grid";
import { IDEMPOTENCY_PATTERN, newIdempotencyKey } from "../../src/lib/idempotency";
import {
  can,
  canCreateMissions,
  canReadExperiments,
  canReadSystemHealth,
  permissionsFor,
} from "../../src/lib/permissions";
import { groupSummaries, numericColumns, summarize, tCritical95 } from "../../src/lib/stats";
import { statusLabel, toneFor } from "../../src/lib/status";
import { sortRows, type Column } from "../../src/components/ui/data";

describe("format", () => {
  it("formats simulation time separately from wall time", () => {
    expect(formatSimTime(0)).toBe("T+00:00.0");
    expect(formatSimTime(65_300)).toBe("T+01:05.3");
    expect(formatSimTime(null)).toBe("T+—");
    expect(formatWallTime("not-a-date")).toBe("unknown");
    expect(formatWallTime("2026-11-24T13:25:42Z", "utc")).toBe("2026-11-24 13:25:42 UTC");
  });
  it("never turns unknown confidence into zero", () => {
    expect(formatConfidence(null)).toBe("unknown");
    expect(formatConfidence(undefined)).toBe("unknown");
    expect(formatConfidence(0)).toBe("0%");
    expect(formatConfidence(0.456)).toBe("46%");
  });
  it("never turns missing coordinates into (0,0) and labels local grid", () => {
    expect(formatLocation(null)).toBe("not reported");
    expect(formatLocation({ crs: "swarm-aid:grid", x: 3, y: 4, units: "cell", uncertainty: 0.5 })).toBe(
      "cell (3, 4) · ±0.5 cell",
    );
    expect(formatLocation({ crs: "swarm-aid:grid", x: 1, y: 2, units: "cell", uncertainty: null })).toContain(
      "uncertainty unknown",
    );
  });
});

describe("freshness", () => {
  it("classifies simulation age with the backend window", () => {
    expect(classifySimAge(null, 5000)).toBe("missing");
    expect(classifySimAge(4000, 5000)).toBe("fresh");
    expect(classifySimAge(3000, 5000)).toBe("stale");
    expect(classifySimAge(4900, 5000, true)).toBe("stale");
    expect(classifySimAge(100, null)).toBe("unknown");
  });
  it("classifies wall-clock sync", () => {
    expect(classifySync(null, 1000)).toBe("unknown");
    expect(classifySync(1000, 5000)).toBe("fresh");
    expect(classifySync(1000, 60_000)).toBe("stale");
  });
  it("treats a missing heartbeat as stale or unknown, not failed", () => {
    const base = {
      availability: "available",
      communication: "connected",
      degraded_sensors: [] as string[],
      last_report_ms: 1000,
    };
    expect(agentCondition(base, 1200)).toBe("nominal");
    expect(agentCondition(base, 9000)).toBe("stale");
    expect(agentCondition({ ...base, last_report_ms: null }, 9000)).toBe("unknown");
    expect(agentCondition({ ...base, degraded_sensors: ["thermal"] }, 1200)).toBe("degraded");
    expect(agentCondition({ ...base, availability: "unavailable" }, 1200)).toBe("unavailable");
  });
});

describe("status mapping", () => {
  it("maps tones and labels", () => {
    expect(toneFor("potentially_urgent")).toBe("bad");
    expect(toneFor("pending")).toBe("warn");
    expect(toneFor(null)).toBe("muted");
    expect(toneFor("something_new")).toBe("info");
    expect(statusLabel("human_review_pending")).toBe("review pending");
    expect(statusLabel("some_value")).toBe("some value");
  });
});

describe("permissions mirror the backend matrix", () => {
  const mission = "m1";
  const me = (
    global: "administrator" | "coordinator" | "operator" | "researcher" | "observer",
    role?: "coordinator" | "operator" | "researcher" | "observer",
  ) => ({
    global_role: global,
    memberships: role ? [{ mission_id: mission, role }] : [],
  });
  it("coordinator decides, operator cannot", () => {
    expect(can(me("coordinator", "coordinator"), "recommendation.decide", mission)).toBe(true);
    expect(can(me("operator", "operator"), "recommendation.decide", mission)).toBe(false);
    expect(can(me("operator", "operator"), "incident.acknowledge", mission)).toBe(true);
  });
  it("administrators never decide without membership", () => {
    const admin = me("administrator");
    expect(can(admin, "mission.read", mission)).toBe(true);
    expect(can(admin, "recommendation.decide", mission)).toBe(false);
    expect(can(admin, "mission.control", mission)).toBe(false);
  });
  it("mission scope: no permission for other missions", () => {
    expect(permissionsFor(me("coordinator", "coordinator"), "other").size).toBe(0);
  });
  it("research exports and global capabilities", () => {
    expect(can(me("researcher", "researcher"), "export.research", mission)).toBe(true);
    expect(can(me("coordinator", "coordinator"), "export.research", mission)).toBe(false);
    expect(canCreateMissions({ global_role: "operator" })).toBe(false);
    expect(canCreateMissions({ global_role: "coordinator" })).toBe(true);
    expect(canReadSystemHealth({ global_role: "coordinator" })).toBe(false);
    expect(canReadExperiments({ global_role: "researcher" })).toBe(true);
  });
});

describe("statistics", () => {
  it("summarizes measured values and excludes missing ones", () => {
    const s = summarize([1, 2, 3, null, 4]);
    expect(s.n).toBe(4);
    expect(s.missing).toBe(1);
    expect(s.mean).toBe(2.5);
    expect(s.median).toBe(2.5);
    expect(s.sd).toBeCloseTo(1.29099, 4);
    expect(s.ci95![0]).toBeCloseTo(2.5 - (3.182 * 1.29099) / 2, 3);
  });
  it("gives no interval for one sample and nothing for no samples", () => {
    expect(summarize([5]).ci95).toBeNull();
    expect(summarize([]).mean).toBeNull();
    expect(tCritical95(100)).toBe(1.96);
  });
  it("groups rows and finds numeric columns", () => {
    const rows = [
      { scenario: "f", policy: "a", coverage: 0.1, seed: 1 },
      { scenario: "f", policy: "a", coverage: 0.3, seed: 2 },
      { scenario: "f", policy: "b", coverage: 0.5, seed: 1 },
    ];
    const g = groupSummaries(rows, ["scenario", "policy"], "coverage");
    expect(g).toHaveLength(2);
    expect(g[0]!.summary.mean).toBeCloseTo(0.2);
    expect(numericColumns(rows, ["scenario", "coverage", "seed"])).toEqual(["coverage", "seed"]);
  });
});

describe("CSV export safety", () => {
  it("neutralises formula injection but keeps numbers", () => {
    expect(escapeCsvCell("=HYPERLINK(1)")).toBe("'=HYPERLINK(1)");
    expect(escapeCsvCell("+cmd")).toBe("'+cmd");
    expect(escapeCsvCell("@SUM(A1)")).toBe("'@SUM(A1)");
    expect(escapeCsvCell("-5")).toBe("-5");
    expect(escapeCsvCell('a,"b"')).toBe('"a,""b"""');
    expect(escapeCsvCell(null)).toBe("");
  });
  it("re-encodes backend CSV", () => {
    const out = sanitizeCsvText("section,key,value\r\nmission_summary,name,=1+1\r\n");
    expect(out).toBe("section,key,value\r\nmission_summary,name,'=1+1\r\n");
    expect(toCsv(["a"], [[1]])).toBe("a\r\n1\r\n");
  });
});

describe("event buffer", () => {
  const ev = (sequence: number) => ({ sequence });
  it("drops duplicates and orders out-of-order events", () => {
    const b = new EventBuffer(0);
    expect(b.offer(ev(1))).toEqual({ kind: "applied", events: [ev(1)] });
    expect(b.offer(ev(1)).kind).toBe("duplicate");
    expect(b.offer(ev(3)).kind).toBe("held");
    expect(b.offer(ev(3)).kind).toBe("duplicate");
    const r = b.offer(ev(2));
    expect(r).toEqual({ kind: "applied", events: [ev(2), ev(3)] });
    expect(b.lastApplied).toBe(3);
  });
  it("reports a persistent gap for resynchronization", () => {
    const b = new EventBuffer(0, 100, 2);
    b.offer(ev(5));
    b.offer(ev(6));
    expect(b.offer(ev(7))).toEqual({ kind: "gap", after: 0 });
    b.resetTo(6);
    expect(b.heldCount).toBe(1);
    expect(b.offer(ev(7)).kind).toBe("duplicate");
  });
  it("replays a batch and bounds history", () => {
    const b = new EventBuffer(0, 3);
    expect(b.replay([ev(2), ev(1), ev(3), ev(4)]).map((e) => e.sequence)).toEqual([1, 2, 3, 4]);
    expect(b.recent.map((e) => e.sequence)).toEqual([4, 3, 2]);
  });
});

describe("grid geometry", () => {
  it("round-trips screen and cell coordinates", () => {
    const view = { scale: 40, tx: 10, ty: 20 };
    const [sx, sy] = toScreen(view, 3, 2);
    expect([sx, sy]).toEqual([150, 120]);
    expect(toCell(view, sx, sy)).toEqual([3, 2]);
  });
  it("fits and zooms around an anchor", () => {
    const v = fitView(12, 10, 500, 420, 10);
    expect(v.scale).toBe(40);
    const z = zoomAt(v, 2, 100, 100);
    expect(z.scale).toBe(80);
    expect(toCell(z, 100, 100)[0]).toBeCloseTo(toCell(v, 100, 100)[0]);
  });
  it("rejects missing, geographic and out-of-bounds locations", () => {
    expect(drawable(null, 12, 10)).toBe(false);
    expect(drawable({ crs: "EPSG:4326", x: 1, y: 1, units: "degree" }, 12, 10)).toBe(false);
    expect(drawable({ crs: "swarm-aid:grid", x: 12, y: 1, units: "cell" }, 12, 10)).toBe(false);
    expect(drawable({ crs: "swarm-aid:grid", x: 0, y: 0, units: "cell" }, 12, 10)).toBe(true);
  });
});

describe("idempotency and sorting", () => {
  it("creates backend-compatible keys", () => {
    const a = newIdempotencyKey();
    expect(a).toMatch(IDEMPOTENCY_PATTERN);
    expect(newIdempotencyKey()).not.toBe(a);
  });
  it("sorts unknown values last in both directions", () => {
    const cols: Column<{ v: number | null }>[] = [
      { key: "v", header: "v", cell: () => null, sort: (r) => r.v },
    ];
    const rows = [{ v: 2 }, { v: null }, { v: 1 }];
    expect(sortRows(rows, cols, { key: "v", dir: "asc" }).map((r) => r.v)).toEqual([1, 2, null]);
    expect(sortRows(rows, cols, { key: "v", dir: "desc" }).map((r) => r.v)).toEqual([2, 1, null]);
  });
});

describe("post-sign-in redirect", () => {
  it("accepts only same-application paths", async () => {
    const { safeRedirect } = await import("../../src/lib/redirect");
    expect(safeRedirect("/missions/abc/overview?x=1")).toBe("/missions/abc/overview?x=1");
    for (const bad of [
      "//evil.example",
      "/\\evil.example",
      "https://evil.example",
      "/javascript:alert(1)",
      "evil",
      "/a\\b",
      "/a\tb",
      "/a\u0000b",
      42,
      null,
    ]) {
      expect(safeRedirect(bad)).toBe("/missions");
    }
  });
});
