/**
 * A card the user picks from, and what it must not hide.
 *
 * Preparation refuses a stale posting — one that vanished from the portal, or
 * whose deadline has passed. A card that says nothing lets someone select it
 * and only learn at the confirmation dialog that it was dropped, which is the
 * kind of thing that reads as the app being broken.
 *
 * The field existed on the API all along; the hand-written type had forgotten
 * it, so the UI could not render what the backend was already sending.
 * `tools/check_api_types.py` is what catches the next one.
 */

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JobCard } from "@/components/JobCard";
import { buildJob } from "@/test/factories";
import { renderWithProviders } from "@/test/utils";

describe("JobCard", () => {
  it("says a posting is gone instead of letting it look selectable", () => {
    renderWithProviders(
      <JobCard job={buildJob({ is_stale: true, expired_at: "2026-09-01T00:00:00Z" })} />,
    );

    expect(screen.getByText(/anúncio saiu do ar/i)).toBeInTheDocument();
  });

  it("distinguishes a closed deadline from a posting that vanished", () => {
    renderWithProviders(<JobCard job={buildJob({ is_stale: true, expired_at: null })} />);

    expect(screen.getByText(/prazo encerrado/i)).toBeInTheDocument();
  });

  it("says nothing about a live posting", () => {
    const { container } = renderWithProviders(<JobCard job={buildJob()} />);

    expect(container.textContent).not.toMatch(/saiu do ar|prazo encerrado/i);
  });
});
