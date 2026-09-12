/**
 * The admin dashboard's four states: loading, loaded, empty and failed.
 *
 * The service is mocked rather than the cache seeded, because what matters is
 * what the page *renders* from a payload — including the two things a metrics
 * screen most easily gets wrong: showing 0 where it means "nothing recorded",
 * and inventing a comparison it does not have.
 */

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminPeriodProvider } from "@/components/admin/period";
import { AdminDashboard } from "@/pages/admin/AdminDashboard";
import { ApiError } from "@/services/client";
import { renderWithProviders } from "@/test/utils";
import type { AdminOverview, Metric } from "@/types/api";

vi.mock("@/services/admin", () => ({
  fetchOverview: vi.fn(),
  listUsers: vi.fn(),
  fetchJobInsights: vi.fn(),
  listErrors: vi.fn(),
  listActivity: vi.fn(),
  fetchSystemHealth: vi.fn(),
}));

import * as adminService from "@/services/admin";

const adminMock = vi.mocked(adminService);

function metric(overrides: Partial<Metric> & { key: string }): Metric {
  return {
    value: 0,
    unit: "count",
    previous: null,
    delta_pct: null,
    trend: "none",
    has_data: true,
    ...overrides,
  };
}

/** A platform with nothing on it — the state a fresh install is actually in. */
function buildOverview(overrides: Partial<AdminOverview> = {}): AdminOverview {
  return {
    period: {
      period: "7d",
      start: "2026-03-09T00:00:00Z",
      end: "2026-03-15T14:30:00Z",
      previous_start: "2026-03-02T09:30:00Z",
      previous_end: "2026-03-09T00:00:00Z",
      days: 7,
    },
    generated_at: "2026-03-15T14:30:00Z",
    headline: [
      metric({ key: "users", value: 0 }),
      metric({ key: "jobs_found", value: 0 }),
      metric({ key: "applications", value: 0 }),
      metric({ key: "success_rate", unit: "percent", has_data: false }),
    ],
    operational: [
      metric({ key: "applications_submitted" }),
      metric({ key: "awaiting_review" }),
      metric({ key: "applications_failed" }),
      metric({ key: "interviews" }),
      metric({ key: "active_runs" }),
      metric({ key: "active_users" }),
    ],
    product: [metric({ key: "submit_rate", unit: "percent", has_data: false })],
    funnel: [
      { key: "jobs_found", count: 0, conversion_from_previous: null, conversion_from_start: null },
      {
        key: "jobs_selected",
        count: 0,
        conversion_from_previous: null,
        conversion_from_start: null,
      },
    ],
    growth: [
      { date: "2026-03-14", users: 0, jobs: 0, applications: 0 },
      { date: "2026-03-15", users: 0, jobs: 0, applications: 0 },
    ],
    automation: {
      status: "attention",
      active_runs: 0,
      runs_in_period: 0,
      runs_today: 0,
      completed: 0,
      failed: 0,
      blocked: 0,
      stopped: 0,
      last_run_at: null,
      last_run_status: null,
      next_run_at: null,
      scheduling: "on_demand",
      avg_duration_seconds: null,
      reasons: ["Nenhuma execução no período selecionado."],
    },
    ai: {
      status: "healthy",
      provider: "anthropic",
      model: "claude-opus-5",
      configured: true,
      calls: 0,
      succeeded: 0,
      failed: 0,
      refusals: 0,
      avg_latency_ms: null,
      tokens_input: 0,
      tokens_output: 0,
      cost_usd: null,
      reasons: ["Chamadas respondendo dentro do esperado."],
    },
    health: {
      status: "healthy",
      version: "0.1.0",
      environment: "test",
      services: [
        { service: "api", status: "online", detail: "Versão 0.1.0 · ambiente test." },
        { service: "database", status: "online", detail: "Consultas respondendo." },
      ],
    },
    alerts: [],
    usage: [],
    errors: [],
    activity: [],
    ...overrides,
  };
}

function renderDashboard() {
  return renderWithProviders(
    <AdminPeriodProvider>
      <AdminDashboard />
    </AdminPeriodProvider>,
  );
}

/**
 * The headline row, as a scope.
 *
 * "Usuários", "Vagas" and "Candidaturas" are also the growth chart's series
 * buttons, so an unscoped `getByText` matches two elements and says so. Each
 * metric section is a labelled `<section>` — that is a region — precisely so a
 * reader (and a test) can address one of them.
 */
