/**
 * What kind of vacancy the account is looking for.
 *
 * The form is shared by the onboarding wizard and the profile page, so what is
 * pinned here is the contract both rely on: the payload carries the portal's
 * own vocabulary rather than the Portuguese labels, saving is refused without
 * the one field that drives the search, and the exclusion list says out loud
 * what it will do before the user commits to it.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PreferencesForm } from "@/components/PreferencesForm";
import { renderWithProviders } from "@/test/utils";
import type { JobPreferences } from "@/types/api";

vi.mock("@/services/preferences", () => ({
  fetchPreferences: vi.fn(),
  updatePreferences: vi.fn(),
}));

import * as preferencesService from "@/services/preferences";

const mocked = vi.mocked(preferencesService);

function buildPreferences(overrides: Partial<JobPreferences> = {}): JobPreferences {
  return {
    target_role: null,
    alternative_roles: [],
    seniority: [],
    work_models: [],
    locations: [],
    salary_min: null,
    salary_currency: "BRL",
    priority_technologies: [],
    excluded_terms: [],
    updated_at: null,
    ...overrides,
  };
}

async function render(preferences: JobPreferences = buildPreferences()) {
  mocked.fetchPreferences.mockResolvedValue(preferences);
  const user = userEvent.setup();
  renderWithProviders(<PreferencesForm />);
  await screen.findByLabelText(/cargo principal/i);
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocked.updatePreferences.mockImplementation(async (payload) =>
    buildPreferences(payload as Partial<JobPreferences>),
  );
});

describe("PreferencesForm", () => {
  it("refuses to save without the role that drives the search", async () => {
    await render();

    expect(screen.getByRole("button", { name: /salvar preferências/i })).toBeDisabled();
    expect(screen.getByText(/informe o cargo principal/i)).toBeInTheDocument();
  });

  it("sends the portal's own vocabulary, not the labels on screen", async () => {
    const user = await render(buildPreferences({ target_role: "Full Stack Developer" }));

    await user.click(screen.getByRole("checkbox", { name: "Júnior" }));
    await user.click(screen.getByRole("checkbox", { name: "Remoto" }));
    await user.click(screen.getByRole("button", { name: /salvar preferências/i }));

    await waitFor(() => expect(mocked.updatePreferences).toHaveBeenCalledTimes(1));
    const payload = mocked.updatePreferences.mock.calls[0][0];
    expect(payload.seniority).toEqual(["entry"]);
    expect(payload.work_models).toEqual(["remote"]);
    expect(payload.target_role).toBe("Full Stack Developer");
  });

  it("keeps an empty salary as no floor rather than zero", async () => {
    const user = await render(buildPreferences({ target_role: "Backend" }));

    await user.click(screen.getByRole("button", { name: /salvar preferências/i }));

    await waitFor(() => expect(mocked.updatePreferences).toHaveBeenCalledTimes(1));
    expect(mocked.updatePreferences.mock.calls[0][0].salary_min).toBeNull();
  });

  it("says what the exclusion list will do before it is saved", async () => {
    await render(
      buildPreferences({ target_role: "Backend", excluded_terms: ["call center", "vendas"] }),
    );

    expect(screen.getByText(/call center, vendas/)).toBeInTheDocument();
    expect(screen.getByText(/vamos pular qualquer vaga/i)).toBeInTheDocument();
  });

  it("states that a priority technology cannot add anything to the resume", async () => {
    await render(buildPreferences({ target_role: "Backend" }));

    expect(
      screen.getByText(/uma tecnologia aqui que você não tem não aparece/i),
    ).toBeInTheDocument();
  });
});
