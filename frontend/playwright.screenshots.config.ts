import { defineConfig, devices } from "@playwright/test";

/**
 * The README's pictures, as a command.
 *
 * Separate from `playwright.config.ts` because this is not a test: it asserts
 * almost nothing and its output is six PNGs in `docs/images/`. Keeping it out
 * of the suite also keeps the suite honest — a run of `npm run e2e` should not
 * rewrite files in the repository.
 *
 * The backend is seeded, not empty. `demo_server.py` alone leaves most screens
 * showing empty states, which is exactly what a screenshot must not show;
 * `seed_mock.py` fills every one of them with deterministic, invented data.
 * It runs first because it creates the schema itself, so the server that
 * follows finds a populated database instead of racing the seed for it.
 *
 *     npm run shots
 */

// Not 8000 and not 5173: a run must not collide with — or worse, quietly borrow —
// a dev server someone already has open, whose API is a different database.
const BACKEND_PORT = 8010;
const FRONTEND_PORT = 5174;

// And its own database file, for the third time the same reason: `--fresh`
// wipes what it finds, and what it finds must not be someone's demo.
const DATA_DIR = "backend/data/screenshots";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /screenshots\.spec\.ts/,
  // Every screen is loaded in one test, and two of them wait on a real browser
  // session inside the backend.
  timeout: 180_000,
  expect: { timeout: 15_000 },
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // The size the README tells contributors to use, so a hand-taken shot
        // and a scripted one are the same picture.
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
  webServer: [
    {
      command:
        `python scripts/seed_mock.py --fresh --data-dir ${DATA_DIR} && ` +
        `python scripts/demo_server.py --port ${BACKEND_PORT} --data-dir ${DATA_DIR}`,
      cwd: "..",
      url: `http://127.0.0.1:${BACKEND_PORT}/api/health`,
      // Never reused: a leftover server is serving a database this run did not
      // seed, and the screenshots would show whatever happened to be in it.
      reuseExistingServer: false,
      // Generous because this is two programs in sequence — seed, then serve —
      // and the seed writes a few hundred rows. It has timed out at 180s on a
      // machine that was also running the test suite.
      timeout: 420_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npm run dev",
      url: `http://localhost:${FRONTEND_PORT}`,
      // Its own port and its own proxy target, for the same reason.
      env: {
        FRONTEND_PORT: String(FRONTEND_PORT),
        BACKEND_ORIGIN: `http://127.0.0.1:${BACKEND_PORT}`,
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
