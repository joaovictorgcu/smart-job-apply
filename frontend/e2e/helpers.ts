/**
 * Shared plumbing for the browser tests.
 *
 * Setup goes through the API rather than the UI. Clicking through login and a
 * search on every spec would test the same three screens over and over and make
 * each spec minutes long; the specs then spend their time on the screen they are
 * actually about. `login.spec.ts` is the exception and drives the real form.
 */

import type { APIRequestContext, Page } from "@playwright/test";
import { expect } from "@playwright/test";

/** Seeded by `scripts/demo_server.py`. */
export const DEMO_EMAIL = "demo@example.com";
export const DEMO_PASSWORD = "demo-password-123";

/** Must match `TOKEN_STORAGE_KEY` in src/services/client.ts. */
const TOKEN_STORAGE_KEY = "sja.token";

export async function apiLogin(request: APIRequestContext): Promise<string> {
  const response = await request.post("/api/auth/login", {
    data: { email: DEMO_EMAIL, password: DEMO_PASSWORD },
  });
  expect(
    response.ok(),
    `login failed (${response.status()}): ${await response.text()}`,
  ).toBeTruthy();
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}

/**
 * Put a valid token in localStorage before the app boots.
 *
 * `addInitScript` runs before any page script, so the auth provider finds the
 * token on its first read and the app never renders the login screen.
 */
export async function signIn(page: Page, token: string): Promise<void> {
  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    [TOKEN_STORAGE_KEY, token] as const,
  );
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

export interface Job {
  id: number;
  title: string;
  company: string;
  score: number | null;
  status: string;
  easy_apply: boolean;
  application_id: number | null;
}

export interface Application {
  id: number;
  status: string;
  job_id: number;
  screening_answers: { question: string; answer: string; needs_review: boolean }[];
}

/**
 * Open a browser session, run one search, and return the jobs it found.
 *
 * The backend runs with `DEMO_PORTAL=true`, so "searching" drives a real
 * Chromium against the bundled fake site — the same code path a real run uses.
 */
export async function runDemoSearch(
  request: APIRequestContext,
  token: string,
  { keywords = "python", maxResults = 3 } = {},
): Promise<Job[]> {
  const headers = authHeaders(token);

  const started = await request.post("/api/automation/session/start", { headers });
  expect(
    started.ok(),
    `session start failed (${started.status()}): ${await started.text()}`,
  ).toBeTruthy();

  const search = await request.post("/api/automation/search", {
    headers,
    // `analyze` is what makes the offline provider score each posting, which the
    // specs need: an unscored job is filtered out by the minimum-score gate.
    data: { keywords, max_results: maxResults, analyze: true },
  });
  expect(
    search.ok(),
    `search failed (${search.status()}): ${await search.text()}`,
  ).toBeTruthy();

  return waitForJobs(request, token, maxResults, { requireScored: true });
}

/**
 * Poll the jobs list until the background run has written its results.
 *
 * A row appears as soon as the posting is scraped, and its score arrives a
 * moment later when the provider answers, so "the jobs are there" is not the
 * same as "the run is done". `requireScored` waits for the second, which is
 * what a spec asserting on scores actually needs.
 */
export async function waitForJobs(
  request: APIRequestContext,
  token: string,
  atLeast: number,
  { timeoutMs = 90_000, requireScored = true } = {},
): Promise<Job[]> {
  const headers = authHeaders(token);
  const deadline = Date.now() + timeoutMs;
  let jobs: Job[] = [];

  while (Date.now() < deadline) {
    const response = await request.get("/api/jobs?limit=50", { headers });
    if (response.ok()) {
      jobs = ((await response.json()) as { items: Job[] }).items;
      const ready = requireScored ? jobs.filter((job) => job.score !== null) : jobs;
      if (ready.length >= atLeast) return ready;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }

  const scored = jobs.filter((job) => job.score !== null).length;
  throw new Error(
    `only ${scored} of ${atLeast} scored jobs (${jobs.length} found) ` +
      `appeared within ${timeoutMs}ms`,
  );
}

/** Fill the forms for `jobIds` and wait until they are parked for review. */
export async function prepareApplications(
  request: APIRequestContext,
  token: string,
  jobIds: number[],
): Promise<Application[]> {
  const headers = authHeaders(token);

  const prepared = await request.post("/api/automation/prepare", {
    headers,
    data: { job_ids: jobIds, confirmed: true },
  });
  expect(
    prepared.ok(),
    `prepare failed (${prepared.status()}): ${await prepared.text()}`,
  ).toBeTruthy();

  return waitForApplications(request, token, jobIds);
}

/**
 * Poll until `jobIds` all have an application parked for review.
 *
 * Keyed on the job ids rather than on a count: the specs prepare one job at a
 * time against a shared account, so "three applications exist" would be
 * satisfied by earlier specs' work.
 */
export async function waitForApplications(
  request: APIRequestContext,
  token: string,
  jobIds: number[],
  timeoutMs = 90_000,
): Promise<Application[]> {
  const headers = authHeaders(token);
  const deadline = Date.now() + timeoutMs;
  let applications: Application[] = [];

  while (Date.now() < deadline) {
    const response = await request.get("/api/applications?limit=100", { headers });
    if (response.ok()) {
      applications = ((await response.json()) as { items: Application[] }).items;
      const wanted = applications.filter((item) => jobIds.includes(item.job_id));
      const settled = wanted.filter((item) => item.status !== "preparing");
      if (settled.length >= jobIds.length) return settled;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }

  const found = applications.filter((item) => jobIds.includes(item.job_id)).length;
  throw new Error(
    `only ${found} of ${jobIds.length} applications for jobs ` +
      `${jobIds.join(", ")} appeared within ${timeoutMs}ms`,
  );
}

export async function readApplication(
  request: APIRequestContext,
  token: string,
  id: number,
): Promise<Record<string, unknown>> {
  const response = await request.get(`/api/applications/${id}`, {
    headers: authHeaders(token),
  });
  expect(response.ok(), `could not read application ${id}`).toBeTruthy();
  return (await response.json()) as Record<string, unknown>;
}
