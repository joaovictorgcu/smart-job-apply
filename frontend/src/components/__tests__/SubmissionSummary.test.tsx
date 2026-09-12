/**
 * Exactly what goes out, stated before anything that can edit it.
 *
 * Approving is a decision about the whole document, and the review screen is a
 * stack of editors. What is pinned here is that the summary describes the
 * *saved record* — which is what the submission rebuilds from — and that the
 * two facts a reviewer must not miss, a flagged answer and an invented term,
 * are impossible to scroll past.
 */

import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SubmissionSummary } from "@/components/SubmissionSummary";
import { buildApplicationDetail, buildApplicationResume } from "@/test/factories";
import { renderWithProviders } from "@/test/utils";
import type { ApplicationDetail, ResumeComparison } from "@/types/api";

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

function comparison(overrides: Partial<ResumeComparison> = {}): ResumeComparison {
  return {
    moves: [],
    highlighted_technologies: [],
    promoted_bullets: 0,
    invented: [],
    experiences_reordered: 2,
    sections_adjusted: 1,
    changes_total: 3,
    is_clean: true,
    is_comparable: true,
    ...overrides,
  };
}

function render(application: Partial<ApplicationDetail> = {}) {
  return renderWithProviders(
    <SubmissionSummary application={buildApplicationDetail(application)} />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocked.fetchApplicationResume.mockResolvedValue(
    buildApplicationResume({ comparison: comparison() }),
  );
});

describe("SubmissionSummary", () => {
  it("names the vacancy and the file that go out", async () => {
    const { container } = render({ resume_filename: "user_1_resume.pdf" });

    expect(screen.getByText("O que será enviado")).toBeInTheDocument();
    expect(screen.getByText("user_1_resume.pdf")).toBeInTheDocument();
    await waitFor(() =>
      expect(container.textContent).toMatch(/3 alterações em relação ao seu currículo principal/i),
    );
  });

  it("counts the letter rather than restating it", () => {
    const { container } = render({ cover_letter: "abcde" });

    expect(container.textContent).toMatch(/5 caracteres/);
  });

  it("says plainly when there is no letter at all", () => {
    const { container } = render({ cover_letter: null });

    expect(container.textContent).toMatch(/o formulário vai sem carta/i);
  });

  it("surfaces an answer still waiting for confirmation", () => {
    const { container } = render({
      screening_answers: [
        {
          question: "Anos de Python?",
          answer: "6",
          type: "number",
          options: [],
          confidence: "high",
          needs_review: false,
          field_id: "a",
        },
        {
          question: "Autorização de trabalho?",
          answer: "Sim",
          type: "text",
          options: [],
          confidence: "low",
          needs_review: true,
          field_id: "b",
        },
      ],
    });

    expect(container.textContent).toMatch(/2 respostas/);
    expect(container.textContent).toMatch(/1 precisa da sua confirmação antes de aprovar/i);
  });

  it("makes an invented term impossible to scroll past", async () => {
    mocked.fetchApplicationResume.mockResolvedValue(
      buildApplicationResume({
        comparison: comparison({ invented: ["Kubernetes"], is_clean: false }),
      }),
    );

    const { container } = render();

    await waitFor(() =>
      expect(container.textContent).toMatch(
        /Kubernetes não está no seu currículo principal/i,
      ),
    );
    expect(container.textContent).toMatch(/isto sai em seu nome/i);
  });

  it("changes what it promises on the external channel", () => {
    render({ channel: "external" });

    expect(screen.getByText("O que você vai levar")).toBeInTheDocument();
    expect(screen.queryByText("O que será enviado")).not.toBeInTheDocument();
  });
});
