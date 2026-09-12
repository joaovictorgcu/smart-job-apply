/**
 * Five destinations, and nothing unreachable behind them.
 *
 * Three entries left the sidebar — the funnel, saved searches and the activity
 * log — because each was the app's vocabulary rather than the user's. What has
 * to stay true is that none of them became a dead route: this file pins the
 * sidebar's shape, and the components that now carry those links pin the rest.
 */

import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Sidebar } from "@/components/Sidebar";
import { ViewSwitch } from "@/components/ViewSwitch";
import { renderWithProviders } from "@/test/utils";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: 1, email: "joao@example.com", full_name: "João Victor", is_admin: false },
    isLoading: false,
  }),
}));

describe("Sidebar", () => {
  it("offers five destinations, each a word the user already has", () => {
    renderWithProviders(<Sidebar alwaysShowLabels />);

    const nav = screen.getByRole("navigation", { name: /navegação principal/i });
    const labels = Array.from(nav.querySelectorAll("a")).map((link) => link.textContent?.trim());

    expect(labels).toEqual([
      "Painel",
      "Vagas",
      "Candidaturas",
      "Perfil",
      "Configurações",
    ]);
  });

  it("no longer asks the user to know what a funnel or a saved search is", () => {
    renderWithProviders(<Sidebar alwaysShowLabels />);

    const nav = screen.getByRole("navigation", { name: /navegação principal/i });
    expect(nav.textContent).not.toMatch(/funil|buscas|atividade/i);
  });
});

describe("ViewSwitch", () => {
  it("keeps both readings of one list on their own URLs", () => {
    renderWithProviders(
      <ViewSwitch
        label="Candidaturas"
        options={[
          { to: "/applications", label: "Lista", end: true },
          { to: "/pipeline", label: "Funil" },
        ]}
      />,
    );

    // Links rather than state: a bookmarked funnel still opens on the funnel.
    expect(screen.getByRole("link", { name: "Lista" })).toHaveAttribute("href", "/applications");
    expect(screen.getByRole("link", { name: "Funil" })).toHaveAttribute("href", "/pipeline");
  });
});
