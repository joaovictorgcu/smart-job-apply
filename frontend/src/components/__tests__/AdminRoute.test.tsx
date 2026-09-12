/**
 * The admin route guard.
 *
 * It is convenience, not protection — the API refuses a non-admin session on its
 * own — so what these tests assert is that the *right screen* appears: an
 * explanation for a normal account, the page for an administrator, and a wait
 * while the session is still being confirmed.
 */

import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AdminRoute } from "@/components/AdminRoute";
import { renderWithProviders } from "@/test/utils";
import type { User } from "@/types/api";

vi.mock("@/hooks/useAuth", () => ({ useAuth: vi.fn() }));

import { useAuth } from "@/hooks/useAuth";

const useAuthMock = vi.mocked(useAuth);

function buildUser(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    email: "someone@example.com",
    full_name: "Someone",
    is_active: true,
    is_admin: false,
    created_at: null,
    last_login_at: null,
    ...overrides,
  };
}

function mockSession(user: User | null, isLoading = false): void {
  useAuthMock.mockReturnValue({
    user,
    isLoading,
    isAuthenticated: Boolean(user),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  });
}

/**
 * The guard, mounted at a route with a real destination for its redirect.
 *
 * Rendering `<Navigate>` as a bare child of a router that matches nothing sends
 * the guard into a loop: the location changes, the component re-renders, it
 * redirects again, and the test runs out of memory instead of failing. Giving
 * /login somewhere to land is both the fix and the more faithful setup.
 */
function renderGuard() {
  return renderWithProviders(
    <Routes>
      <Route
        path="/"
        element={
          <AdminRoute>
            <p>Admin Dashboard</p>
          </AdminRoute>
        }
      />
      <Route path="/login" element={<p>Tela de login</p>} />
    </Routes>,
  );
}

describe("AdminRoute", () => {
  it("renders the area for an administrator", () => {
    mockSession(buildUser({ is_admin: true }));

    renderGuard();

    expect(screen.getByText("Admin Dashboard")).toBeInTheDocument();
  });

  it("explains itself to a normal account instead of showing the area", () => {
    mockSession(buildUser({ is_admin: false }));

    renderGuard();

    expect(screen.getByText("Área restrita")).toBeInTheDocument();
    expect(screen.queryByText("Admin Dashboard")).not.toBeInTheDocument();
  });

  it("waits instead of bouncing while the session is still being confirmed", () => {
    // A reload with a valid token starts here; redirecting would throw the
    // administrator out of a page they are allowed to see.
    mockSession(null, true);

    renderGuard();

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("Admin Dashboard")).not.toBeInTheDocument();
  });

  it("sends a signed-out visitor to the login screen", () => {
    mockSession(null, false);

    renderGuard();

    expect(screen.getByText("Tela de login")).toBeInTheDocument();
    expect(screen.queryByText("Admin Dashboard")).not.toBeInTheDocument();
    // Not the restricted-area message: there is no session to refuse yet.
    expect(screen.queryByText("Área restrita")).not.toBeInTheDocument();
  });
});
