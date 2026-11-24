import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/** Synthetic demo mode end-to-end. Asserts that no backend request is made.
 * Synthetic state lives only in this tab, so navigation stays inside the app (no reloads). */
async function openMission(page: Page, name: string, expectHeading = true) {
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Missions", exact: true })
    .click();
  await page.getByRole("link", { name, exact: true }).click();
  if (expectHeading) await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
}

async function startDemo(page: Page, role = "coordinator") {
  const backendCalls: string[] = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.pathname.startsWith("/api/") || u.pathname.startsWith("/ws/")) backendCalls.push(u.pathname);
  });
  await page.goto("/login");
  await page
    .getByLabel("Synthetic demo")
    .check()
    .catch(async () => page.getByText("Synthetic demo", { exact: false }).first().click());
  await page.getByLabel("Demonstration role").selectOption(role);
  await page.getByRole("button", { name: "Start synthetic demo" }).click();
  await expect(page.getByText("SYNTHETIC DEMO MODE.")).toBeVisible();
  return backendCalls;
}

test("startup, one-click demo, playback and isolation from the backend", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  const calls = await startDemo(page);
  await expect(page.getByRole("heading", { name: "Six-agent flood demonstration" })).toBeVisible();
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Confirm start/ })
    .click();
  await page.getByLabel("Playback", { exact: true }).selectOption("8");
  await expect(
    page
      .getByLabel("System status")
      .locator(".tstat")
      .filter({ hasText: /^Status/ })
      .getByText("running"),
  ).toBeVisible();
  await expect
    .poll(
      async () =>
        Number(
          (await page
            .locator(".metric")
            .filter({ hasText: "Observations" })
            .locator(".value")
            .textContent()) ?? 0,
        ),
      { timeout: 30_000 },
    )
    .toBeGreaterThan(5);
  // Pause, resume, then confirm the backend was never contacted.
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Confirm pause/ })
    .click();
  await expect(page.getByRole("button", { name: "Resume", exact: true })).toBeVisible();
  expect(calls).toEqual([]);
  expect(errors.filter((e) => !e.includes("favicon"))).toEqual([]);
});

test("map interaction, agent selection, observations, incidents and evidence", async ({ page }) => {
  await startDemo(page);
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Confirm start/ })
    .click();
  await page.getByLabel("Playback", { exact: true }).selectOption("8");
  await page.waitForTimeout(9000);
  await page.getByRole("link", { name: "Live simulation map" }).click();
  const map = page.getByRole("application", { name: /Mission map/ });
  await expect(map).toBeVisible();
  await page.getByRole("button", { name: "Zoom in" }).click();
  await page.getByRole("button", { name: "Fit to view" }).click();
  await page.getByRole("button", { name: /^Agent d0 at cell/ }).click();
  await expect(page.getByRole("region", { name: "Selection" }).getByText("agents")).toBeVisible();
  await page.getByRole("region", { name: "Selection" }).getByRole("link", { name: "Open details" }).click();
  await expect(page.getByRole("heading", { name: "Agent d0" })).toBeVisible();
  await page.getByRole("tab", { name: "Observations" }).click();
  await expect(page.getByRole("table", { name: "Agent observations" })).toBeVisible();
  await page.getByRole("link", { name: "Observations", exact: true }).click();
  await page.getByLabel("Category").selectOption("possible_human");
  await page.getByRole("table", { name: "Observations" }).locator("tbody tr").first().click();
  await expect(page.getByText("Observation ID (stable)")).toBeVisible();
  await page.getByRole("link", { name: "Incidents", exact: true }).click();
  await page.getByRole("table", { name: "Incidents" }).locator("tbody tr").first().click();
  await expect(page.getByRole("heading", { level: 1, name: /incident/ })).toBeVisible();
  await page.getByRole("tab", { name: /Evidence/ }).click();
  await page.getByRole("link", { name: "Open in evidence center" }).click();
  await expect(page.getByRole("heading", { name: "Multimodal evidence center" })).toBeVisible();
  await expect(page.getByText(/No stored media for this reference/).first()).toBeVisible();
});

