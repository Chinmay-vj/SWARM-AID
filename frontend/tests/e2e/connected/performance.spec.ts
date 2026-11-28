import { mkdirSync, writeFileSync } from "node:fs";
import os from "node:os";
import { expect, test } from "@playwright/test";

/**
 * Local performance observations (not a scalability claim). Runs one real mission per agent
 * count through the dashboard and records counts, browser-measured API timings, JS heap and
 * long tasks. Output: ../runs/frontend/phase8-performance.json (git-ignored).
 */
const PASSWORD = process.env.E2E_PASSWORD ?? "";
test.skip(
  !PASSWORD || !process.env.E2E_PERF,
  "Set E2E_PASSWORD and E2E_PERF=1 to run performance observations",
);
test.setTimeout(600_000);

test("dashboard behaviour with 3, 6, 10 and 20 agents", async ({ page, request }) => {
  const login = await request.post("/api/v1/auth/login", {
    data: { username: "coordinator", password: PASSWORD },
  });
  const token = (await login.json()).access_token as string;
  const h = { Authorization: `Bearer ${token}` };
  await page.goto("/login");
  await page.getByLabel(/Connected simulation/).check();
  await page.getByLabel("Username").fill("coordinator");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Missions", exact: true })).toBeVisible();
  await page.evaluate(() => {
    (window as unknown as { __longTasks: number[] }).__longTasks = [];
    new PerformanceObserver((list) =>
      list
        .getEntries()
        .forEach((e) => (window as unknown as { __longTasks: number[] }).__longTasks.push(e.duration)),
    ).observe({ type: "longtask", buffered: true });
  });
  const results = [];
  for (const agents of [3, 6, 10, 20]) {
    const created = await request.post("/api/v1/missions", {
      headers: h,
      data: {
        name: `perf ${agents} agents`,
        config: { scenario_id: "flood_basic", agents, seed: 12986, horizon: 150 },
      },
    });
    expect(created.status()).toBe(201);
    const mission = await created.json();
    // Navigate inside the SPA so the in-memory session is kept.
    await page.evaluate((path) => {
      window.history.pushState({}, "", path);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }, `/missions/${mission.id}/overview`);
    await expect(page.getByRole("heading", { name: mission.name })).toBeVisible();
    await page.evaluate(() => {
      performance.clearResourceTimings();
      (window as unknown as { __longTasks: number[] }).__longTasks = [];
    });
    expect(
      (
        await request.post(`/api/v1/missions/${mission.id}/start`, { headers: h, data: { reason: "perf" } })
      ).status(),
    ).toBe(200);
    await page.waitForTimeout(15_000);
    const t0 = Date.now();
    await page.getByRole("link", { name: "Live simulation map" }).click();
    await expect(page.getByRole("table", { name: "Map entities" })).toBeVisible();
    const mapNavigationMs = Date.now() - t0;
    const browser = await page.evaluate(() => {
      const api = performance
        .getEntriesByType("resource")
        .filter((e) => e.name.includes("/api/v1/"))
        .map((e) => e.duration)
        .sort((a, b) => a - b);
      const mem = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory;
      const tasks = (window as unknown as { __longTasks: number[] }).__longTasks;
      return {
        apiRequests: api.length,
        apiP50Ms: api.length ? Math.round(api[Math.floor(api.length / 2)]!) : null,
        apiP95Ms: api.length ? Math.round(api[Math.floor(api.length * 0.95)]!) : null,
        jsHeapMb: mem ? Math.round((mem.usedJSHeapSize / 1048576) * 10) / 10 : null,
        longTasks: tasks.length,
        longestTaskMs: tasks.length ? Math.round(Math.max(...tasks)) : 0,
        streamStatus:
          document.querySelector('[aria-label="System status"]')?.textContent?.includes("Live events●open") ??
          false,
      };
    });
    const m = await (await request.get(`/api/v1/missions/${mission.id}`, { headers: h })).json();
    const summary = await (
      await request.get(`/api/v1/missions/${mission.id}/summary`, { headers: h })
    ).json();
    await request.post(`/api/v1/missions/${mission.id}/stop`, { headers: h, data: { reason: "perf done" } });
    results.push({
      agents,
      simTimeMs: m.last_sim_ms,
      events: m.last_event_sequence,
      observations: summary.observations,
      incidents: Object.values(summary.incidents_by_disposition as Record<string, number>).reduce(
        (a, b) => a + b,
        0,
      ),
      mapNavigationMs,
      ...browser,
    });
  }
  const report = {
    recordedAt: new Date().toISOString(),
    hardware: {
      cpus: os.cpus().length,
      cpuModel: os.cpus()[0]?.model,
      memoryGb: Math.round(os.totalmem() / 1e9),
      platform: `${os.platform()} ${os.release()}`,
    },
    backend: "SQLite, SWARM_SIMULATION_TICK_DELAY_MS=100, single uvicorn worker on the same machine",
    window: "15 s of wall-clock simulation per agent count, overview page open, then map navigation",
    results,
  };
  mkdirSync("../runs/frontend", { recursive: true });
  writeFileSync("../runs/frontend/phase8-performance.json", JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
});
