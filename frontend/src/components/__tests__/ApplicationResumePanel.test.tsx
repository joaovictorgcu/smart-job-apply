/**
 * The panel that answers "which resume is this application using, and why".
 *
 * The service module is mocked rather than the cache seeded, because half of
 * what matters here is what the panel *sends*: an edit must produce a PATCH
 * scoped to this application, and re-adapting must not be reachable by accident.
 * The loading, empty, error and saving states are pinned too — an application
 * created before this feature legitimately has no copy, and that must read as an
 * offer to adapt, never as a failure.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApplicationResumePanel } from "@/components/ApplicationResumePanel";
import {
  buildAdaptedExperience,
  buildApplicationResume,
  buildResumeVersion,
} from "@/test/factories";
import { renderWithProviders } from "@/test/utils";
import type { ApplicationResume } from "@/types/api";

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

const APPLICATION_ID = 5;

function notFound(): Error & { status: number } {
  return Object.assign(new Error("Not found"), { status: 404 });
}

function render() {
  return renderWithProviders(
    <MemoryRouter>
      <ApplicationResumePanel applicationId={APPLICATION_ID} />
    </MemoryRouter>,
  );
}

async function renderAdapted(overrides: Partial<ApplicationResume> = {}) {
  mocked.fetchApplicationResume.mockResolvedValue(buildApplicationResume(overrides));
  const result = render();
  await screen.findByText(/versão 1/i);
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocked.listResumeVersions.mockResolvedValue([]);
});

describe("ApplicationResumePanel states", () => {
  it("reports loading while the copy is being fetched", () => {
    mocked.fetchApplicationResume.mockReturnValue(new Promise(() => {}));

    render();

    expect(document.querySelector('[aria-busy="true"]')).toBeTruthy();
    expect(screen.getByText("Currículo desta candidatura")).toBeInTheDocument();
  });

  it("offers to adapt when the application has no copy yet", async () => {
    mocked.fetchApplicationResume.mockRejectedValue(notFound());

    render();

    expect(
      await screen.findByText(/ainda não tem currículo próprio/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /adaptar currículo para esta vaga/i }),
    ).toBeEnabled();
  });

  it("states the failure instead of pretending there is no copy", async () => {
    mocked.fetchApplicationResume.mockRejectedValue(
      Object.assign(new Error("boom"), { status: 500 }),
    );

    render();

    expect(
      await screen.findByText(/não foi possível carregar o currículo desta candidatura/i),
    ).toBeInTheDocument();
  });
});

describe("ApplicationResumePanel document", () => {
  it("names the vacancy the copy was adapted to", async () => {
    await renderAdapted();

    expect(
      screen.getByText(/adaptado para desenvolvedor backend \.net sênior/i),
    ).toBeInTheDocument();
  });

  it("shows the adherence figure with the posting context", async () => {
    await renderAdapted();

    expect(screen.getByText(/aderência 87%/i)).toBeInTheDocument();
  });

  it("hides the adherence figure when the posting gave no signal", async () => {
    await renderAdapted({ fit_factors: [], fit_score: 0 });

    expect(screen.queryByText(/aderência/i)).not.toBeInTheDocument();
  });

  it("lists the experiences in the order the derivation chose", async () => {
    await renderAdapted();

    const headings = screen.getAllByText(/·\s*(Globalthings|Nuvem Retail)/);
    expect(headings[0]).toHaveTextContent("Globalthings");
    expect(headings[1]).toHaveTextContent("Nuvem Retail");
  });

  it("says how much of an experience moved up for this vacancy", async () => {
    await renderAdapted();

    expect(screen.getByText(/100% de relação com a vaga/i)).toBeInTheDocument();
    expect(screen.getByText(/2 itens promovidos/i)).toBeInTheDocument();
  });

  it("warns when the master resume moved on without this copy", async () => {
    await renderAdapted({ is_stale: true });

    expect(screen.getByText(/o seu currículo principal mudou/i)).toBeInTheDocument();
    // Stale is not wrong: the application keeps presenting what is on screen.
    expect(screen.getByText(/continua usando exatamente o que você está vendo/i)).toBeTruthy();
  });

  it("marks a copy the user has edited by hand", async () => {
    await renderAdapted({ was_edited: true });

    expect(screen.getByText(/editada por você/i)).toBeInTheDocument();
  });
});

describe("ApplicationResumePanel change report", () => {
  it("groups what was adapted for this vacancy", async () => {
    const user = userEvent.setup();
    await renderAdapted();

    await user.click(screen.getByRole("tab", { name: /o que foi adaptado/i }));

    expect(screen.getByText("Experiências priorizadas")).toBeInTheDocument();
    expect(screen.getByText("Descrições reordenadas")).toBeInTheDocument();
    expect(screen.getByText("Competências destacadas")).toBeInTheDocument();
    expect(screen.getByText("Tecnologias enfatizadas")).toBeInTheDocument();
    expect(screen.getByText("Projetos relevantes")).toBeInTheDocument();
    expect(screen.getByText(/2 de 3 itens subiram na descrição/i)).toBeInTheDocument();
  });

  it("breaks the adherence figure down into arguable factors", async () => {
    const user = userEvent.setup();
    await renderAdapted();

    await user.click(screen.getByRole("tab", { name: /o que foi adaptado/i }));

    expect(screen.getByText("Tecnologias pedidas")).toBeInTheDocument();
    expect(screen.getByText("Tempo de experiência")).toBeInTheDocument();
    expect(screen.getByText("9/5 anos")).toBeInTheDocument();
  });

  it("surfaces what the history cannot back instead of hiding it", async () => {
    const user = userEvent.setup();
    await renderAdapted();

    await user.click(screen.getByRole("tab", { name: /o que foi adaptado/i }));

    expect(screen.getByText(/o anúncio pede e o histórico não cobre/i)).toBeInTheDocument();
    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
  });

  it("says plainly when nothing was reorganised", async () => {
    const user = userEvent.setup();
    await renderAdapted({ changes: [], fit_factors: [], fit_score: 0 });

    await user.click(screen.getByRole("tab", { name: /o que foi adaptado/i }));

    expect(screen.getByText(/nada foi reorganizado/i)).toBeInTheDocument();
  });
});

describe("ApplicationResumePanel versions", () => {
  it("links back to the master resume and to the sibling versions", async () => {
    const user = userEvent.setup();
    mocked.listResumeVersions.mockResolvedValue([
      buildResumeVersion(),
      buildResumeVersion({
        application_id: 9,
        job_id: 11,
        job_title: "Pessoa Desenvolvedora Full Stack",
        job_company: "Trilha Educação",
        fit_score: 64,
      }),
    ]);
    await renderAdapted();

    await user.click(screen.getByRole("tab", { name: /outras versões/i }));

    const master = await screen.findByRole("link", { name: /currículo principal/i });
    expect(master).toHaveAttribute("href", "/profile");
    const sibling = screen.getByRole("link", { name: /pessoa desenvolvedora full stack/i });
    expect(sibling).toHaveAttribute("href", "/applications/9");
    // This application's own version is not listed as an "other".
    expect(
      screen.queryByRole("link", { name: /desenvolvedor backend \.net sênior/i }),
    ).not.toBeInTheDocument();
  });

  it("says so when this is the only version so far", async () => {
    const user = userEvent.setup();
    mocked.listResumeVersions.mockResolvedValue([buildResumeVersion()]);
    await renderAdapted();

    await user.click(screen.getByRole("tab", { name: /outras versões/i }));

    expect(await screen.findByText(/sua única versão adaptada/i)).toBeInTheDocument();
  });
});

describe("ApplicationResumePanel editing", () => {
  it("saves the edits against this application only", async () => {
    const user = userEvent.setup();
    mocked.updateApplicationResume.mockImplementation(async (_id, payload) =>
      buildApplicationResume({
        was_edited: true,
        headline: payload.headline ?? null,
        version: 1,
        updated_at: "2026-08-01T11:00:00Z",
      }),
    );
    await renderAdapted();

    await user.click(screen.getByRole("button", { name: /editar esta versão/i }));
    const headline = screen.getByLabelText("Título");
    await user.clear(headline);
    await user.type(headline, "Backend .NET");
    await user.click(screen.getByRole("button", { name: /salvar esta versão/i }));

    await waitFor(() => expect(mocked.updateApplicationResume).toHaveBeenCalledTimes(1));
    const [applicationId, payload] = mocked.updateApplicationResume.mock.calls[0];
    expect(applicationId).toBe(APPLICATION_ID);
    expect(payload.headline).toBe("Backend .NET");
    // The identity of each experience is never sent back: only its text.
    expect(payload.experiences?.[0]).toEqual({
      summary: "APIs corporativas e o portal de gestão de acessos.",
      responsibilities: [
        "Projetei APIs REST em C# e ASP.NET Core.",
        "Construí telas do portal em React e TypeScript.",
      ],
      technologies: ["C#", ".NET", "PostgreSQL", "React"],
      results: ["Reduzi o tempo de resposta das APIs de 800 ms para 210 ms."],
    });
  });

  it("keeps save disabled until something actually changed", async () => {
    const user = userEvent.setup();
    await renderAdapted();

    await user.click(screen.getByRole("button", { name: /editar esta versão/i }));

    expect(screen.getByRole("button", { name: /salvar esta versão/i })).toBeDisabled();
  });

  it("discards the edits on cancel without sending anything", async () => {
    const user = userEvent.setup();
    await renderAdapted();

    await user.click(screen.getByRole("button", { name: /editar esta versão/i }));
    await user.type(screen.getByLabelText("Título"), " editado");
    await user.click(screen.getByRole("button", { name: /^cancelar$/i }));

    expect(mocked.updateApplicationResume).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /editar esta versão/i })).toBeInTheDocument();
  });

  it("states that editing here leaves the master resume alone", async () => {
    await renderAdapted();

    expect(screen.getByText(/o currículo principal não muda/i)).toBeInTheDocument();
  });
});

describe("ApplicationResumePanel adapting again", () => {
  it("derives a new version for this application on request", async () => {
    const user = userEvent.setup();
    mocked.adaptApplicationResume.mockResolvedValue(
      buildApplicationResume({ version: 2, updated_at: "2026-08-01T12:00:00Z" }),
    );
    await renderAdapted();

    await user.click(screen.getByRole("button", { name: /adaptar novamente/i }));

    await waitFor(() => expect(mocked.adaptApplicationResume).toHaveBeenCalledWith(APPLICATION_ID));
    // A fresh derivation lands on the report: "what changed" is the question the
    // user just asked, so the panel answers it instead of making them find it.
    expect(await screen.findByText("Experiências priorizadas")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /^currículo$/i }));
    expect(screen.getByText(/versão 2/i)).toBeInTheDocument();
  });

  it("reports a failure to adapt without losing the stored copy", async () => {
    const user = userEvent.setup();
    mocked.adaptApplicationResume.mockRejectedValue(
      Object.assign(new Error("Adicione as suas experiências no Perfil."), { status: 412 }),
    );
    await renderAdapted();

    await user.click(screen.getByRole("button", { name: /adaptar novamente/i }));

    expect(
      await screen.findByText(/não foi possível adaptar o currículo/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/versão 1/i)).toBeInTheDocument();
  });

  it("re-derives from an empty state too", async () => {
    const user = userEvent.setup();
    mocked.fetchApplicationResume.mockRejectedValue(notFound());
    mocked.adaptApplicationResume.mockResolvedValue(buildApplicationResume());
    render();
    await screen.findByText(/ainda não tem currículo próprio/i);

    await user.click(screen.getByRole("button", { name: /adaptar currículo para esta vaga/i }));

    await waitFor(() => expect(mocked.adaptApplicationResume).toHaveBeenCalledWith(APPLICATION_ID));
    expect(await screen.findByText("Experiências priorizadas")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /^currículo$/i }));
    expect(screen.getByText(/versão 1/i)).toBeInTheDocument();
  });
});

describe("ApplicationResumePanel with an empty master resume", () => {
  it("points the user at the profile when there is no experience to prioritise", async () => {
    await renderAdapted({
      experiences: [],
      projects: [],
      changes: [],
      skills: [],
      highlighted_skills: [],
    });

    expect(screen.getByText(/nenhuma experiência no currículo principal/i)).toBeInTheDocument();
  });

  it("still renders an experience that matched nothing", async () => {
    await renderAdapted({
      experiences: [buildAdaptedExperience({ relevance: 0, matched_terms: [], promoted: 0 })],
    });

    expect(screen.queryByText(/de relação com a vaga/i)).not.toBeInTheDocument();
    expect(screen.getByText(/·\s*Globalthings/)).toBeInTheDocument();
  });
});
