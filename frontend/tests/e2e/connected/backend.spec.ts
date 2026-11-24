import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Real-backend end-to-end tests. Requires a running Phase 7 backend (via the Vite proxy) and
 * the local development accounts. Set E2E_PASSWORD; otherwise every test is skipped (and
 * reported as skipped, not passed).
 */
const PASSWORD = process.env.E2E_PASSWORD ?? "";
test.skip(!PASSWORD, "E2E_PASSWORD not set: connected tests need the real backend and dev accounts");
test.describe.configure({ mode: "serial" });

async function token(request: APIRequestContext, username: string): Promise<string> {
  const r = await request.post("/api/v1/auth/login", { data: { username, password: PASSWORD } });
  expect(r.status()).toBe(200);
  return (await r.json()).access_token as string;
}
const auth = (t: string) => ({ Authorization: `Bearer ${t}` });

async function signIn(page: Page, username: string) {
  await page.goto("/login");
  await page.getByLabel(/Connected simulation/).check();
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Missions" })).toBeVisible();
  await expect(page.getByText("SYNTHETIC DEMO MODE.")).toHaveCount(0);
}

const status = (page: Page, label: string) =>
  page
    .getByLabel("System status")
    .locator(".tstat")
    .filter({ hasText: new RegExp(`^${label}`) });
let missionId = "";
let missionUrl = "";

test("authenticate, create a six-agent flood mission and start it", async ({ page }) => {
  await signIn(page, "coordinator");
  await page.getByRole("button", { name: "New mission" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^Name/).fill(`E2E flood ${Date.now()}`);
  await dialog.getByLabel("Scenario").selectOption("flood_basic");
  await dialog.getByLabel(/Agents/).fill("6");
  await dialog.getByLabel("Seed").fill("42");
  await dialog.getByLabel(/Horizon/).fill("400");
  await dialog.getByLabel("Model 2 mode").selectOption("fusion");
  await dialog.getByRole("button", { name: "Create mission" }).click();
  await expect(page).toHaveURL(/\/missions\/[0-9a-f-]{36}\/overview/);
  missionUrl = new URL(page.url()).pathname;
  missionId = missionUrl.split("/")[2]!;
  await expect(status(page, "Status")).toContainText("draft");
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Confirm start/ })
    .click();
  await expect(status(page, "Status")).toContainText("running");
  await expect(status(page, "Live events")).toContainText("open");
});

test("real reported positions, observations, communication events and Model 2 output", async ({ page }) => {
  await signIn(page, "coordinator");
  await page.goto(missionUrl);
  await expect
    .poll(
      async () =>
        Number(
          await page.locator(".metric").filter({ hasText: "Observations" }).locator(".value").textContent(),
        ),
      { timeout: 30_000 },
    )
    .toBeGreaterThan(10);
  await page.getByRole("link", { name: "Live simulation map" }).click();
  const entities = page.getByRole("table", { name: "Map entities" });
  await expect(
    entities
      .getByRole("row")
      .filter({ hasText: /cell \(\d+, \d+\)/ })
      .first(),
  ).toBeVisible();
  await page.getByRole("button", { name: /^Agent d0 at cell/ }).click();
  const selection = page.getByRole("region", { name: "Selection" });
  await expect(selection).toContainText("d0");
  await expect(selection).toContainText(/cell \(\d+, \d+\) · ±0\.5 cell/);
  await page.getByRole("link", { name: "Observations", exact: true }).click();
  await expect(page.getByRole("table", { name: "Observations" }).locator("tbody tr").first()).toBeVisible();
  await page.getByRole("link", { name: "Event timeline" }).click();
  await expect(page.getByText(/Observation .* from d\d/).first()).toBeVisible();
  await page.getByRole("link", { name: "Command agent (Model 2)" }).click();
  await expect(page.getByText(/Model 1 report\(s\) from/).first()).toBeVisible({ timeout: 30_000 });
});

