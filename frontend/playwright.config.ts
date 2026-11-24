import { defineConfig, devices } from "@playwright/test";

/**
 * Two separate projects:
 *  - mock: synthetic demo mode only. No backend is needed and no backend is contacted.
 *  - connected: the real Phase 7 backend at SWARM_BACKEND_URL (default 127.0.0.1:8000).
 *    Requires E2E_PASSWORD (shared password of the local dev accounts admin, coordinator,
 *    operator, researcher, observer). Connected tests are never counted as mock tests.
 * Uses the installed Google Chrome (channel "chrome") so no browser download is required;
 * set PW_CHANNEL="" to use Playwright's bundled Chromium instead.
 */
const channel = process.env.PW_CHANNEL ?? "chrome";
const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: { baseURL, trace: "retain-on-failure", screenshot: "only-on-failure", ...(channel ? { channel } : {}) },
  projects: [
    { name: "mock", testDir: "./tests/e2e/mock", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, ...(channel ? { channel } : {}) } },
    { name: "connected", testDir: "./tests/e2e/connected", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, ...(channel ? { channel } : {}) } },
  ],
  webServer: {
    command: "npx vite --host 127.0.0.1 --port 5173 --strictPort",
    url: baseURL,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
