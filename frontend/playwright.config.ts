import { defineConfig, devices } from "@playwright/test";

/**
 * Browser tests for the dashboard, against a real backend.
 *
 * `scripts/demo_server.py` boots the API with the offline AI provider and the
 * bundled fake job portal, so a run needs no API key, no LinkedIn account and no
 * network. `--fresh` wipes the demo database first, which is what makes these
 * tests repeatable: they assert on counts and on empty states.
 *
 * Both servers are started here, and Playwright reuses an already-running pair
 * locally so `npm run dev` in another terminal is not fought over. On CI it
 * always starts its own.
 */

const BACKEND_PORT = 8000;
const FRONTEND_PORT = 5173;

export default defineConfig({
  testDir: "./e2e",
  // The flow under test drives a real Chromium inside the backend as well as
  // the one Playwright drives, so steps are slower than a typical web test.
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  // Serial: the specs share one backend and one demo account, and a search run
  // is global to that account.
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `python scripts/demo_server.py --fresh --port ${BACKEND_PORT}`,
      cwd: "..",
      url: `http://127.0.0.1:${BACKEND_PORT}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npm run dev",
      url: `http://localhost:${FRONTEND_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
