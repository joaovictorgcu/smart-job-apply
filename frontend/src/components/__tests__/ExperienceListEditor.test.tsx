/**
 * The master resume's structured half.
 *
 * Two things are pinned here. The first is the payload: the editor collects
 * bullets as free text and has to send them as the lists the derivation reasons
 * about, with the blank lines a textarea inevitably leaves behind dropped. The
 * second is the promise the screen makes out loud — editing the master leaves
 * existing applications alone — because a user who does not believe that will
 * never touch this form again after their first application.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ExperienceListEditor } from "@/components/ExperienceListEditor";
import { buildExperience } from "@/test/factories";
import { renderWithProviders } from "@/test/utils";

vi.mock("@/services/resumes", () => ({
  fetchApplicationResume: vi.fn(),
  listResumeVersions: vi.fn(),
  adaptApplicationResume: vi.fn(),
  updateApplicationResume: vi.fn(),
  fetchMasterResume: vi.fn(),
  listExperiences: vi.fn(),
  createExperience: vi.fn(),
  updateExperience: vi.fn(),
  deleteExperience: vi.fn(),
}));

import * as resumesService from "@/services/resumes";

const mocked = vi.mocked(resumesService);

beforeEach(() => {
  vi.clearAllMocks();
  mocked.listExperiences.mockResolvedValue([]);
});

describe("ExperienceListEditor", () => {
  it("explains why structured experience matters when there is none", async () => {
    renderWithProviders(<ExperienceListEditor />);

    expect(await screen.findByText(/nenhuma experiência cadastrada/i)).toBeInTheDocument();
    expect(screen.getByText(/só pode reordenar competências/i)).toBeInTheDocument();
  });

  it("sends bullets as lists and drops the blank lines a textarea leaves behind", async () => {
    const user = userEvent.setup();
    mocked.createExperience.mockResolvedValue(buildExperience());
    renderWithProviders(<ExperienceListEditor />);
    await screen.findByText(/nenhuma experiência cadastrada/i);

    await user.click(screen.getByRole("button", { name: /adicionar experiência/i }));
    await user.type(screen.getByLabelText(/^Empresa/), "Globalthings");
    await user.type(screen.getByLabelText(/^Cargo/), "Engenheiro de Software");
    await user.type(
      screen.getByLabelText("Responsabilidades"),
      "Mantive APIs em C#.\n\nModelei o banco em PostgreSQL.",
    );
    await user.type(screen.getByLabelText("Tecnologias"), "C#, .NET, , PostgreSQL");
    await user.click(screen.getByRole("button", { name: /salvar experiência/i }));

    await waitFor(() => expect(mocked.createExperience).toHaveBeenCalledTimes(1));
    const payload = mocked.createExperience.mock.calls[0][0];
    expect(payload.company).toBe("Globalthings");
    expect(payload.responsibilities).toEqual([
      "Mantive APIs em C#.",
      "Modelei o banco em PostgreSQL.",
    ]);
    expect(payload.technologies).toEqual(["C#", ".NET", "PostgreSQL"]);
  });

  it("refuses to save until the company and the role are filled in", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ExperienceListEditor />);
    await screen.findByText(/nenhuma experiência cadastrada/i);

    await user.click(screen.getByRole("button", { name: /adicionar experiência/i }));

    expect(screen.getByRole("button", { name: /salvar experiência/i })).toBeDisabled();
    await user.type(screen.getByLabelText(/^Empresa/), "Globalthings");
    expect(screen.getByRole("button", { name: /salvar experiência/i })).toBeDisabled();
    await user.type(screen.getByLabelText(/^Cargo/), "Dev");
    expect(screen.getByRole("button", { name: /salvar experiência/i })).toBeEnabled();
  });

  it("never sends an end date for a position marked as current", async () => {
    const user = userEvent.setup();
    mocked.createExperience.mockResolvedValue(buildExperience());
    renderWithProviders(<ExperienceListEditor />);
    await screen.findByText(/nenhuma experiência cadastrada/i);

    await user.click(screen.getByRole("button", { name: /adicionar experiência/i }));
    await user.type(screen.getByLabelText(/^Empresa/), "Globalthings");
    await user.type(screen.getByLabelText(/^Cargo/), "Dev");
    await user.type(screen.getByLabelText("Fim"), "2024-01-01");
    await user.click(screen.getByLabelText(/ainda estou nesta posição/i));
    await user.click(screen.getByRole("button", { name: /salvar experiência/i }));

    await waitFor(() => expect(mocked.createExperience).toHaveBeenCalledTimes(1));
    const payload = mocked.createExperience.mock.calls[0][0];
    expect(payload.is_current).toBe(true);
    expect(payload.ended_on).toBeNull();
  });

  it("shows a stored position with its period and its counts", async () => {
    mocked.listExperiences.mockResolvedValue([buildExperience()]);
    renderWithProviders(<ExperienceListEditor />);

    expect(await screen.findByText(/·\s*Globalthings/)).toBeInTheDocument();
    expect(screen.getByText(/atual/)).toBeInTheDocument();
    expect(screen.getByText(/2 responsabilidades · 1 resultado · 1 projeto/)).toBeInTheDocument();
  });

  it("edits a stored position without restating the whole master resume", async () => {
    const user = userEvent.setup();
    mocked.listExperiences.mockResolvedValue([buildExperience()]);
    mocked.updateExperience.mockResolvedValue(buildExperience({ role: "Tech Lead" }));
    renderWithProviders(<ExperienceListEditor />);
    await screen.findByText(/·\s*Globalthings/);

    await user.click(screen.getByRole("button", { name: /^editar$/i }));
    const role = screen.getByLabelText(/^Cargo/);
    await user.clear(role);
    await user.type(role, "Tech Lead");
    await user.click(screen.getByRole("button", { name: /salvar experiência/i }));

    await waitFor(() => expect(mocked.updateExperience).toHaveBeenCalledTimes(1));
    const [id, payload] = mocked.updateExperience.mock.calls[0];
    expect(id).toBe(1);
    expect(payload.role).toBe("Tech Lead");
  });

  it("asks before removing a position, and says what happens to existing applications", async () => {
    const user = userEvent.setup();
    mocked.listExperiences.mockResolvedValue([buildExperience()]);
    mocked.deleteExperience.mockResolvedValue(undefined);
    renderWithProviders(<ExperienceListEditor />);
    await screen.findByText(/·\s*Globalthings/);

    await user.click(screen.getByRole("button", { name: /remover engenheiro de software/i }));

    expect(mocked.deleteExperience).not.toHaveBeenCalled();
    expect(screen.getByText(/continuam com o texto delas/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^remover$/i }));
    await waitFor(() => expect(mocked.deleteExperience).toHaveBeenCalledWith(1));
  });

  it("states that a vacancy reorders these experiences rather than rewriting them", async () => {
    renderWithProviders(<ExperienceListEditor />);

    expect(
      await screen.findByText(/reordenadas e reenfatizadas — nunca reescritas/i),
    ).toBeInTheDocument();
  });
});
