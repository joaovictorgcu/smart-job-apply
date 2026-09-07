/**
 * Minimal, valid fixtures for the API shapes the tests exercise.
 *
 * Every factory returns a fully populated object so a test only has to state the
 * one field it cares about — an omitted field can never be the reason a test
 * passes or fails.
 */

import type {
  AdaptedExperience,
  ApplicationDetail,
  ApplicationResume,
  Experience,
  Job,
  PreviewResponse,
  ResumeVersionSummary,
  ScreeningAnswer,
  UserSettings,
} from "@/types/api";
import type { AppEvent } from "@/types/events";

export function buildJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 10,
    external_id: "ext-10",
    source: "linkedin",
    title: "Engenheiro de Software Sênior",
    company: "Globalthings",
    location: "Recife, PE",
    url: "https://example.invalid/jobs/10",
    workplace_type: "remote",
    easy_apply: true,
    status: "analyzed",
    score: 87,
    score_reasons: [],
    missing_requirements: [],
    score_breakdown: [],
    score_gates: [],
    // Derived server-side from the score and its breakdown; an empty breakdown
    // has no arithmetic to report, which is exactly what an old job looks like.
    verdict: "strong",
    weighted_score: null,
    score_divergence: null,
    skip_reason: null,
    detected_language: "pt",
    posted_at: "2026-08-01T09:00:00Z",
    created_at: "2026-08-01T09:05:00Z",
    search_id: 1,
    application_id: 5,
    ...overrides,
  };
}

export function buildScreeningAnswer(
  overrides: Partial<ScreeningAnswer> = {},
): ScreeningAnswer {
  return {
    question: "Quantos anos de experiência você tem com Python?",
    answer: "8",
    question_type: "number",
    confidence: "high",
    needs_review: false,
    reasoning: null,
    source: "answer_bank",
    field_id: "years-python",
    ...overrides,
  };
}

export function buildApplicationDetail(
  overrides: Partial<ApplicationDetail> = {},
): ApplicationDetail {
  return {
    id: 5,
    job_id: 10,
    status: "awaiting_review",
    channel: "easy_apply",
    cover_letter: "Prezada equipe, tenho interesse nesta vaga.",
    screening_answers: [buildScreeningAnswer()],
    resume_filename: "curriculo.pdf",
    total_steps: 3,
    current_step: 3,
    needs_human_input: false,
    was_dry_run: false,
    approved_at: null,
    submitted_at: null,
    error_message: null,
    outcome: null,
    outcome_updated_at: null,
    outcome_note: null,
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-01T10:30:00Z",
    job: buildJob(),
    events: [],
    ...overrides,
  };
}

export function buildSettings(overrides: Partial<UserSettings> = {}): UserSettings {
  return {
    daily_cap: 20,
    min_score: 70,
    action_delay_min: 2,
    action_delay_max: 5,
    apply_delay_min: 30,
    apply_delay_max: 90,
    working_hour_start: 9,
    working_hour_end: 18,
    require_manual_approval: true,
    dry_run: true,
    ai_model: "claude-sonnet-4-5",
    cover_letter_tone: "professional",
    content_language: "pt",
    generate_cover_letter: true,
    ...overrides,
  };
}

export function buildPreview(overrides: Partial<PreviewResponse> = {}): PreviewResponse {
  return {
    jobs_to_process: 3,
    already_applied: 1,
    below_threshold: 2,
    remaining_today: 12,
    daily_cap: 20,
    dry_run: true,
    requires_confirmation: true,
    jobs: [buildJob()],
    warnings: [],
    ...overrides,
  };
}

export function buildExperience(overrides: Partial<Experience> = {}): Experience {
  return {
    id: 1,
    company: "Globalthings",
    role: "Engenheiro de Software Sênior",
    employment_type: "CLT",
    location: "Recife, PE",
    started_on: "2022-03-01",
    ended_on: null,
    is_current: true,
    summary: "APIs corporativas e o portal de gestão de acessos.",
    responsibilities: [
      "Projetei APIs REST em C# e ASP.NET Core.",
      "Construí telas do portal em React e TypeScript.",
    ],
    technologies: ["C#", ".NET", "PostgreSQL", "React", "TypeScript"],
    results: ["Reduzi o tempo de resposta das APIs de 800 ms para 210 ms."],
    projects: [
      {
        name: "Gerenciador de Acessos",
        description: "Portal interno, API em .NET e front em React.",
        technologies: ["C#", ".NET", "React"],
      },
    ],
    position: 0,
    created_at: "2026-08-01T09:00:00Z",
    updated_at: "2026-08-01T09:00:00Z",
    ...overrides,
  };
}

