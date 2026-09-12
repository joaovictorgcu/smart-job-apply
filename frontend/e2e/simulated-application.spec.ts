/**
 * A full simulated application, from search to submitted.
 *
 * This is the spec that answers "does the product actually work": a real
 * Chromium in the backend searches the bundled fake portal, the offline provider
 * scores what it found, the form is filled and parked, and only an explicit
 * approval in the UI sends it.
 *
 * Nothing here touches LinkedIn. The backend runs with `DEMO_PORTAL=true`, so
 * the "site" being automated is served from inside the API process.
 *
 * The load-bearing assertion is the order of events: after preparing, the
 * application must be `awaiting_review` and NOT submitted. A build that
 * submitted during preparation would still show a submitted application at the
 * end, so the intermediate state is what proves assisted mode holds.
 */

import { expect, test } from "@playwright/test";

import {
  apiLogin,
  prepareApplications,
  readApplication,
  runDemoSearch,
  signIn,
  type Job,
} from "./helpers";

test.describe.configure({ mode: "serial" });

let token = "";
let jobs: Job[] = [];

test.beforeAll(async ({ request }) => {
  token = await apiLogin(request);
  jobs = await runDemoSearch(request, token, { maxResults: 3 });
});

test("the search finds and scores the postings", async ({ page }) => {
  await signIn(page, token);
  await page.goto("/jobs");

  await expect(page.getByRole("heading", { name: "Vagas" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Backend Engineer 1/ })).toBeVisible();

  // Every posting came back scored: the offline provider answered for each one.
  expect(jobs.length).toBeGreaterThanOrEqual(3);
  for (const job of jobs) {
    expect(job.score, `job ${job.id} was not scored`).not.toBeNull();
    expect(job.easy_apply).toBe(true);
  }
});

test("preparing an application fills the form and stops before sending", async ({
  page,
  request,
}) => {
  const applications = await prepareApplications(request, token, [jobs[0].id]);
  const application = applications[0];

  // The gate, asserted on the server's own state rather than on the screen.
  expect(application.status).toBe("awaiting_review");

  await signIn(page, token);
  await page.goto(`/applications/${application.id}`);

  // The whole draft is on screen for review before anything can be sent.
  await expect(page.getByRole("heading", { name: "Respostas de triagem" })).toBeVisible();
  await expect(page.getByText("Years of Python experience?")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Carta de apresentação" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Aprovar e enviar" })).toBeEnabled();
});

test("approving sends it, and only then", async ({ page, request }) => {
  const applications = await prepareApplications(request, token, [jobs[1].id]);
  const application = applications.find((item) => item.job_id === jobs[1].id);
  expect(application, "the prepared application should be listed").toBeTruthy();
  const id = application!.id;

  const before = await readApplication(request, token, id);
  expect(before.status).toBe("awaiting_review");
  expect(before.submitted_at).toBeFalsy();

  await signIn(page, token);
  await page.goto(`/applications/${id}`);

  await page.getByRole("button", { name: "Aprovar e enviar" }).click();

  // A second, explicit confirmation that names the company.
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Enviar esta candidatura?");
  await dialog.getByRole("button", { name: /^Enviar para / }).click();

  await expect(page.getByText(/Enviada|enviada/).first()).toBeVisible({ timeout: 60_000 });

  await expect
    .poll(async () => (await readApplication(request, token, id)).status, {
      timeout: 60_000,
    })
    .toBe("submitted");
});

test("cancelling the confirmation sends nothing", async ({ page, request }) => {
  const applications = await prepareApplications(request, token, [jobs[2].id]);
  const application = applications.find((item) => item.job_id === jobs[2].id);
  const id = application!.id;

  await signIn(page, token);
  await page.goto(`/applications/${id}`);

  await page.getByRole("button", { name: "Aprovar e enviar" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancelar" }).click();

  await expect(dialog).toBeHidden();
  // Backing out of the dialog must leave the application exactly as it was.
  expect((await readApplication(request, token, id)).status).toBe("awaiting_review");
});

test("the dashboard leads with what is waiting for the operator", async ({ page }) => {
  await signIn(page, token);
  await page.goto("/");

  // The screen answers one question, and the work that cannot proceed without
  // a human is the first thing under it.
  await expect(page.getByRole("heading", { name: /O que você quer fazer hoje\?/ })).toBeVisible();
  await expect(page.getByText(/candidatura[s]? espera[m]? você/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Revisar/ }).first()).toBeVisible();
});
