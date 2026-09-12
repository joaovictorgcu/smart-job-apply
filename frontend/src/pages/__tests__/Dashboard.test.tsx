/**
 * "O que eu faço agora?" — and the dashboard answers only that.
 *
 * This screen used to be a scoreboard. What is pinned here is the shape that
 * replaced it: the work that cannot proceed without a human leads, each count
 * carries the action that clears it, and an account with no resume gets one
 * instruction instead of a page of zeroes.
 */

import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Dashboard } from "@/pages/Dashboard";
import { buildApplicationDetail, buildJob } from "@/test/factories";
import { renderWithProviders } from "@/test/utils";
import type { Application, DashboardStats, MasterResume, OutcomeStats } from "@/types/api";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: 1, email: "joao@example.com", full_name: "João Victor Uchôa" },
    isLoading: false,
  }),
}));

vi.mock("@/services/resumes", () => ({
  fetchMasterResume: vi.fn(),
  listExperiences: vi.fn(),
  listResumeVersions: vi.fn(),
  fetchApplicationResume: vi.fn(),
  adaptApplicationResume: vi.fn(),
  updateApplicationResume: vi.fn(),
  createExperience: vi.fn(),
  updateExperience: vi.fn(),
  deleteExperience: vi.fn(),
}));
vi.mock("@/services/stats", () => ({
  fetchStats: vi.fn(),
  fetchOutcomeStats: vi.fn(),
  fetchSegmentStats: vi.fn(),
}));
vi.mock("@/services/applications", () => ({ listApplications: vi.fn() }));
vi.mock("@/services/jobs", () => ({ listJobs: vi.fn() }));
vi.mock("@/services/automation", () => ({
  fetchSessionStatus: vi.fn(),
  startSession: vi.fn(),
  stopSession: vi.fn(),
  stopAutomation: vi.fn(),
}));

import * as applicationsService from "@/services/applications";
import * as automationService from "@/services/automation";
import * as jobsService from "@/services/jobs";
import * as resumesService from "@/services/resumes";
import * as statsService from "@/services/stats";

const resumes = vi.mocked(resumesService);
const stats = vi.mocked(statsService);
const applications = vi.mocked(applicationsService);
const jobs = vi.mocked(jobsService);
const automation = vi.mocked(automationService);

function master(overrides: Partial<MasterResume> = {}): MasterResume {
  return {
    headline: "Desenvolvedor Full Stack",
    location: "Recife, PE",
    summary: null,
    years_of_experience: 4,
    skills: [".NET"],
    resume_text: "texto",
    resume_filename: "cv.pdf",
    experiences: [],
    fingerprint: "abc",
    updated_at: null,
    ...overrides,
  };
}

function dashboardStats(overrides: Partial<DashboardStats> = {}): DashboardStats {
  return {
    jobs_total: 12,
    jobs_by_status: {},
    applications_total: 3,
    applications_today: 0,
    awaiting_review: 2,
    daily_cap: 15,
    remaining_today: 15,
    average_score: 80,
    score_distribution: [],
    applications_last_7_days: [],
    ai_calls_total: 0,
    ai_tokens_input: 0,
    ai_tokens_output: 0,
    ...overrides,
  } as DashboardStats;
}

function outcomeStats(overrides: Partial<OutcomeStats> = {}): OutcomeStats {
  return {
    total_submitted: 7,
    interviews: 2,
    offers: 0,
    rejected: 1,
    ghosted: 1,
    interview_rate: 0.28,
    by_outcome: [],
    interview_rate_by_band: [],
    ...overrides,
  } as OutcomeStats;
}

/** The list shape: an `ApplicationDetail` minus what only the detail carries. */
function waiting(overrides: Partial<Application> = {}): Application {
  const detail = buildApplicationDetail(overrides) as unknown as Record<string, unknown>;
  delete detail.job;
  delete detail.events;
  return detail as unknown as Application;
}

beforeEach(() => {
  vi.clearAllMocks();
  resumes.fetchMasterResume.mockResolvedValue(master());
  stats.fetchStats.mockResolvedValue(dashboardStats());
  stats.fetchOutcomeStats.mockResolvedValue(outcomeStats());
  applications.listApplications.mockResolvedValue({
    items: [waiting()],
    total: 1,
    limit: 4,
    offset: 0,
  });
  jobs.listJobs.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  automation.fetchSessionStatus.mockResolvedValue({
    browser_open: false,
    logged_in: false,
    blocked: false,
    blocked_reason: null,
    active_run_id: null,
    applications_today: 0,
    daily_cap: 15,
    dry_run: true,
    ai_configured: true,
  });
});

describe("Dashboard", () => {
  it("greets by first name and asks the only question it answers", async () => {
    renderWithProviders(<Dashboard />);

    expect(await screen.findByText(/olá, joão\./i)).toBeInTheDocument();
    expect(screen.getByText(/o que você quer fazer hoje\?/i)).toBeInTheDocument();
  });

  it("leads with the work that cannot proceed without a human", async () => {
    renderWithProviders(<Dashboard />);

    expect(await screen.findByText(/candidatura espera você/i)).toBeInTheDocument();
    expect(
      screen.getByText("Desenvolvedor Backend .NET Sênior"),
    ).toBeInTheDocument();
  });

  it("names the posting without fetching a page of jobs to join on", async () => {
    renderWithProviders(<Dashboard />);

    await screen.findByText("Desenvolvedor Backend .NET Sênior");
    // The only job query is the "ready to prepare" one, filtered on the server.
    expect(jobs.listJobs).toHaveBeenCalledTimes(1);
    expect(jobs.listJobs.mock.calls[0][0]).toMatchObject({ status: "analyzed" });
  });

  it("offers jobs worth preparing, and only those with no application yet", async () => {
    jobs.listJobs.mockResolvedValue({
      items: [
        buildJob({ id: 1, application_id: null }),
        buildJob({ id: 2, application_id: 99 }),
      ],
      total: 2,
      limit: 20,
      offset: 0,
    });

    const { container } = renderWithProviders(<Dashboard />);

    // The count and its label are separate nodes, so match the flattened text.
    await screen.findByText(/vaga recomendada/i);
    expect(container.textContent).toMatch(/1\s*vaga recomendada/i);
  });

  it("keeps the numbers as a consequence, not as the content", async () => {
    const { container } = renderWithProviders(<Dashboard />);

    await screen.findByText(/olá, joão\./i);
    expect(container.textContent).toMatch(/7\s*enviadas/);
    expect(container.textContent).toMatch(/2\s*entrevistas/);
  });

  it("shows one instruction instead of a page of zeroes with no resume", async () => {
    resumes.fetchMasterResume.mockResolvedValue(
      master({ headline: null, resume_text: null, experiences: [] }),
    );

    renderWithProviders(<Dashboard />);

    expect(await screen.findByText(/comece pelo seu currículo/i)).toBeInTheDocument();
    expect(screen.queryByText(/o que você quer fazer hoje\?/i)).not.toBeInTheDocument();
  });
});
