/**
 * The login screen, driven as a person would.
 *
 * Every other spec injects a token, so this is the only place the real form,
 * its validation and the redirect are exercised against the real API.
 */

import { expect, test } from "@playwright/test";

import { DEMO_EMAIL, DEMO_PASSWORD } from "./helpers";

test.describe("signing in", () => {
  test("a valid account reaches the dashboard", async ({ page }) => {
    await page.goto("/login");

    await page.getByLabel("E-mail").fill(DEMO_EMAIL);
    await page.getByLabel("Senha").fill(DEMO_PASSWORD);
    await page.getByRole("button", { name: "Entrar" }).click();

    // The dashboard asks the one question it answers, and offers the way in.
    await expect(page.getByRole("heading", { name: /O que você quer fazer hoje\?/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /Encontrar vagas/ })).toBeVisible();
  });

  test("a wrong password is reported without leaving the form", async ({ page }) => {
    await page.goto("/login");

    await page.getByLabel("E-mail").fill(DEMO_EMAIL);
    await page.getByLabel("Senha").fill("definitely-not-the-password");
    await page.getByRole("button", { name: "Entrar" }).click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("an empty form is validated in the browser", async ({ page }) => {
    await page.goto("/login");

    await page.getByRole("button", { name: "Entrar" }).click();

    await expect(page.getByText("Informe o seu e-mail.")).toBeVisible();
    await expect(page.getByText("Informe a sua senha.")).toBeVisible();
  });

  test("a protected route sends an anonymous visitor to login", async ({ page }) => {
    await page.goto("/applications");

    await expect(page).toHaveURL(/\/login/);
  });
});