test("recommendation review, approval, rejection and stale version", async ({ page }) => {
  await startDemo(page);
  await openMission(page, "Recommendation version conflict");
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Confirm start/ })
    .click();
  await page.getByLabel("Playback", { exact: true }).selectOption("8");
  await expect(
    page.locator(".metric").filter({ hasText: "Pending reviews" }).locator(".value"),
  ).not.toHaveText("0", { timeout: 40_000 });
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Confirm pause/ })
    .click();
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: /^Human review/ })
    .click();
  // First decision races a Model 2 revision → stale.
  await page.getByRole("button", { name: "Approve review" }).first().click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel(/Reason/).fill("reviewed evidence");
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "Approve review" }).click();
  await expect(dialog.getByText("This version is outdated.")).toBeVisible();
  await dialog.getByRole("button", { name: "Load updated version" }).click();
  // Approve the updated version.
  await page.getByRole("button", { name: "Approve review" }).first().click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel(/Reason/).fill("reviewed updated version");
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "Approve review" }).click();
  await expect(dialog.getByText("Decision recorded and sent to Model 2.")).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).last().click();
  // Reject another if available.
  const reject = page.getByRole("button", { name: "Reject" }).first();
  if (await reject.isVisible()) {
    await reject.click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel(/Reason/).fill("insufficient evidence");
    await dialog.getByRole("checkbox").check();
    await dialog.getByRole("button", { name: "Reject recommendation" }).click();
    await expect(dialog.getByText("Decision recorded and sent to Model 2.")).toBeVisible();
    await dialog.getByRole("button", { name: "Close" }).last().click();
  }
  await page.getByRole("tab", { name: "Decision history" }).click();
  await expect(page.getByRole("table", { name: "Human decisions" })).toBeVisible();
});

test("unauthorized action is disabled for an observer", async ({ page }) => {
  await startDemo(page, "observer");
  await expect(page.getByRole("button", { name: "Start", exact: true })).toBeDisabled();
});

test("communication degradation and Model 2 unavailability scenarios", async ({ page }) => {
  await startDemo(page);
  await openMission(page, "Communication degradation");
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Confirm start/ })
    .click();
  await page.getByLabel("Playback", { exact: true }).selectOption("8");
  await expect(
    page
      .getByLabel("System status")
      .locator(".tstat")
      .filter({ hasText: /^Comms/ }),
  ).toContainText("degraded", { timeout: 30_000 });
  await page.getByRole("link", { name: "Communication network" }).click();
  await expect(page.getByRole("img", { name: /Communication topology/ })).toBeVisible();
  await expect(page.getByText("Degradation and recovery history")).toBeVisible();
  await openMission(page, "Model 2 unavailable");
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Confirm start/ })
    .click();
  await page.getByLabel("Playback", { exact: true }).selectOption("8");
  await expect(
    page
      .getByLabel("System status")
      .locator(".tstat")
      .filter({ hasText: /^Model 2/ }),
  ).toContainText("unavailable", { timeout: 30_000 });
});

test("analytics, synthetic export labelling and backend-failure state", async ({ page }) => {
  await startDemo(page);
  await page.getByRole("link", { name: "Research analytics" }).click();
  await expect(page.getByText("Synthetic demonstration metrics.")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "operational CSV" }).click();
  expect((await download).suggestedFilename()).toMatch(/^SYNTHETIC-mission-syn-flood-6-operational\.csv$/);
  await openMission(page, "Backend failure", false);
  await expect(page.getByText(/backend could not be reached/i)).toBeVisible({ timeout: 20_000 });
});

for (const size of [
  { width: 1366, height: 768 },
  { width: 1920, height: 1080 },
  { width: 820, height: 1180 },
  { width: 390, height: 844 },
]) {
  test(`responsive layout ${size.width}x${size.height} has no horizontal page scroll`, async ({ page }) => {
    await page.setViewportSize(size);
    await startDemo(page);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
    if (size.width <= 900) {
      await page.getByRole("button", { name: "Open navigation" }).click();
      await expect(
        page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: /Drone fleet/ }),
      ).toBeInViewport();
    }
  });
}

test("automated accessibility scan (axe, WCAG 2.x A/AA rules)", async ({ page }) => {
  await startDemo(page);
  for (const link of ["Mission overview", "Human review", "Drone fleet (Model 1)", "Settings"]) {
    const path = link;
    await page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("link", { name: link, exact: true })
      .click();
    await page.waitForTimeout(800);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    const describe = (v: (typeof serious)[number]) =>
      `${path}: ${v.id} (${v.nodes.length}) ` +
      v.nodes
        .slice(0, 5)
        .map((n) => `${n.target.join(" ")} :: ${(n.failureSummary ?? "").split("\n").pop()}`)
        .join(" | ");
    expect(serious.map(describe)).toEqual([]);
  }
});

test.describe("dark theme", () => {
  test.use({ colorScheme: "dark" });
  test("automated accessibility scan in dark theme", async ({ page }) => {
    await startDemo(page);
    for (const link of ["Mission overview", "Human review", "Incidents", "Communication network"]) {
      await page
        .getByRole("navigation", { name: "Main navigation" })
        .getByRole("link", { name: link, exact: true })
        .click();
      await page.waitForTimeout(800);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(
        serious.map(
          (v) =>
            `${link}: ${v.id} ${v.nodes
              .slice(0, 3)
              .map((n) => n.target.join(" "))
              .join(" | ")}`,
        ),
      ).toEqual([]);
    }
  });
});
