import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Phase 9 connected integration checks against the real backend (Vite proxy):
 * Model 2 unavailability and recovery produced by the simulated transport, and contradicting
 * agent reports shown to operators as conflicting evidence. Requires E2E_PASSWORD; otherwise
 * every test is reported as skipped.
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
  await expect(page.getByRole("heading", { name: "Missions", exact: true })).toBeVisible();
}

async function mission(request: APIRequestContext, coord: string, name: string, config: object) {
  const created = await request.post("/api/v1/missions", {
    headers: auth(coord),
    data: { name: `${name} ${Date.now()}`, config },
  });
  expect(created.status()).toBe(201);
  return (await created.json()).id as string;
}

async function waitStatus(request: APIRequestContext, coord: string, id: string, wanted: RegExp) {
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/v1/missions/${id}`, { headers: auth(coord) })).json()).status,
      {
        timeout: 90_000,
      },
    )
    .toMatch(wanted);
}

test("Model 2 unavailability and recovery from a scheduled command outage are shown", async ({
  page,
  request,
}) => {
  const coord = await token(request, "coordinator");
  const id = await mission(request, coord, "E2E Model 2 outage", {
    scenario_id: "flood_server_unavailable",
    agents: 6,
    seed: 12984,
    outage_steps: [12, 13, 14, 15],
  });
  expect((await request.post(`/api/v1/missions/${id}/start`, { headers: auth(coord) })).status()).toBe(200);
  await waitStatus(request, coord, id, /completed/);
  const events = await (
    await request.get(`/api/v1/missions/${id}/events`, { headers: auth(coord), params: { limit: 1000 } })
  ).json();
  const kinds = (events as { event_type: string }[]).map((e) => e.event_type);
  expect(kinds).toContain("MODEL_2_UNAVAILABLE");
  expect(kinds.indexOf("MODEL_2_UNAVAILABLE")).toBeLessThan(kinds.indexOf("MODEL_2_RECOVERED"));

  await signIn(page, "coordinator");
  await page.goto(`/missions/${id}/events`);
  // The live view is bounded to recent events; the outage is earlier in the persisted log.
  await page.getByRole("button", { name: /Load persisted history/ }).click();
  await expect(page.getByText("Model 2 command agent unavailable").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Model 2 command agent recovered").first()).toBeVisible();
});

test("contradicting agent reports appear to operators as conflicting evidence", async ({ page, request }) => {
  const coord = await token(request, "coordinator");
  const id = await mission(request, coord, "E2E conflicting evidence", {
    scenario_id: "flood_basic",
    agents: 6,
    seed: 12985,
    horizon: 2000,
  });
  expect((await request.post(`/api/v1/missions/${id}/start`, { headers: auth(coord) })).status()).toBe(200);
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/v1/missions/${id}`, { headers: auth(coord) })).json()).last_sim_ms,
      {
        timeout: 30_000,
      },
    )
    .toBeGreaterThan(300);
  await request.post(`/api/v1/missions/${id}/pause`, {
    headers: auth(coord),
    data: { reason: "e2e conflict" },
  });
  await waitStatus(request, coord, id, /paused/);
  const now = (await (await request.get(`/api/v1/missions/${id}`, { headers: auth(coord) })).json())
    .last_sim_ms;
  for (const [agent, label] of [
    ["d0", "water"],
    ["d1", "fire"],
  ] as const) {
    const cred = await (
      await request.post(`/api/v1/missions/${id}/agent-credentials`, {
        headers: auth(coord),
        data: { agent_key: agent },
      })
    ).json();
    const machine = await (
      await request.post("/api/v1/auth/machine-token", {
        data: { credential_id: cred.credential_id, secret: cred.secret },
      })
    ).json();
    const report = await request.post(`/api/v1/missions/${id}/observations`, {
      headers: auth(machine.access_token),
      data: {
        observation_id: crypto.randomUUID(),
        kind: "hazard",
        label,
        observed_ms: now,
        confidence: 0.7,
        cell: [11, 9],
        evidence: [
          {
            evidence_id: crypto.randomUUID(),
            captured_ms: now,
            modality: "image",
            artifact_key: "synthetic/e2e-conflict",
          },
        ],
      },
    });
    expect(report.status()).toBe(202);
  }

  await signIn(page, "coordinator");
  await page.goto(`/missions/${id}/incidents`);
  const table = page.getByRole("table", { name: "Incidents" });
  await expect(table.getByText(/[1-9]\d* conflicting/).first()).toBeVisible({ timeout: 30_000 });
  await request.post(`/api/v1/missions/${id}/stop`, {
    headers: auth(coord),
    data: { reason: "e2e cleanup" },
  });
});
