/**
 * The README's screenshots, taken by a script instead of by hand.
 *
 * They were stale — captured before the dashboard, the review screen and the
 * navigation were reworked — and they went stale because retaking them was a
 * manual chore nobody was going to do twice. A screenshot that costs one
 * command is a screenshot that can be current.
 *
 * This does not run with the normal browser suite (`playwright.config.ts`
 * ignores it) because it asserts almost nothing: it drives the app to a screen
 * and writes a PNG. Run it with `npm run shots`.
 *
 * The data is `scripts/seed_mock.py`, which is deterministic — fixed RNG seed,
 * dates anchored to a fixed offset from today — so two runs produce the same
 * screens. Everything in them is invented: no real posting, no real company, no
 * real person, and nothing was ever sent anywhere. That is the reason to shoot
 * the seed rather than a real account, beyond convenience.
 */

import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import type { Locator, Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

/** Seeded by `scripts/seed_mock.py`. */
const EMAIL = "admin@admin.com";
const PASSWORD = "123";

/** Must match `TOKEN_STORAGE_KEY` in src/services/client.ts. */
const TOKEN_STORAGE_KEY = "sja.token";

// `import.meta.url`, not `__dirname`: this file is loaded as an ES module.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const IMAGES = path.resolve(HERE, "..", "..", "docs", "images");

interface ApplicationRow {
  id: number;
  status: string;
  job_title: string | null;
}

/**
 * Wait for the network to settle *and* for animation to finish.
 *
 * `networkidle` alone is not enough here: cards fade in and the score bars
 * animate their width, so a shot taken the instant the data arrives catches
 * half-drawn UI. A screenshot is the one test where "it looks right" is the
 * whole assertion.
 */
async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(700);
}

const VIEWPORT = { width: 1440, height: 900 };

function wrote(file: string): void {
  // eslint-disable-next-line no-console -- the point of the run is the files.
  console.log(`wrote ${path.relative(process.cwd(), file)}`);
}

async function shot(page: Page, name: string): Promise<void> {
  const file = path.join(IMAGES, name);
  await page.screenshot({ path: file });
  wrote(file);
}

/**
 * Shoot one element, by growing the window until the element fits in it.
 *
 * The obvious `locator.screenshot()` produces a broken picture for anything
 * taller than the viewport: the parts that were never scrolled into view come
 * out as blank bands, and the sticky header prints across the middle. Resizing
 * first means the browser lays the whole element out and paints it once, so
 * what is captured is what a person would see on a tall enough screen.
 *
 * The height is measured after the resize, not before: growing the window
 * reflows the column and changes the very number being measured.
 */
async function shotElement(page: Page, locator: Locator, name: string): Promise<void> {
  await page.setViewportSize({ width: VIEWPORT.width, height: 2400 });
  await locator.scrollIntoViewIfNeeded();
  await settle(page);

  const box = await locator.boundingBox();
  expect(box, `${name}: the element has no box to measure`).toBeTruthy();
  await page.setViewportSize({
    width: VIEWPORT.width,
    height: Math.min(Math.ceil(box!.height) + 48, 4000),
  });
  await locator.scrollIntoViewIfNeeded();
  await settle(page);

  const file = path.join(IMAGES, name);
  await locator.screenshot({ path: file });
  wrote(file);
  await page.setViewportSize(VIEWPORT);
}

test.beforeAll(async () => {
  await mkdir(IMAGES, { recursive: true });
});