export function buildAdaptedExperience(
  overrides: Partial<AdaptedExperience> = {},
): AdaptedExperience {
  return {
    experience_id: 1,
    company: "Globalthings",
    role: "Engenheiro de Software Sênior",
    location: "Recife, PE",
    employment_type: "CLT",
    started_on: "2022-03-01",
    ended_on: null,
    is_current: true,
    summary: "APIs corporativas e o portal de gestão de acessos.",
    responsibilities: [
      "Projetei APIs REST em C# e ASP.NET Core.",
      "Construí telas do portal em React e TypeScript.",
    ],
    technologies: ["C#", ".NET", "PostgreSQL", "React"],
    results: ["Reduzi o tempo de resposta das APIs de 800 ms para 210 ms."],
    projects: [
      {
        name: "Gerenciador de Acessos",
        description: "Portal interno, API em .NET e front em React.",
        technologies: ["C#", ".NET"],
        company: "Globalthings",
        role: "Engenheiro de Software Sênior",
        matched_terms: ["C#", ".NET"],
      },
    ],
    relevance: 100,
    matched_terms: ["C#", ".NET", "PostgreSQL"],
    promoted: 2,
    ...overrides,
  };
}

export function buildApplicationResume(
  overrides: Partial<ApplicationResume> = {},
): ApplicationResume {
  return {
    application_id: 5,
    job_id: 10,
    job_title: "Desenvolvedor Backend .NET Sênior",
    job_company: "Banco Meridiano",
    version: 1,
    headline: "Engenheira de software — .NET, React e Python",
    summary: "Dez anos entre backend, frontend e dados.",
    skills: ["C#", ".NET", "PostgreSQL", "React", "Java"],
    highlighted_skills: ["C#", ".NET", "PostgreSQL"],
    emphasized_technologies: ["C#", ".NET", "PostgreSQL"],
    experiences: [
      buildAdaptedExperience(),
      buildAdaptedExperience({
        experience_id: 2,
        company: "Nuvem Retail",
        role: "Desenvolvedor Full Stack",
        started_on: "2020-01-06",
        ended_on: "2022-02-28",
        is_current: false,
        responsibilities: ["Desenvolvi a vitrine e o checkout em React."],
        technologies: ["React", "TypeScript", "Node"],
        results: [],
        projects: [],
        relevance: 0,
        matched_terms: [],
        promoted: 0,
      }),
    ],
    projects: [
      {
        name: "Gerenciador de Acessos",
        description: "Portal interno, API em .NET e front em React.",
        technologies: ["C#", ".NET"],
        company: "Globalthings",
        role: "Engenheiro de Software Sênior",
        matched_terms: ["C#", ".NET"],
      },
    ],
    changes: [
      {
        kind: "experience_prioritized",
        target: "Engenheiro de Software Sênior — Globalthings",
        terms: ["C#", ".NET"],
        matched: 0,
        total: 0,
      },
      {
        kind: "experience_refocused",
        target: "Engenheiro de Software Sênior — Globalthings",
        terms: ["C#"],
        matched: 2,
        total: 3,
      },
      { kind: "skill_highlighted", target: "C#", terms: [], matched: 0, total: 0 },
      { kind: "technology_emphasized", target: ".NET", terms: [], matched: 0, total: 0 },
      {
        kind: "project_selected",
        target: "Gerenciador de Acessos",
        terms: ["C#"],
        matched: 0,
        total: 0,
      },
    ],
    fit_score: 87,
    fit_factors: [
      {
        factor: "technologies",
        score: 100,
        weight_pct: 40,
        matched: 3,
        total: 3,
        terms: ["C#", ".NET", "PostgreSQL"],
      },
      { factor: "experience", score: 100, weight_pct: 30, matched: 3, total: 3, terms: ["C#"] },
      { factor: "skills", score: 100, weight_pct: 20, matched: 3, total: 3, terms: ["C#"] },
      { factor: "seniority", score: 100, weight_pct: 10, matched: 9, total: 5, terms: [] },
    ],
    uncovered_requirements: ["Kubernetes"],
    model: null,
    was_edited: false,
    is_stale: false,
    adapted_at: "2026-08-01T10:00:00Z",
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-01T10:00:00Z",
    ...overrides,
  };
}

export function buildResumeVersion(
  overrides: Partial<ResumeVersionSummary> = {},
): ResumeVersionSummary {
  return {
    application_id: 5,
    job_id: 10,
    job_title: "Desenvolvedor Backend .NET Sênior",
    job_company: "Banco Meridiano",
    application_status: "awaiting_review",
    version: 1,
    fit_score: 87,
    has_fit: true,
    highlighted_count: 3,
    was_edited: false,
    is_stale: false,
    updated_at: "2026-08-01T10:00:00Z",
    ...overrides,
  };
}

export function buildAppEvent(overrides: Partial<AppEvent> = {}): AppEvent {
  return {
    name: "job.found",
    timestamp: "2026-08-01T10:00:00Z",
    run_id: 1,
    job_id: 10,
    application_id: null,
    message: "Vaga encontrada.",
    level: "info",
    data: {},
    ...overrides,
  };
}
