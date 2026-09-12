/**
 * Erasing the account, from the screen.
 *
 * What matters here is the order of the guards, not the layout: nothing is sent
 * until the user asks twice and types the password, a wrong password leaves the
 * session alone, and a successful deletion does not leave the app sitting on a
 * screen whose account no longer exists.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as RouterModule from "react-router-dom";

import { DangerZone } from "@/components/DangerZone";
import { renderWithProviders } from "@/test/utils";

const navigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof RouterModule>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

vi.mock("@/services/auth", () => ({
  deleteAccount: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  fetchCurrentUser: vi.fn(),
}));

import * as authService from "@/services/auth";

const authMock = vi.mocked(authService);

async function openTheForm() {
  await userEvent.click(screen.getByRole("button", { name: /apagar minha conta/i }));
}

describe("DangerZone", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("names what is erased instead of calling it 'your data'", () => {
    renderWithProviders(<DangerZone />);

    expect(screen.getByText(/sessão do linkedin guardada/i)).toBeInTheDocument();
    expect(screen.getByText(/trilha de auditoria/i)).toBeInTheDocument();
    expect(screen.getByText(/não há período de carência/i)).toBeInTheDocument();
  });

  it("asks a second time before showing the password field", async () => {
    renderWithProviders(<DangerZone />);

    expect(screen.queryByLabelText("Senha")).not.toBeInTheDocument();

    await openTheForm();

    expect(await screen.findByLabelText("Senha")).toBeInTheDocument();
    expect(authMock.deleteAccount).not.toHaveBeenCalled();
  });

  it("will not submit an empty password", async () => {
    renderWithProviders(<DangerZone />);
    await openTheForm();

    const confirm = screen.getByRole("button", { name: /apagar definitivamente/i });

    expect(confirm).toBeDisabled();
    await userEvent.click(confirm);
    expect(authMock.deleteAccount).not.toHaveBeenCalled();
  });

  it("sends the password, then drops the session and leaves the app", async () => {
    authMock.deleteAccount.mockResolvedValue(undefined);
    renderWithProviders(<DangerZone />);
    await openTheForm();

    await userEvent.type(screen.getByLabelText("Senha"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: /apagar definitivamente/i }));

    await waitFor(() =>
      expect(authMock.deleteAccount).toHaveBeenCalledWith("correct-horse-battery"),
    );
    // `replace`, so the back button cannot return to an app with no account.
    // Ending the session is `deleteAccount`'s own job, asserted where it lives.
    expect(navigate).toHaveBeenCalledWith("/login", { replace: true });
  });

  it("keeps the session when the password is refused", async () => {
    authMock.deleteAccount.mockRejectedValue(new Error("Incorrect password."));
    renderWithProviders(<DangerZone />);
    await openTheForm();

    await userEvent.type(screen.getByLabelText("Senha"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /apagar definitivamente/i }));

    expect(await screen.findByText("Incorrect password.")).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("cancelling forgets what was typed", async () => {
    renderWithProviders(<DangerZone />);
    await openTheForm();
    await userEvent.type(screen.getByLabelText("Senha"), "half-typed");

    await userEvent.click(screen.getByRole("button", { name: /cancelar/i }));
    await openTheForm();

    expect((screen.getByLabelText("Senha") as HTMLInputElement).value).toBe("");
  });
});
