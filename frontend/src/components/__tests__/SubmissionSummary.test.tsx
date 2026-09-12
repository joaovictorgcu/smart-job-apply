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
import {
  buildApplicationDetail,
  buildApplicationResume,
  buildScreeningAnswer,
} from "@/test/factories";
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
  it("names the vacancy and the file that goes out", async () => {
    const { container } = render({ resume_filename: "user_1_resume.pdf" });

    expect(screen.getByText("O que será enviado")).toBeInTheDocument();
    await waitFor(() => expect(container.textContent).toMatch(/3 alterações/i));
  });

  it("says the adapted version is the file, once there is one", async () => {
    // Getting this wrong in either direction misleads the reader at the exact
    // moment they decide what an employer receives.
    const { container } = render({ resume_filename: "user_1_resume.pdf" });

    await waitFor(() =>
      expect(container.textContent).toMatch(/a sua versão para esta vaga, em pdf/i),
    );
    expect(screen.getByRole("link", { name: /ver o pdf que será anexado/i })).toHaveAttribute(
      "href",
      "/api/resumes/applications/5/pdf",
    );
  });

  it("falls back to the uploaded PDF when there is no copy to draw from", async () => {
    // A 404 is the normal "no copy yet" state; the hook maps it to null.
    mocked.fetchApplicationResume.mockResolvedValue(
      null as unknown as ReturnType<typeof buildApplicationResume>,
    );

    const { container } = render({ resume_filename: "user_1_resume.pdf" });

    await waitFor(() => expect(container.textContent).toMatch(/user_1_resume/));
    expect(container.textContent).toMatch(/ainda não tem uma versão própria/i);
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
        buildScreeningAnswer({ question: "Anos de Python?", answer: "6" }),
        buildScreeningAnswer({
          question: "Autorização de trabalho?",
          answer: "Sim",
          question_type: "text",
          confidence: "low",
          needs_review: true,
          field_id: "b",
        }),
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
