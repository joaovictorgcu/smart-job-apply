/**
 * The master resume against the one this vacancy gets.
 *
 * The claim under test is "how little changed", so the assertions are about
 * the four counters and the one with teeth: a measured zero inventions reads
 * as a result, and anything else has to read as a stop sign rather than a
 * footnote.
 */

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResumeComparisonPanel } from "@/components/ResumeComparisonPanel";
import { renderWithProviders } from "@/test/utils";
import type { ResumeComparison } from "@/types/api";

function build(overrides: Partial<ResumeComparison> = {}): ResumeComparison {
  return {
    moves: [
      {
        experience_id: 3,
        company: "Initech",
        role: "Backend Developer",
        from_position: 3,
        to_position: 1,
        promoted_bullets: 2,
        matched_terms: [".NET", "React"],
      },
      {
        experience_id: 1,
        company: "Acme",
        role: "Dev",
        from_position: 1,
        to_position: 2,
        promoted_bullets: 0,
        matched_terms: [],
      },
    ],
    highlighted_technologies: [".NET", "React"],
    promoted_bullets: 2,
    invented: [],
    experiences_reordered: 2,
    sections_adjusted: 1,
    changes_total: 5,
    is_clean: true,
    is_comparable: true,
    ...overrides,
  };
}

describe("ResumeComparisonPanel", () => {
  it("leads with the change budget", () => {
    renderWithProviders(<ResumeComparisonPanel comparison={build()} />);

    expect(screen.getByText("alterações no total")).toBeInTheDocument();
    expect(screen.getByText("tecnologias destacadas")).toBeInTheDocument();
    expect(screen.getByText("trechos reordenados")).toBeInTheDocument();
    expect(screen.getByText("informações inventadas")).toBeInTheDocument();
  });

  it("states a clean copy as a measured result, not a promise", () => {
    const { container } = renderWithProviders(<ResumeComparisonPanel comparison={build()} />);

    expect(container.textContent).toMatch(/tudo nesta versão veio do seu currículo principal/i);
  });

  it("turns an invented term into a stop sign naming it", () => {
    const { container } = renderWithProviders(
      <ResumeComparisonPanel comparison={build({ invented: ["Kubernetes"], is_clean: false })} />,
    );

    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
    expect(container.textContent).toMatch(/confira antes de aprovar/i);
    expect(container.textContent).not.toMatch(/tudo nesta versão veio/i);
  });

  it("says where an experience moved from and why", () => {
    const { container } = renderWithProviders(<ResumeComparisonPanel comparison={build()} />);

    expect(screen.getByText("Backend Developer — Initech")).toBeInTheDocument();
    expect(container.textContent).toMatch(/3ª/);
    expect(container.textContent).toMatch(/por causa de \.NET, React/);
  });

  it("says a highlighted technology was already there", () => {
    const { container } = renderWithProviders(<ResumeComparisonPanel comparison={build()} />);

    expect(container.textContent).toMatch(/já estavam no seu currículo/i);
  });

  it("explains why it cannot compare a stale copy", () => {
    const { container } = renderWithProviders(
      <ResumeComparisonPanel comparison={build({ is_comparable: false })} />,
    );

    expect(container.textContent).toMatch(/editou o seu currículo principal depois/i);
    expect(screen.queryByText("alterações no total")).not.toBeInTheDocument();
  });

  it("says plainly when nothing changed at all", () => {
    const { container } = renderWithProviders(
      <ResumeComparisonPanel
        comparison={build({
          moves: [],
          highlighted_technologies: [],
          experiences_reordered: 0,
          sections_adjusted: 0,
          promoted_bullets: 0,
          changes_total: 0,
        })}
      />,
    );

    expect(container.textContent).toMatch(/é o seu currículo principal como ele está/i);
  });

  it("renders nothing without a comparison", () => {
    const { container } = renderWithProviders(<ResumeComparisonPanel comparison={null} />);

    expect(container.textContent).toBe("");
  });
});
