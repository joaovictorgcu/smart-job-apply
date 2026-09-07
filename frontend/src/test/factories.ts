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
  ResumeFocus,
  ResumeSections,
  ScreeningAnswer,
  TailoredExperience,
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

export function buildTailoredExperience(
  overrides: Partial<TailoredExperience> = {},
): TailoredExperience {
  return {
    id: "exp-globalthings",
    role: "Tech Lead",
    company: "Globalthings",
    period: "2023 — atual",
    location: "Recife, PE",
    description:
      "Desenvolvimento e manutenção de aplicações backend em C# e .NET 8, com ASP.NET Core e Entity Framework sobre PostgreSQL.",
    highlights: [
      "Desenvolvimento e manutenção de aplicações backend em C# e .NET 8, com ASP.NET Core e Entity Framework sobre PostgreSQL.",
    ],
    technologies: [".NET", "C#", "PostgreSQL", "React"],
    matched: [".NET", "C#", "PostgreSQL"],
    relevance: 100,
    emphasis: "lead",
    omitted: ["Condução de code reviews semanais e mentoria de três desenvolvedores."],
    ...overrides,
  };
}

export function buildResumeSections(overrides: Partial<ResumeSections> = {}): ResumeSections {
  return {
    full_name: "Alex Moreira",
    headline: "Desenvolvimento de software — .NET, Python, React e APIs",
    location: "Recife, PE",
    summary: "Dez anos construindo software de ponta a ponta.",
    years_of_experience: 10,
    prioritized_skills: [".NET", "C#", "PostgreSQL"],
    other_skills: ["React", "Python"],
    experiences: [buildTailoredExperience()],
    projects: [
      {
        id: "proj-gateway",
        name: "Gateway de APIs de parceiros",
        description: "Camada em ASP.NET Core.",
        outcome: "Integração de um novo parceiro passou de semanas para dias.",
        technologies: ["C#", "ASP.NET Core"],
        matched: ["C#"],
        relevance: 100,
      },
    ],
    education: [
      {
        id: "edu-ufpe",
        degree: "Bacharelado em Ciência da Computação",
        institution: "UFPE",
        start: "2011",
        end: "2015",
        detail: "",
      },
    ],
    certifications: ["Microsoft AZ-204"],
    language: "pt",
    ...overrides,
  };
}

export function buildResumeFocus(overrides: Partial<ResumeFocus> = {}): ResumeFocus {
  return {
    title: "Desenvolvedor Backend .NET",
    company: "Meridian Software",
    level: null,
    keywords: [".NET", "C#", "PostgreSQL"],
    unsupported: ["Elixir"],
    ...overrides,
  };
}

export function buildApplicationResume(
  overrides: Partial<ApplicationResume> = {},
): ApplicationResume {
  return {
    application_id: 5,
    job_id: 10,
    job_title: "Desenvolvedor Backend .NET",
    job_company: "Meridian Software",
    content: "# Alex Moreira\n\n## Foco desta versão\n.NET, C#, PostgreSQL",
    changes: [
      {
        section: "Competências",
        action: "reordered",
        detail: "3 competência(s) pedidas pelo anúncio passaram para o início.",
      },
    ],
    unsupported_requirements: ["Elixir"],
    invention_flags: [],
    stretch_flags: [],
    summary: "Seu próprio currículo reorganizado para Desenvolvedor Backend .NET.",
    model: null,
    was_edited: false,
    is_stale: false,
    strategy: "deterministic",
    sections: buildResumeSections(),
    focus: buildResumeFocus(),
    created_at: "2026-09-07T10:00:00Z",
    updated_at: "2026-09-07T10:00:00Z",
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
