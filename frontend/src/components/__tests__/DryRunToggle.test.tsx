/**
 * Dry run is the outermost safety net. Turning it OFF is the only direction
 * that adds risk, so it must cost the operator a deliberate second step; turning
 * it back ON must never be slowed down.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DryRunToggle } from "@/components/DryRunToggle";
import { queryKeys } from "@/hooks/useApi";
import { updateSettings } from "@/services/profile";
import type * as ProfileService from "@/services/profile";
import { buildSettings } from "@/test/factories";
import { createTestQueryClient, renderWithProviders } from "@/test/utils";

// Only the write is faked: everything else in the module keeps its real shape,
// so a renamed export breaks the test instead of silently stubbing itself out.
vi.mock("@/services/profile", async (importOriginal) => ({
  ...(await importOriginal<typeof ProfileService>()),
  updateSettings: vi.fn(),
}));

const updateSettingsMock = vi.mocked(updateSettings);
const CONFIRM_TITLE = /desligar o modo de teste\?/i;

function renderToggle(dryRun: boolean) {
  const queryClient = createTestQueryClient();
  queryClient.setQueryData(queryKeys.settings(), buildSettings({ dry_run: dryRun }));
  return renderWithProviders(<DryRunToggle />, { queryClient });
}

describe("DryRunToggle", () => {
  beforeEach(() => {
    updateSettingsMock.mockReset();
  });

  it("asks for confirmation before turning dry run off", async () => {
    const user = userEvent.setup();
    updateSettingsMock.mockResolvedValue(buildSettings({ dry_run: false }));
    renderToggle(true);

    await user.click(screen.getByRole("switch"));

    // Flipping the switch alone must not reach the API.
    expect(updateSettingsMock).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(CONFIRM_TITLE)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^desligar o modo de teste$/i }));

    await waitFor(() => expect(updateSettingsMock).toHaveBeenCalledTimes(1));
    expect(updateSettingsMock).toHaveBeenCalledWith({ dry_run: false });
  });

  it("does not turn dry run off when the confirmation is dismissed", async () => {
    const user = userEvent.setup();
    renderToggle(true);

    await user.click(screen.getByRole("switch"));
    await user.click(screen.getByRole("button", { name: /manter o modo de teste ligado/i }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(updateSettingsMock).not.toHaveBeenCalled();
  });

  it("turns dry run back on without any confirmation step", async () => {
    const user = userEvent.setup();
    updateSettingsMock.mockResolvedValue(buildSettings({ dry_run: true }));
    renderToggle(false);

    await user.click(screen.getByRole("switch"));

    await waitFor(() => expect(updateSettingsMock).toHaveBeenCalledTimes(1));
    expect(updateSettingsMock).toHaveBeenCalledWith({ dry_run: true });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