test("pause, review a real recommendation, decide, and see it persisted and validated", async ({
  page,
  request,
}) => {
  await signIn(page, "coordinator");
  await page.goto(missionUrl);
  await expect(
    page.locator(".metric").filter({ hasText: "Pending reviews" }).locator(".value"),
  ).not.toHaveText(/^(0|—)$/, { timeout: 60_000 });
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Confirm pause/ })
    .click();
  await expect(status(page, "Status")).toContainText("paused");
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: /^Human review/ })
    .click();
  await page.getByRole("button", { name: "Approve review" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/Reason/).fill("e2e reviewed evidence");
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "Approve review" }).click();
  await expect(dialog.getByText("Decision recorded and sent to Model 2.")).toBeVisible();
  await expect(dialog.locator(".badge").filter({ hasText: "submitted" })).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).last().click();

  // Stale version: a decision bound to an outdated version is refused by the backend.
  const t = await token(request, "coordinator");
  const queue = await (
    await request.get(`/api/v1/missions/${missionId}/review-queue`, { headers: auth(t) })
  ).json();
  if (queue.length) {
    const rec = queue[0].recommendation;
    const stale = await request.post(`/api/v1/recommendations/${rec.id}/approve`, {
      headers: auth(t),
      data: { version: rec.version + 7, reason: "stale check" },
    });
    expect(stale.status()).toBe(409);
    expect((await stale.json()).error.code).toBe("stale_version");
  }

  // Resume so Model 2 validates; the persisted decision becomes accepted or rejected.
  await page.getByRole("link", { name: "Mission overview" }).click();
  await page.getByRole("button", { name: "Resume", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Confirm resume/ })
    .click();
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: /^Human review/ })
    .click();
  await page.getByRole("tab", { name: "Decision history" }).click();
  const table = page.getByRole("table", { name: "Human decisions" });
  await expect(table.locator("tbody tr").first()).toContainText(/accepted|rejected/, { timeout: 30_000 });

  // Browser refresh: the session is restored and the persisted decision is retrieved.
  await page.reload();
  await page.getByRole("tab", { name: "Decision history" }).click();
  await expect(
    page.getByRole("table", { name: "Human decisions" }).locator("tbody tr").first(),
  ).toContainText(/accepted|rejected/);
});

test("unauthorized roles: observer UI is read-only and the backend refuses actions", async ({
  page,
  request,
}) => {
  const admin = await token(request, "admin");
  const coord = await token(request, "coordinator");
  const users = await (await request.get("/api/v1/users", { headers: auth(admin) })).json();
  const observer = users.items.find((u: { username: string }) => u.username === "observer");
  const add = await request.post(`/api/v1/missions/${missionId}/members`, {
    headers: auth(coord),
    data: { user_id: observer.id, role: "observer" },
  });
  expect([201, 409]).toContain(add.status());
  const obs = await token(request, "observer");
  expect(
    (
      await request.post(`/api/v1/missions/${missionId}/pause`, { headers: auth(obs), data: { reason: "x" } })
    ).status(),
  ).toBe(403);
  await signIn(page, "observer");
  await page.goto(missionUrl);
  await expect(page.getByRole("button", { name: "Pause", exact: true })).toBeDisabled();
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: /^Human review/ })
    .click();
  await expect(page.getByText(/cannot approve or reject/)).toBeVisible();
  // Cross-mission direct URL access is refused (404 hides existence).
  await page.goto("/missions/00000000-0000-4000-8000-000000000001/overview");
  await expect(page.getByText("Mission not found")).toBeVisible();
});

