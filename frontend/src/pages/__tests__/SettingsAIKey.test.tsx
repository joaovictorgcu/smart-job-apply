/**
 * Bringing your own AI key, from the settings screen.
 *
 * The service module is mocked rather than the cache seeded, because what
 * matters here is what the screen *sends* and what it refuses to send. Three
 * promises are asserted: the key leaves only when the user typed one, a
 * provider without a key never reaches the server, and testing a key does not
 * save it.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Settings } from "@/pages/Settings";
import { buildSettings } from "@/test/factories";
import { renderWithProviders } from "@/test/utils";
import type { AIStatus, UserSettings } from "@/types/api";

vi.mock("@/services/profile", () => ({
  fetchProfile: vi.fn(),
  updateProfile: vi.fn(),
  uploadResume: vi.fn(),
  readResumeIntake: vi.fn(),
  readStoredResumeIntake: vi.fn(),
  applyResumeIntake: vi.fn(),
  fetchSettings: vi.fn(),
  updateSettings: vi.fn(),
  fetchAIStatus: vi.fn(),
  fetchAIProviders: vi.fn(),
  testAICredentials: vi.fn(),
  generateCoverLetter: vi.fn(),
  fetchHealth: vi.fn(),
}));

vi.mock("@/services/automation", () => ({
  fetchSessionStatus: vi.fn(),
  startSession: vi.fn(),
  stopSession: vi.fn(),
  killSwitch: vi.fn(),
}));

import * as profileService from "@/services/profile";

const profileMock = vi.mocked(profileService);

const DEPLOYMENT_STATUS: AIStatus = {
  configured: true,
  model: "claude-opus-5",
  provider: "anthropic",
  source: "deployment",
  detail: "",
};

function arrange(settings: Partial<UserSettings> = {}) {
  const stored = buildSettings(settings);
  profileMock.fetchSettings.mockResolvedValue(stored);
  profileMock.updateSettings.mockImplementation(async (payload) =>
    buildSettings({ ...stored, ...payload } as Partial<UserSettings>),
  );
  profileMock.fetchAIStatus.mockResolvedValue(DEPLOYMENT_STATUS);
  profileMock.fetchAIProviders.mockResolvedValue([
    { name: "anthropic", key_url: "https://console.anthropic.com/settings/keys" },
    { name: "groq", key_url: "https://console.groq.com/keys" },
  ]);
  return stored;
}

async function selectProvider(name: string) {
  const select = await screen.findByLabelText("Provedor");
  await userEvent.selectOptions(select, name);
}

async function save() {
  await userEvent.click(screen.getByRole("button", { name: /salvar configurações/i }));
}

describe("the AI key an account brings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("offers only the providers the server says are selectable", async () => {
    arrange();
    renderWithProviders(<Settings />);

    await selectProvider("groq");

    // Local providers are absent by construction: on a hosted install
    // "localhost" is the server, not the user's machine.
    expect(screen.queryByRole("option", { name: /ollama/i })).not.toBeInTheDocument();
  });

  it("sends the provider and the key together", async () => {
    arrange();
    renderWithProviders(<Settings />);

    await selectProvider("groq");
    await userEvent.type(await screen.findByLabelText("Chave de API"), "gsk-my-own-key");
    await save();

    await waitFor(() => expect(profileMock.updateSettings).toHaveBeenCalled());
    const payload = profileMock.updateSettings.mock.calls[0][0];
    expect(payload.ai_provider).toBe("groq");
    expect(payload.ai_api_key).toBe("gsk-my-own-key");
    // Read-only field: it reports whether a key is stored, and is not ours to send.
    expect(payload).not.toHaveProperty("ai_key_set");
  });

  it("refuses to save a provider with no key, without a round trip", async () => {
    arrange();
    renderWithProviders(<Settings />);

    await selectProvider("groq");
    await save();

    expect(await screen.findByText(/exige uma chave de api/i)).toBeInTheDocument();
    expect(profileMock.updateSettings).not.toHaveBeenCalled();
  });

  it("keeps a stored key when nothing is typed", async () => {
    arrange({ ai_provider: "groq", ai_key_set: true });
    renderWithProviders(<Settings />);

    await userEvent.clear(await screen.findByLabelText("Limite diário de envios"));
    await userEvent.type(screen.getByLabelText("Limite diário de envios"), "30");
    await save();

    await waitFor(() => expect(profileMock.updateSettings).toHaveBeenCalled());
    // Absent, not empty: an empty string is how a key is *cleared*.
    expect(profileMock.updateSettings.mock.calls[0][0]).not.toHaveProperty("ai_api_key");
  });

  it("demands a new key when the provider changes", async () => {
    arrange({ ai_provider: "groq", ai_key_set: true });
    renderWithProviders(<Settings />);

    await selectProvider("anthropic");
    await save();

    expect(await screen.findByText(/chave guardada é do provedor anterior/i)).toBeInTheDocument();
    expect(profileMock.updateSettings).not.toHaveBeenCalled();
  });

  it("tests a key without saving it", async () => {
    arrange();
    profileMock.testAICredentials.mockResolvedValue({
      ok: true,
      provider: "groq",
      model: "llama-3.3-70b-versatile",
      detail: "",
    });
    renderWithProviders(<Settings />);

    await selectProvider("groq");
    await userEvent.type(await screen.findByLabelText("Chave de API"), "gsk-try-me");
    await userEvent.click(screen.getByRole("button", { name: /testar chave/i }));

    expect(await screen.findByText(/ainda não foi salva/i)).toBeInTheDocument();
    expect(profileMock.testAICredentials).toHaveBeenCalledWith({
      provider: "groq",
      api_key: "gsk-try-me",
    });
    expect(profileMock.updateSettings).not.toHaveBeenCalled();
  });

  it("shows the provider's own words when a key is rejected", async () => {
    arrange();
    profileMock.testAICredentials.mockResolvedValue({
      ok: false,
      provider: "groq",
      model: "",
      detail: "groq: invalid api key",
    });
    renderWithProviders(<Settings />);

    await selectProvider("groq");
    await userEvent.type(await screen.findByLabelText("Chave de API"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /testar chave/i }));

    expect(await screen.findByText("groq: invalid api key")).toBeInTheDocument();
  });

  it("never renders the stored key, not even masked", async () => {
    arrange({ ai_provider: "groq", ai_key_set: true });
    renderWithProviders(<Settings />);

    const input = (await screen.findByLabelText("Chave de API")) as HTMLInputElement;

    expect(input.value).toBe("");
    expect(input.type).toBe("password");
    expect(screen.getByText(/deixe em branco para mantê-la/i)).toBeInTheDocument();
  });
});