test("captures the screens the README describes", async ({ page, request }) => {
  const login = await request.post("/api/auth/login", {
    data: { email: EMAIL, password: PASSWORD },
  });
  expect(
    login.ok(),
    `login failed (${login.status()}): ${await login.text()}. ` +
      "Did `scripts/seed_mock.py --fresh` run before the server?",
  ).toBeTruthy();
  const { access_token: token } = (await login.json()) as { access_token: string };

  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    [TOKEN_STORAGE_KEY, token] as const,
  );

  // --- the four screens in the table ------------------------------------- //

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await settle(page);
  await shot(page, "dashboard.png");

  await page.goto("/jobs");
  await expect(page.getByRole("article").first()).toBeVisible();
  await settle(page);
  await shot(page, "jobs.png");

  // The demo server zeroes every delay and the minimum score so a run finishes
  // in seconds. On the settings screen that reads as "every safeguard is off",
  // which is the opposite of what the screen is for. These are the values the
  // product actually ships with (`app/config.py`), so the picture shows the
  // defaults a real install starts from rather than the demo's hurry.
  const restored = await request.put("/api/settings", {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      min_score: 70,
      action_delay_min: 2.5,
      action_delay_max: 7,
      apply_delay_min: 45,
      apply_delay_max: 120,
      working_hour_start: 8,
      working_hour_end: 20,
    },
  });
  expect(
    restored.ok(),
    `could not restore the shipped defaults (${restored.status()}): ${await restored.text()}`,
  ).toBeTruthy();

  await page.goto("/settings");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await settle(page);
  await shot(page, "settings.png");

  await page.goto("/pipeline");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await settle(page);
  await shot(page, "pipeline.png");

  // --- the application that is waiting for a decision --------------------- //

  // Awaiting review is the screen worth showing: the form is filled in and
  // halted at the gate, which is the whole premise of assisted mode. Falling
  // back to any application at all keeps the run producing files if the seed
  // ever stops leaving one parked there.
  const listed = await request.get("/api/applications?limit=100", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(listed.ok(), `could not list applications (${listed.status()})`).toBeTruthy();
  const applications = ((await listed.json()) as { items: ApplicationRow[] }).items;
  const target =
    applications.find((row) => row.status === "awaiting_review") ?? applications[0];
  expect(target, "the seed produced no applications to screenshot").toBeTruthy();

  // The seed leaves applications without their own resume, and the panel's
  // empty state is not what the README caption promises. Deriving it here
  // rather than clicking the button keeps the picture the same on every run:
  // the adaptation is deterministic and offline (`app/domain/resume.py`).
  const derived = await request.post(`/api/resumes/applications/${target.id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(
    derived.ok(),
    `could not derive a resume for application ${target.id} ` +
      `(${derived.status()}): ${await derived.text()}`,
  ).toBeTruthy();

  await page.goto(`/applications/${target.id}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await settle(page);

  const resume = page.getByTestId("application-resume-panel");
  await expect(resume).toBeVisible();

  // The caption promises the change list and the invention guard, and those
  // live on the second tab. The first tab is the document itself, which is a
  // different picture and one the README does not claim to be showing.
  await resume.getByRole("tab", { name: "O que foi adaptado" }).click();
  await settle(page);
  await shotElement(page, resume, "cv-tailoring.png");

  // A viewport shot, not the whole panel: the review panel is the letter, four
  // screening answers and the approval gate, and printed end to end it is over
  // two thousand pixels tall — unreadable beside a 900px picture in the
  // README's table. What matters is the top of it, which is where the decision
  // is made.
  const review = page.getByTestId("application-review-panel");
  await expect(review).toBeVisible();
  // `scrollIntoViewIfNeeded` on an element taller than the window stops as soon
  // as any part of it shows, which lands mid-letter. Aligning its top frames
  // the panel from its first line.
  //
  // Through `scrollIntoView` and not `window.scrollTo`: the page does not
  // scroll the window. `AppShell` puts the routed content in a `<main
  // class="scroll-area">`, so the window is always at zero and scrolling it
  // does nothing — which is how the first attempt produced a blank picture.
  await review.evaluate((element) => {
    element.scrollIntoView({ block: "start" });
    const scroller = element.closest("main");
    if (scroller) scroller.scrollTop = Math.max(0, scroller.scrollTop - 16);
    // `scrollIntoView` walks every scrollable ancestor, the window included,
    // and nudging the window slides the sidebar and the header out of frame.
    window.scrollTo(0, 0);
  });
  await settle(page);
  await shot(page, "review.png");
});
