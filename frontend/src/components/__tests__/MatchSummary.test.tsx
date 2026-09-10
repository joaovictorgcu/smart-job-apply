/**
 * "Por que esta vaga?" — the part of the answer a reader can check.
 *
 * What is pinned here is honesty rather than layout: a gap is always named,
 * the sentence never claims the resume covers something it does not, and a
 * posting with nothing comparable says so instead of rendering as a total
 * mismatch.
 */

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MatchSummary } from "@/components/MatchSummary";
import { renderWithProviders } from "@/test/utils";
import type { Recommendation } from "@/types/api";

function build(overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    verdict: "strong",
    score: 92,
    covered: [".NET", "React", "APIs REST"],
    missing: ["Azure"],
    prioritized: [],
    covered_total: 3,
    asked_total: 4,
    coverage_pct: 75,
    has_evidence: true,
    ...overrides,
  };
}

describe("MatchSummary", () => {
  it("names the band in words, not only as a number", () => {
    renderWithProviders(<MatchSummary recommendation={build()} />);

    expect(screen.getByText("Excelente compatibilidade")).toBeInTheDocument();
  });

  it("lists what you have and what you do not, side by side", () => {
    renderWithProviders(<MatchSummary recommendation={build()} />);

    expect(screen.getByText(".NET")).toBeInTheDocument();
    expect(screen.getByText("Azure")).toBeInTheDocument();
  });

  it("states the gap as a gap and promises not to paper over it", () => {
    const { container } = renderWithProviders(<MatchSummary recommendation={build()} />);

    // Asserted on the flattened text: the sentence is built from interpolated
    // fragments, so it spans several text nodes.
    expect(container.textContent).toMatch(/ponto de atenção/i);
    expect(container.textContent).toMatch(/nada disso é acrescentado ao seu currículo/i);
  });

  it("counts the requirements it is talking about", () => {
    const { container } = renderWithProviders(<MatchSummary recommendation={build()} />);

    expect(container.textContent).toMatch(/você atende 3 de 4 requisitos citados/i);
  });

  it("says so when the posting named nothing comparable", () => {
    renderWithProviders(
      <MatchSummary
        recommendation={build({
          covered: [],
          missing: [],
          covered_total: 0,
          asked_total: 0,
          has_evidence: false,
        })}
      />,
    );

    expect(screen.getByText(/não cita tecnologias específicas/i)).toBeInTheDocument();
    expect(screen.queryByText(/você atende/i)).not.toBeInTheDocument();
  });

  it("does not claim coverage when there is none", () => {
    const { container } = renderWithProviders(
      <MatchSummary
        recommendation={build({
          verdict: "weak",
          score: 30,
          covered: [],
          covered_total: 0,
          missing: ["Rust", "Elixir"],
          asked_total: 2,
        })}
      />,
    );

    expect(container.textContent).toMatch(/nenhum dos 2 requisitos citados/i);
    expect(screen.getByText("Compatibilidade baixa")).toBeInTheDocument();
  });

  it("renders nothing at all without a recommendation", () => {
    // Not `toBeEmptyDOMElement`: the harness's toast provider owns a container
    // of its own, and this is about the summary contributing no text.
    const { container } = renderWithProviders(<MatchSummary recommendation={null} />);

    expect(container.textContent).toBe("");
  });

  it("drops the prose in compact mode but keeps the gap visible", () => {
    renderWithProviders(<MatchSummary recommendation={build()} compact />);

    expect(screen.queryByText(/por que esta vaga/i)).not.toBeInTheDocument();
    expect(screen.getByText("Azure")).toBeInTheDocument();
  });
});
