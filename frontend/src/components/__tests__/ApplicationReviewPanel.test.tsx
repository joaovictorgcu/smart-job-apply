/**
 * The approval gate.
 *
 * "Aprovar e enviar" is the only control in the whole app that can reach
 * LinkedInService.submit(), so these tests pin the exact conditions under which
 * it is clickable. They describe the component as it behaves today; where that
 * differs from the intent, the gap is a skipped test, never a silent fix.
 */

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ApplicationReviewPanel } from "@/components/ApplicationReviewPanel";
import { queryKeys } from "@/hooks/useApi";
import {
  buildApplicationDetail,
  buildScreeningAnswer,
  buildSettings,
} from "@/test/factories";
import { createTestQueryClient, renderWithProviders } from "@/test/utils";
import type { ApplicationDetail, UserSettings } from "@/types/api";

const APPROVE = /aprovar e enviar/i;

function renderPanel(
  application: ApplicationDetail,
  settings: UserSettings = buildSettings({ dry_run: false }),
) {
  const queryClient = createTestQueryClient();
  // Dry run is read from settings, so it has to be in the cache before render:
  // an undefined settings query would gate the button for the wrong reason.
  queryClient.setQueryData(queryKeys.settings(), settings);
  return renderWithProviders(<ApplicationReviewPanel application={application} />, {
    queryClient,
  });
}

describe("ApplicationReviewPanel approval gate", () => {
  it("enables approval when every screening answer is confirmed", () => {
    renderPanel(
      buildApplicationDetail({
        screening_answers: [buildScreeningAnswer({ needs_review: false })],
      }),
    );

    expect(screen.getByRole("button", { name: APPROVE })).toBeEnabled();
    expect(screen.getByText("Todas as respostas confirmadas")).toBeInTheDocument();
  });

  it("disables approval while any screening answer still needs review", () => {
    renderPanel(
      buildApplicationDetail({
        screening_answers: [
          buildScreeningAnswer({ needs_review: false }),
          buildScreeningAnswer({
            question: "Você aceita trabalhar presencialmente?",
            answer: "Sim",
            question_type: "text",
            confidence: "low",
            needs_review: true,
            field_id: "onsite",
          }),
        ],
      }),
    );

    expect(screen.getByRole("button", { name: APPROVE })).toBeDisabled();
    // The reason is stated, not merely implied by a grey button.
    expect(screen.getByText("1 resposta precisa de revisão")).toBeInTheDocument();
  });

  it("keeps approval disabled after confirming an answer until the edit is saved", async () => {
    const user = userEvent.setup();
    renderPanel(
      buildApplicationDetail({
        screening_answers: [
          buildScreeningAnswer({
            question: "Você aceita trabalhar presencialmente?",
            answer: "Sim",
            question_type: "text",
            confidence: "low",
            needs_review: true,
            field_id: "onsite",
          }),
        ],
      }),
    );

    await user.click(screen.getByRole("button", { name: /está correta/i }));

    // The flag is cleared locally, so the gate moves to the unsaved-edit check:
    // what LinkedIn receives is the saved draft, not what is on screen.
    expect(screen.getByText("Todas as respostas confirmadas")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: APPROVE })).toBeDisabled();
    expect(screen.getByText("Edições não salvas")).toBeInTheDocument();
  });

  it("disables approval while dry run is on, even with nothing else pending", () => {
    renderPanel(buildApplicationDetail(), buildSettings({ dry_run: true }));

    expect(screen.getByRole("button", { name: APPROVE })).toBeDisabled();
    expect(screen.getByText(/o modo de teste está ligado/i)).toBeInTheDocument();
  });

  it("disables approval unless the application is awaiting review", () => {
    renderPanel(buildApplicationDetail({ status: "draft" }));

    expect(screen.getByRole("button", { name: APPROVE })).toBeDisabled();
  });

  /*
   * FINDING, not a regression: the panel gates on the per-answer `needs_review`
   * flags only. The application-level `needs_human_input` field is never read
   * here, so an application the backend marked as needing a human is still
   * approvable as long as its individual answers are confirmed. Whether that
   * flag should also block is a product decision; changing the gate is out of
   * scope for the task that added these tests.
   */
  it.todo("blocks approval while application.needs_human_input is true");
});
