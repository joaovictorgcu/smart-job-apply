/**
 * Minimal, valid fixtures for the API shapes the tests exercise.
 *
 * Every factory returns a fully populated object so a test only has to state the
 * one field it cares about — an omitted field can never be the reason a test
 * passes or fails.
 */

import type {
  ApplicationDetail,
  ApplicationResume,
  Job,
  PreviewResponse,
  ResumeDocument,
  ResumeExperience,
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
    resume_focus: [".NET 8", "APIs REST"],
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-01T10:30:00Z",
    job: buildJob(),
    events: [],
    ...overrides,
  };
}

export function buildExperience(
  overrides: Partial<ResumeExperience> = {},
): ResumeExperience {
  return {
    key: "globalthings-tech-lead",
    company: "Globalthings",
    role: "Tech Lead",
    start: "2023-02",
    end: null,
    location: "Recife, PE",
    summary: "Lidera a plataforma de gestão de acessos.",
    highlights: [
      {
        text: "Reescreveu o serviço de autorização em .NET 8.",
        technologies: [".NET 8", "APIs REST"],
        impact: "p95 de 420 ms para 120 ms",
      },
      {
        text: "Montou o painel administrativo em Blazor.",
        technologies: ["Blazor"],
        impact: null,
      },
    ],
    technologies: [".NET 8", "SQL Server", "Blazor"],
    projects: [],
    focus: [],
    ...overrides,
  };
}

export function buildResumeDocument(
  overrides: Partial<ResumeDocument> = {},
): ResumeDocument {
  return {
    headline: "Tech Lead — .NET, React e Python",
    summary: "Nove anos construindo produtos web.",
    skills: ["Arquitetura de software", "Liderança técnica"],
    technologies: [".NET 8", "React", "Python"],
    experiences: [
      buildExperience(),
      buildExperience({
        key: "nexo-fullstack",
        company: "Nexo Digital",
        role: "Engenheiro Full Stack",
        start: "2020-06",
        end: "2023-01",
        summary: "Construiu o checkout de ponta a ponta.",
        highlights: [
          {
            text: "Refez o checkout em React e TypeScript.",
            technologies: ["React", "TypeScript"],
            impact: "conversão de 61% para 74%",
          },
        ],
        technologies: ["React", "TypeScript", "Node.js"],
      }),
    ],
    projects: [],
    education: [],
    certifications: [],
    languages: ["pt-BR"],
    ...overrides,
  };
}

/**
 * One application's resume version, derived from the master.
 *
 * The default is a `.NET`-focused version whose leading experience is the .NET
 * job with a rewritten summary — so a test asserting "this is visibly the
 * version for this posting" has something to assert against.
 */
export function buildApplicationResume(
  overrides: Partial<ApplicationResume> = {},
): ApplicationResume {
  const base = buildResumeDocument();
  const document = buildResumeDocument({
    summary: "Nove anos construindo produtos web — ênfase em .NET 8 e APIs REST.",
    technologies: [".NET 8", "React", "Python"],
    experiences: [
      buildExperience({
        summary:
          "Lidera a plataforma de gestão de acessos — ênfase em .NET 8 e APIs REST; " +
          "p95 de 420 ms para 120 ms.",
        focus: [".NET 8", "APIs REST"],
      }),
      buildExperience({
        key: "nexo-fullstack",
        company: "Nexo Digital",
        role: "Engenheiro Full Stack",
        start: "2020-06",
        end: "2023-01",
        summary: "Construiu o checkout de ponta a ponta.",
        highlights: [
          {
            text: "Refez o checkout em React e TypeScript.",
            technologies: ["React", "TypeScript"],
            impact: "conversão de 61% para 74%",
          },
        ],
        technologies: ["React", "TypeScript", "Node.js"],
      }),
    ],
  });

  return {
    application_id: 5,
    job_id: 10,
    job_title: "Desenvolvedor Backend .NET Sênior",
    job_company: "Globalthings",
    document,
    base_document: base,
    focus: [".NET 8", "APIs REST", "SQL Server"],
    changes: [
      {
        section: "Experiência — Globalthings",
        action: "rephrased",
        detail: "Descrição reescrita para destacar .NET 8 e APIs REST.",
      },
    ],
    invention_flags: [],
    source: "rules",
    is_stale: false,
    markdown: "# Tech Lead\n\nNove anos construindo produtos web.\n",
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-01T10:05:00Z",
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
