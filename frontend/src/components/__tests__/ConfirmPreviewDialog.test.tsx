/**
 * The gate in front of form filling: the operator must see the volume and the
 * warnings, and tick an acknowledgement, before a browser starts clicking.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfirmPreviewDialog } from "@/components/ConfirmPreviewDialog";
import { buildPreview } from "@/test/factories";
import type { PreviewResponse } from "@/types/api";

const CONFIRM = /preencher 3 candidaturas/i;
const ACKNOWLEDGE = /entendo que isto vai abrir e preencher/i;

function renderDialog(preview: PreviewResponse, onConfirm = vi.fn()) {
  render(
    <ConfirmPreviewDialog
      open
      onClose={vi.fn()}
      preview={preview}
      onConfirm={onConfirm}
    />,
  );
  return { onConfirm };
}

describe("ConfirmPreviewDialog", () => {
  it("keeps the confirm button disabled until the acknowledgement is ticked", async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderDialog(buildPreview());

    const confirm = screen.getByRole("button", { name: CONFIRM });
    expect(confirm).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: ACKNOWLEDGE }));

    expect(confirm).toBeEnabled();
    await user.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("surfaces every warning it was given", () => {
    renderDialog(
      buildPreview({
        warnings: [
          "A sua sessão do LinkedIn não foi verificada hoje.",
          "Três vagas não são de Candidatura Simplificada.",
        ],
      }),
    );

    expect(
      screen.getByText("A sua sessão do LinkedIn não foi verificada hoje."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Três vagas não são de Candidatura Simplificada."),
    ).toBeInTheDocument();
  });

  it("warns when the selection exceeds the remaining daily quota", () => {
    renderDialog(buildPreview({ jobs_to_process: 3, remaining_today: 1, daily_cap: 20 }));

    expect(screen.getByText(/só restam/i)).toBeInTheDocument();
  });

  it("offers nothing to acknowledge when no job is eligible", () => {
    renderDialog(buildPreview({ jobs_to_process: 0 }));

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /nada para preencher/i })).toBeDisabled();
  });
});