function headline(): HTMLElement {
  return screen.getByRole("region", { name: "Indicadores principais" });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AdminDashboard", () => {
  it("shows the title and the period the numbers cover", async () => {
    adminMock.fetchOverview.mockResolvedValue(buildOverview());

    renderDashboard();

    expect(screen.getByRole("heading", { name: "Admin Dashboard" })).toBeInTheDocument();
    expect(screen.getByText("Visão geral da plataforma")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/7 dias/)).toBeInTheDocument());
  });

  it("marks the page busy while the metrics are in flight", async () => {
    // A deferred rather than a promise that never settles: leaving one pending
    // keeps the worker alive long past the assertion.
    let release: (value: AdminOverview) => void = () => {};
    adminMock.fetchOverview.mockReturnValue(
      new Promise<AdminOverview>((resolve) => {
        release = resolve;
      }),
    );

    renderDashboard();

    await waitFor(() =>
      expect(document.querySelectorAll('[aria-busy="true"]').length).toBeGreaterThan(0),
    );
    expect(screen.queryByText("Nenhum alerta")).not.toBeInTheDocument();

    release(buildOverview());
    await waitFor(() => expect(screen.getByText("Nenhum alerta")).toBeInTheDocument());
  });

  it("renders the headline tiles with their labels", async () => {
    adminMock.fetchOverview.mockResolvedValue(buildOverview());

    renderDashboard();

    await waitFor(() => expect(within(headline()).getByText("Usuários")).toBeInTheDocument());
    expect(within(headline()).getByText("Vagas encontradas")).toBeInTheDocument();
    expect(within(headline()).getByText("Candidaturas")).toBeInTheDocument();
    expect(within(headline()).getByText("Taxa de sucesso")).toBeInTheDocument();
  });

  it("says 'sem dados' instead of reporting a rate nobody has earned", async () => {
    adminMock.fetchOverview.mockResolvedValue(buildOverview());

    renderDashboard();

    // A 0% success rate on an install with no attempts would be a lie a viewer
    // could act on.
    await waitFor(() => expect(screen.getAllByText("sem dados").length).toBeGreaterThan(0));
  });

  it("shows the comparison when there is one, and says so when there is not", async () => {
    adminMock.fetchOverview.mockResolvedValue(
      buildOverview({
        headline: [
          metric({ key: "jobs_found", value: 4, previous: 2, delta_pct: 1, trend: "up" }),
          metric({ key: "users", value: 3 }),
        ],
      }),
    );

    renderDashboard();

    const row = () => within(headline());
    await waitFor(() => expect(row().getByText("+100,0%")).toBeInTheDocument());
    expect(row().getByText("vs. período anterior")).toBeInTheDocument();
    // The users tile has no previous value, so it says so instead of showing a
    // comparison it cannot make.
    expect(row().getByText("Sem base de comparação.")).toBeInTheDocument();
  });

  it("reports a healthy platform as having no alerts rather than hiding the card", async () => {
    adminMock.fetchOverview.mockResolvedValue(buildOverview());

    renderDashboard();

    await waitFor(() => expect(screen.getByText("Nenhum alerta")).toBeInTheDocument());
  });

  it("lists the alerts it is given, with their severity", async () => {
    adminMock.fetchOverview.mockResolvedValue(
      buildOverview({
        alerts: [
          {
            key: "application_failures",
            severity: "critical",
            title: "Candidaturas falhando acima do normal",
            detail: "3 de 6 tentativas terminaram em erro (50%) no período.",
            metric: "applications_failed",
          },
        ],
      }),
    );

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText("Candidaturas falhando acima do normal")).toBeInTheDocument(),
    );
    expect(screen.getByText("Crítico")).toBeInTheDocument();
  });

  it("explains an empty chart instead of drawing an empty chart", async () => {
    adminMock.fetchOverview.mockResolvedValue(buildOverview());

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText(/Nenhum registro de candidaturas neste período/)).toBeInTheDocument(),
    );
  });

  it("explains an empty funnel and an empty error list", async () => {
    adminMock.fetchOverview.mockResolvedValue(buildOverview());

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText("Nenhuma vaga encontrada neste período")).toBeInTheDocument(),
    );
    expect(screen.getByText("Nenhum erro neste período")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma atividade neste período")).toBeInTheDocument();
  });

  it("never claims a next automation run, because nothing schedules one", async () => {
    adminMock.fetchOverview.mockResolvedValue(buildOverview());

    renderDashboard();

    await waitFor(() => expect(screen.getByText("Próxima execução")).toBeInTheDocument());
    expect(
      screen.getByText("Sem agendador: cada execução é iniciada por um usuário"),
    ).toBeInTheDocument();
  });

  it("says the AI provider does not price its calls rather than showing US$ 0,00", async () => {
    adminMock.fetchOverview.mockResolvedValue(buildOverview());

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText("Este provider não informa custo")).toBeInTheDocument(),
    );
  });

  it("shows the errors it is given without any technical detail beyond one line", async () => {
    adminMock.fetchOverview.mockResolvedValue(
      buildOverview({
        errors: [
          {
            id: "automation:12",
            occurred_at: "2026-03-15T13:42:00Z",
            source: "automation",
            kind: "prepare",
            summary: "Falha ao processar candidatura.",
            detail: "Execução #12 · failed",
            count: 1,
          },
        ],
      }),
    );

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText("Falha ao processar candidatura.")).toBeInTheDocument(),
    );
    expect(screen.getByText("Automação")).toBeInTheDocument();
  });

  it("offers a retry when the API fails, and does not render half a dashboard", async () => {
    adminMock.fetchOverview.mockRejectedValue(new ApiError(500, "Internal server error."));

    renderDashboard();

    await waitFor(() =>
      expect(
        screen.getByText("Não foi possível carregar os indicadores"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("Internal server error.")).toBeInTheDocument();
    expect(screen.queryByText("Indicadores principais")).not.toBeInTheDocument();

    adminMock.fetchOverview.mockResolvedValue(buildOverview());
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));

    await waitFor(() => expect(within(headline()).getByText("Usuários")).toBeInTheDocument());
  });

  it("requests the period the filter is on", async () => {
    adminMock.fetchOverview.mockResolvedValue(buildOverview());

    renderDashboard();

    await waitFor(() => expect(adminMock.fetchOverview).toHaveBeenCalled());
    expect(adminMock.fetchOverview).toHaveBeenCalledWith(
      { period: "7d" },
      expect.anything(),
    );
  });
});
