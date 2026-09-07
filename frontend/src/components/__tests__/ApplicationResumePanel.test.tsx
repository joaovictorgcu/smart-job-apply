/**
 * The panel where one application's own resume is read, understood and edited.
 *
 * What is asserted here is that the *behaviour is visible*, not merely stored:
 * the vacancy this version was built for is named on screen, the prioritised
 * skills and the chosen experience order are rendered, the same employer reads
 * differently on two applications, and the panel never breaks on an application
 * that has no version — which is every application prepared before this
 * existed.
 */

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ApplicationResumePanel } from "@/components/ApplicationResumePanel";
import { queryKeys } from "@/hooks/useApi";
import {
  buildApplicationResume,
  buildResumeFocus,
  buildResumeSections,
  buildTailoredExperience,
} from "@/test/factories";
import { createTestQueryClient, renderWithProviders } from "@/test/utils";
import type { ApplicationResume } from "@/types/api";

function renderPanel(
  resume: ApplicationResume | null,
  { applicationId = 5, aiConfigured = true } = {},
) {
  const queryClient = createTestQueryClient();
  queryClient.setQueryData(queryKeys.applicationResume(applicationId), resume);
  return renderWithProviders(
    <MemoryRouter>
      <ApplicationResumePanel applicationId={applicationId} aiConfigured={aiConfigured} />
    </MemoryRouter>,
    { queryClient },
  );
}

describe("ApplicationResumePanel", () => {
  it("names the panel and the vacancy this version was built for", () => {
    renderPanel(buildApplicationResume());

    expect(
      screen.getByRole("heading", { name: /currículo desta candidatura/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/versão criada para/i)).toBeInTheDocument();
    expect(
      screen.getByText("Desenvolvedor Backend .NET — Meridian Software"),
    ).toBeInTheDocument();
  });

  it("offers a way back to the master resume", () => {
    renderPanel(buildApplicationResume());

    const link = screen.getByRole("link", { name: /currículo principal/i });
    expect(link).toHaveAttribute("href", "/profile");
  });

  it("shows the prioritised skills and what the vacancy asked for", () => {
    renderPanel(
      buildApplicationResume({
        sections: buildResumeSections({
          prioritized_skills: [".NET", "C#", "Entity Framework"],
          other_skills: ["React", "Python"],
        }),
      }),
    );

    const skills = screen
      .getByText(/competências priorizadas/i)
      .parentElement as HTMLElement;
    expect(within(skills).getByText("Entity Framework")).toBeInTheDocument();
    expect(screen.getByText(/o que esta vaga pede/i)).toBeInTheDocument();
    // Nothing is lost — the rest is still there, just not first.
    expect(screen.getByText(/demais competências \(2\)/i)).toBeInTheDocument();
  });

  it("renders the selected experiences with their adapted description", () => {
    renderPanel(buildApplicationResume());

    expect(screen.getByText(/experiências, na ordem desta candidatura/i)).toBeInTheDocument();
    expect(screen.getByText(/Tech Lead/)).toBeInTheDocument();
    expect(
      screen.getByText(/aplicações backend em C# e .NET 8/i),
    ).toBeInTheDocument();
    // The emphasis this version gives the entry is on screen, with its score.
    expect(screen.getByText(/destaque · 100%/i)).toBeInTheDocument();
  });

  it("says which of the master's bullets this version left out", async () => {
    const user = userEvent.setup();
    renderPanel(buildApplicationResume());

    await user.click(screen.getByText(/1 ponto\(s\) do currículo principal fora desta versão/i));

    expect(screen.getByText(/mentoria de três desenvolvedores/i)).toBeInTheDocument();
  });

  it("shows the same employer differently on two applications", () => {
    // The requirement from the brief, at the level the user actually sees it.
    const forDotnet = buildApplicationResume();
    const forReact = buildApplicationResume({
      application_id: 6,
      job_title: "Desenvolvedor Full Stack React",
      focus: buildResumeFocus({
        title: "Desenvolvedor Full Stack React",
        keywords: ["React", "TypeScript"],
      }),
      sections: buildResumeSections({
        prioritized_skills: ["React", "TypeScript"],
        experiences: [
          buildTailoredExperience({
            description:
              "Integração das interfaces em React e TypeScript com as APIs de backend e o banco de dados.",
            highlights: [
              "Integração das interfaces em React e TypeScript com as APIs de backend e o banco de dados.",
            ],
            matched: ["React", "TypeScript"],
          }),
        ],
      }),
    });

    const first = renderPanel(forDotnet, { applicationId: 5 });
    expect(screen.getByText(/aplicações backend em C# e .NET 8/i)).toBeInTheDocument();
    first.unmount();

    renderPanel(forReact, { applicationId: 6 });
    expect(
      screen.getByText(/Integração das interfaces em React e TypeScript/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/aplicações backend em C# e .NET 8/i)).not.toBeInTheDocument();
  });

  it("surfaces the gaps it refused to paper over", () => {
    renderPanel(buildApplicationResume());

    expect(screen.getByText(/lacunas que esta versão não disfarça/i)).toBeInTheDocument();
    expect(screen.getByText("Elixir")).toBeInTheDocument();
  });

  it("flags a version that is behind the master without rewriting it", () => {
    renderPanel(buildApplicationResume({ is_stale: true }));

    expect(screen.getByText(/currículo principal mudou depois/i)).toBeInTheDocument();
    // Still showing the version as reviewed, not a silently refreshed one.
    expect(screen.getByLabelText(/currículo desta candidatura/i)).toHaveValue(
      buildApplicationResume().content,
    );
  });

  it("lets the user edit this version, and only enables saving once it changed", async () => {
    const user = userEvent.setup();
    renderPanel(buildApplicationResume());

    const save = screen.getByRole("button", { name: /salvar nesta candidatura/i });
    expect(save).toBeDisabled();

    await user.type(screen.getByLabelText(/currículo desta candidatura/i), " ajuste");

    expect(save).toBeEnabled();
    expect(screen.getByRole("button", { name: /descartar edições/i })).toBeInTheDocument();
  });

  it("offers to build a version when the application has none, without erroring", () => {
    // Every application prepared before this feature existed looks like this.
    renderPanel(null);

    expect(screen.getByRole("button", { name: /gerar para esta vaga/i })).toBeEnabled();
    expect(screen.getByText(/ainda não existe uma versão para esta candidatura/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /salvar nesta candidatura/i })).not.toBeInTheDocument();
    // And it still points at the master resume.
    expect(screen.getByRole("link", { name: /currículo principal/i })).toBeInTheDocument();
  });

  it("renders a legacy version from its content alone", () => {
    renderPanel(
      buildApplicationResume({
        sections: null,
        focus: null,
        strategy: "ai",
        content: "# Currículo antigo",
      }),
    );

    expect(screen.getByText(/só o documento está disponível/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/currículo desta candidatura/i)).toHaveValue("# Currículo antigo");
  });

  it("does not offer the AI rewrite without an API key", () => {
    renderPanel(buildApplicationResume(), { aiConfigured: false });

    expect(screen.getByRole("button", { name: /reescrever com ia/i })).toBeDisabled();
    // The version itself is still there and still editable — it never needed a key.
    expect(screen.getByLabelText(/currículo desta candidatura/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /gerar novamente/i })).toBeEnabled();
  });
});
