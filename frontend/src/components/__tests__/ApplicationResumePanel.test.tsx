/**
 * The resume panel on an application.
 *
 * Two things must never blur on this screen: which job is being answered, and
 * which resume is answering it. These tests walk every real state — no version
 * yet, loaded, stale after a profile edit, flagged, and edited by hand — and
 * assert that the master resume is visibly the master and read-only there.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApplicationResumePanel } from "@/components/ApplicationResumePanel";
import { queryKeys } from "@/hooks/useApi";
import {
  deriveApplicationResume,
  updateApplicationResume,
} from "@/services/resumes";
import type * as ResumesService from "@/services/resumes";
import {
  buildApplicationDetail,
  buildApplicationResume,
  buildExperience,
} from "@/test/factories";
import { createTestQueryClient, renderWithProviders } from "@/test/utils";
import type { ApplicationResume } from "@/types/api";

// Only the writes are faked: the reads are seeded into the query cache, and
// everything else in the module keeps its real shape, so a renamed export
// breaks the test instead of silently stubbing itself out.
vi.mock("@/services/resumes", async (importOriginal) => ({
  ...(await importOriginal<typeof ResumesService>()),
  deriveApplicationResume: vi.fn(),
  updateApplicationResume: vi.fn(),
}));

const deriveMock = vi.mocked(deriveApplicationResume);
const updateMock = vi.mocked(updateApplicationResume);

const application = buildApplicationDetail({ id: 5 });

function renderPanel(resume: ApplicationResume | null) {
  const queryClient = createTestQueryClient();
  // Seeded rather than fetched: the panel's states are what is under test, not
  // the request, and the setup file fails any real network call.
  queryClient.setQueryData(queryKeys.applicationResume(application.id), resume);
  return renderWithProviders(<ApplicationResumePanel application={application} />, {
    queryClient,
  });
}

beforeEach(() => {
  deriveMock.mockReset();
  updateMock.mockReset();
});

describe("ApplicationResumePanel", () => {
  it("names the job this resume is for", () => {
    renderPanel(buildApplicationResume());

    expect(
      screen.getByText(/Engenheiro de Software Sênior — Globalthings/i),
    ).toBeInTheDocument();
  });

  it("offers to derive a version when the application has none", async () => {
    const user = userEvent.setup();
    deriveMock.mockResolvedValue(buildApplicationResume());
    renderPanel(null);

    expect(
      screen.getByText(/ainda não tem currículo próprio/i),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /gerar do currículo principal/i }));

    await waitFor(() => expect(deriveMock).toHaveBeenCalledWith(5));
  });

  it("shows what this version prioritises for the posting", () => {
    renderPanel(buildApplicationResume());

    expect(screen.getByText(/priorizado automaticamente/i)).toBeInTheDocument();
    expect(screen.getByText(/\.NET 8 · APIs REST · SQL Server/)).toBeInTheDocument();
    // The emphasis is visible on the experience itself, not only as a chip.
    expect(screen.getByText(/Priorizado aqui:/)).toBeInTheDocument();
  });

  it("keeps the master resume a separate, read-only tab", async () => {
    const user = userEvent.setup();
    renderPanel(buildApplicationResume());

    await user.click(screen.getByRole("tab", { name: /currículo principal/i }));

    expect(screen.getByText(/Ele é só leitura aqui/i)).toBeInTheDocument();
    // The way back to editing the master is a link out, never a second editor.
    expect(screen.getAllByRole("link", { name: /perfil/i }).length).toBeGreaterThan(0);
  });

  it("explains the difference against the master it was derived from", async () => {
    const user = userEvent.setup();
    renderPanel(buildApplicationResume());

    await user.click(screen.getByRole("tab", { name: /diferenças/i }));

    expect(screen.getByText(/em relação ao currículo principal/i)).toBeInTheDocument();
    expect(screen.getByText(/Resumo profissional/i)).toBeInTheDocument();
    expect(screen.getByText(/Descrição reescrita para destacar/i)).toBeInTheDocument();
  });

  it("says so when the posting has nothing in common with the resume", async () => {
    const user = userEvent.setup();
    const untouched = buildApplicationResume();
    renderPanel({
      ...untouched,
      focus: [],
      changes: [],
      document: untouched.base_document,
    });

    expect(screen.getByText(/nenhuma interseção/i)).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /diferenças/i }));
    expect(screen.getByText(/idêntica ao currículo principal/i)).toBeInTheDocument();
  });

  it("offers to re-derive when the master changed, without altering the version", () => {
    renderPanel(buildApplicationResume({ is_stale: true }));

    expect(screen.getByText(/continua exatamente como está/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /regerar do principal/i }),
    ).toBeEnabled();
  });

  it("flags a technology that is not in the master resume", () => {
    renderPanel(
      buildApplicationResume({ source: "user", invention_flags: ["Kubernetes"] }),
    );

    expect(screen.getByText(/Confira você mesmo/i)).toBeInTheDocument();
    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
  });

  it("saves an edited version through the editor", async () => {
    const user = userEvent.setup();
    const resume = buildApplicationResume();
    updateMock.mockResolvedValue({ ...resume, source: "user" });
    renderPanel(resume);

    await user.click(screen.getByRole("button", { name: /^editar$/i }));
    const summary = screen.getByLabelText(/resumo profissional nesta candidatura/i);
    await user.clear(summary);
    await user.type(summary, "Minha versão.");
    await user.click(screen.getByRole("button", { name: /salvar esta versão/i }));

    await waitFor(() => expect(updateMock).toHaveBeenCalledTimes(1));
    const [applicationId, document] = updateMock.mock.calls[0];
    expect(applicationId).toBe(5);
    expect(document.summary).toBe("Minha versão.");
    // Identity is not editable, so it goes back exactly as it came.
    expect(document.experiences[0].company).toBe("Globalthings");
  });

  it("locks company, role and period in the editor", async () => {
    const user = userEvent.setup();
    renderPanel(
      buildApplicationResume({
        document: {
          ...buildApplicationResume().document,
          experiences: [buildExperience({ focus: [".NET 8"] })],
        },
      }),
    );

    await user.click(screen.getByRole("button", { name: /^editar$/i }));

    expect(screen.getByText(/não são editáveis aqui/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^empresa$/i)).not.toBeInTheDocument();
  });
});