test("event stream disconnect, reconnection and resynchronization", async ({ page }) => {
  // Proxy the real mission WebSocket so the test can drop it like a network failure.
  const sockets: { close: (o?: { code?: number; reason?: string }) => Promise<void> }[] = [];
  const subscribes: number[] = [];
  await page.routeWebSocket(/\/ws\/v1\/missions\//, (ws) => {
    const server = ws.connectToServer();
    sockets.push(ws);
    ws.onMessage((message) => {
      try {
        const frame = JSON.parse(String(message)) as { type?: string; after_sequence?: number };
        if (frame.type === "subscribe" && typeof frame.after_sequence === "number")
          subscribes.push(frame.after_sequence);
      } catch {
        /* not JSON */
      }
      server.send(message);
    });
  });
  await signIn(page, "coordinator");
  await page.goto(missionUrl);
  await expect(status(page, "Live events")).toContainText("open");
  await sockets.at(-1)!.close({ code: 4000, reason: "e2e network drop" });
  await expect(status(page, "Live events")).toContainText(/reconnecting|polling/, { timeout: 15_000 });
  await expect(status(page, "Live events")).toContainText("open", { timeout: 30_000 });
  expect(sockets.length).toBeGreaterThanOrEqual(2);
  // The reconnect resumes after the last applied sequence instead of replaying from zero.
  expect(subscribes.at(-1)!).toBeGreaterThanOrEqual(subscribes[0]!);
});

test("analytics, research export as researcher, and authorized exports", async ({ page, request }) => {
  const admin = await token(request, "admin");
  const coord = await token(request, "coordinator");
  const users = await (await request.get("/api/v1/users", { headers: auth(admin) })).json();
  const researcher = users.items.find((u: { username: string }) => u.username === "researcher");
  await request.post(`/api/v1/missions/${missionId}/members`, {
    headers: auth(coord),
    data: { user_id: researcher.id, role: "researcher" },
  });
  await signIn(page, "researcher");
  await page.goto(`${missionUrl.replace(/overview$/, "analytics")}`);
  await expect(page.getByRole("heading", { name: "Research analytics" })).toBeVisible();
  await expect(page.getByText("Synthetic demonstration metrics.")).toHaveCount(0);
  await expect(page.getByRole("figure").first()).toBeVisible({ timeout: 30_000 });
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "research JSON" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe(`mission-${missionId}-research.json`);
  const csvDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "operational CSV" }).click();
  expect((await csvDownload).suggestedFilename()).toMatch(/operational\.csv$/);
  await page.goto("/experiments");
  await expect(page.getByRole("heading", { name: "Experiment results" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Experiment comparison" })).toBeVisible({ timeout: 30_000 });
});

test("communication degradation and mission switching", async ({ page, request }) => {
  const coord = await token(request, "coordinator");
  const created = await request.post("/api/v1/missions", {
    headers: auth(coord),
    data: {
      name: `E2E outage ${Date.now()}`,
      config: { scenario_id: "flood_outage", agents: 6, seed: 42, horizon: 120 },
    },
  });
  expect(created.status()).toBe(201);
  const outage = await created.json();
  await signIn(page, "coordinator");
  await page.goto(`/missions/${outage.id}/overview`);
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Confirm start/ })
    .click();
  await page.getByRole("link", { name: "Communication network" }).click();
  await expect(page.getByText("Degradation and recovery history")).toBeVisible();
  await expect(
    page
      .locator("li")
      .filter({ hasText: /degraded|restored/ })
      .first(),
  ).toBeVisible({ timeout: 60_000 });
  // Switch back to the first mission: the timeline and header change scope.
  await page.goto(missionUrl);
  await expect(page.getByLabel("System status")).not.toContainText("E2E outage");
  await request.post(`/api/v1/missions/${outage.id}/stop`, {
    headers: auth(coord),
    data: { reason: "e2e cleanup" },
  });
});

test("stop the simulation and retrieve persisted information", async ({ page }) => {
  await signIn(page, "coordinator");
  await page.goto(missionUrl);
  const stop = page.getByRole("button", { name: "Stop", exact: true });
  if (await stop.isEnabled().catch(() => false)) {
    await stop.click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /Confirm stop/ })
      .click();
  }
  await expect(status(page, "Status")).toContainText(/stopped|completed/, { timeout: 30_000 });
  await page.reload();
  await expect(page.locator(".metric").filter({ hasText: "Observations" }).locator(".value")).not.toHaveText(
    "—",
  );
  await page.getByRole("link", { name: "Incidents", exact: true }).click();
  await expect(page.getByRole("table", { name: "Incidents" }).locator("tbody tr").first()).toBeVisible();
});
