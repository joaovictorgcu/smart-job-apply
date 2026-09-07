/**
 * The external channel's half of the review panel.
 *
 * An application to a posting on the company's own site has no form this app can
 * send, so the approval gate must not be offered at all — and the one control it
 * does get, "Já me candidatei", records a human act rather than performing one.
 * These tests pin both halves: the submit button is absent, and the recording
 * control is not secretly gated on the things that guard sending.
 */

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ApplicationReviewPanel } from "@/components/ApplicationReviewPanel";
import { queryKeys } from "@/hooks/useApi";
import { buildApplicationDetail, buildJob, buildSettings } from "@/test/factories";
import { createTestQueryClient, renderWithProviders } from "@/test/utils";
import type { ApplicationDetail, UserSettings } from "@/types/api";

const APPROVE = /aprovar e enviar/i;
const RECORD = /já me candidatei/i;

function buildExternal(overrides: Partial<ApplicationDetail> = {}): ApplicationDetail {
  return buildApplicationDetail({
    channel: "external",
    screening_answers: [],
    job: buildJob({
      source: "gupy",
      easy_apply: false,
      url: "https://empresa.gupy.io/job/eng-backend",
      application_id: 5,
    }),
    ...overrides,
  });
}

function renderPanel(
  application: ApplicationDetail,
  settings: UserSettings = buildSettings({ dry_run: false }),
) {
  const queryClient = createTestQueryClient();
  queryClient.setQueryData(queryKeys.settings(), settings);
  return renderWithProviders(<ApplicationReviewPanel application={application} />, {
    queryClient,
  });
}

describe("ApplicationReviewPanel on the external channel", () => {
  it("offers the company's own site instead of an approval button", () => {
    renderPanel(buildExternal());

    expect(screen.queryByRole("button", { name: APPROVE })).not.toBeInTheDocument();

    const link = screen.getByRole("link", { name: /candidatar-se no site da empresa/i });
    expect(link).toHaveAttribute("href", "https://empresa.gupy.io/job/eng-backend");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("offers a control to record that the application was made", () => {
    renderPanel(buildExternal());

    expect(screen.getByRole("button", { name: RECORD })).toBeEnabled();
    expect(screen.getByText(/o app não envia nada por você/i)).toBeInTheDocument();
  });

  it("keeps recording available while dry run is on, because nothing is sent", () => {
    // Dry run guards what the app sends to LinkedIn. This sends nothing, so
    // blocking it would only suppress the data the statistics are built from.
    renderPanel(buildExternal(), buildSettings({ dry_run: true }));

    expect(screen.getByRole("button", { name: RECORD })).toBeEnabled();
  });

  it("asks for a confirmation before recording, and says it sends nothing", async () => {
    const user = userEvent.setup();
    renderPanel(buildExternal());

    await user.click(screen.getByRole("button", { name: RECORD }));

    expect(
      screen.getByRole("heading", { name: /registrar que você se candidatou/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/isto não envia nada/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /registrar candidatura/i })).toBeInTheDocument();
  });

  it("cannot be recorded twice: an already-recorded application has no control", () => {
    renderPanel(buildExternal({ status: "submitted", outcome: "applied" }));

    expect(screen.getByRole("button", { name: RECORD })).toBeDisabled();
    expect(screen.getByText(/já está no funil e nas estatísticas/i)).toBeInTheDocument();
  });

  it("leaves the Easy Apply panel exactly as it was", () => {
    renderPanel(buildApplicationDetail());

    expect(screen.getByRole("button", { name: APPROVE })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: RECORD })).not.toBeInTheDocument();
  });
});
