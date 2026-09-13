/**
 * The one write the admin panel has: suspending an account's login.
 *
 * Three things are worth a test here, and they are all about restraint rather
 * than about the table: the action asks before it cuts somebody's session, it
 * refuses to point at the administrator's own account, and it never offers to
 * grant the role — `is_admin` is not in the payload the API accepts, and it is
 * not in this screen either.
 */

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminPeriodProvider } from "@/components/admin/period";
import { AdminUsers } from "@/pages/admin/AdminUsers";
import { renderWithProviders } from "@/test/utils";
import type { AdminUserRow, User } from "@/types/api";

vi.mock("@/services/admin", () => ({
  fetchOverview: vi.fn(),
  listUsers: vi.fn(),
  fetchJobInsights: vi.fn(),
  listErrors: vi.fn(),
  listActivity: vi.fn(),
  fetchSystemHealth: vi.fn(),
  setAccountActive: vi.fn(),
}));
vi.mock("@/hooks/useAuth", () => ({ useAuth: vi.fn() }));

import { useAuth } from "@/hooks/useAuth";
import * as adminService from "@/services/admin";

const adminMock = vi.mocked(adminService);
const useAuthMock = vi.mocked(useAuth);

function row(overrides: Partial<AdminUserRow> & { id: number }): AdminUserRow {
  return {
    email: `user${overrides.id}@example.com`,
    full_name: `Conta ${overrides.id}`,
    is_active: true,
    is_admin: false,
    created_at: "2026-02-01T10:00:00Z",
    last_login_at: null,
    jobs: 0,
    applications: 0,
    submitted: 0,
    ...overrides,
  };
}

const ME: User = {
  id: 1,
  email: "admin@example.com",
  full_name: "Admin",
  is_active: true,
  is_admin: true,
  created_at: null,
  last_login_at: null,
};

function renderUsers() {
  return renderWithProviders(
    <AdminPeriodProvider>
      <AdminUsers />
    </AdminPeriodProvider>,
  );
}

/**
 * The row for one account, as a scope.
 *
 * `DataList` renders the same rows twice — a table from `md` up, cards below it —
 * and jsdom has no viewport to hide either, so every query has to say which one
 * it means. The table is the one carrying the semantics.
 */
async function rowFor(email: string): Promise<HTMLElement> {
  const table = await screen.findByRole("table", { name: "Contas da plataforma" });
  const tableRow = within(table).getByText(email).closest("tr");
  if (!tableRow) throw new Error(`No row rendered for ${email}.`);
  return tableRow;
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthMock.mockReturnValue({
    user: ME,
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  });
  adminMock.listUsers.mockResolvedValue({
    items: [row({ id: 1, email: ME.email, is_admin: true }), row({ id: 2 })],
    total: 2,
    limit: 25,
    offset: 0,
  });
});

describe("AdminUsers", () => {
  it("asks before it cuts an open session", async () => {
    const user = userEvent.setup();
    adminMock.setAccountActive.mockResolvedValue(row({ id: 2, is_active: false }));

    renderUsers();

    const target = await rowFor("user2@example.com");
    await user.click(within(target).getByRole("button", { name: "Suspender" }));

    // The question names the account, and nothing is sent until it is answered.
    expect(await screen.findByText("Suspender este acesso?")).toBeInTheDocument();
    expect(adminMock.setAccountActive).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Suspender o acesso" }));
    await waitFor(() => expect(adminMock.setAccountActive).toHaveBeenCalledWith(2, false));
  });

  it("lets the administrator back out of the question", async () => {
    const user = userEvent.setup();

    renderUsers();

    const target = await rowFor("user2@example.com");
    await user.click(within(target).getByRole("button", { name: "Suspender" }));
    await user.click(await screen.findByRole("button", { name: "Manter o acesso" }));

    await waitFor(() =>
      expect(screen.queryByText("Suspender este acesso?")).not.toBeInTheDocument(),
    );
    expect(adminMock.setAccountActive).not.toHaveBeenCalled();
  });

  it("will not offer to lock the administrator out of their own account", async () => {
    renderUsers();

    const mine = await rowFor(ME.email);
    expect(within(mine).getByRole("button", { name: "Suspender" })).toBeDisabled();
  });

  it("reactivates without a confirmation, because giving access back is not destructive", async () => {
    const user = userEvent.setup();
    adminMock.listUsers.mockResolvedValue({
      items: [row({ id: 3, is_active: false })],
      total: 1,
      limit: 25,
      offset: 0,
    });
    adminMock.setAccountActive.mockResolvedValue(row({ id: 3, is_active: true }));

    renderUsers();

    const target = await rowFor("user3@example.com");
    await user.click(within(target).getByRole("button", { name: "Reativar" }));

    await waitFor(() => expect(adminMock.setAccountActive).toHaveBeenCalledWith(3, true));
    expect(screen.queryByText("Suspender este acesso?")).not.toBeInTheDocument();
  });

  it("offers no way to grant the admin role", async () => {
    renderUsers();

    await rowFor("user2@example.com");
    // The role is granted on the host by scripts/create_admin.py. The API's
    // payload has a single field for exactly this reason; the screen matches it.
    expect(screen.queryByRole("button", { name: /admin/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});
