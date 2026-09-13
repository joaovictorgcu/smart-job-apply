import type { ApplicationStatus, AutomationRunStatus, JobStatus } from "@/types/api";
import type { EventLevel } from "@/types/events";

const NUMBER_FORMAT = new Intl.NumberFormat("pt-BR");
const PERCENT_FORMAT = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  maximumFractionDigits: 0,
});

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return NUMBER_FORMAT.format(value);
}

export function formatPercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return "—";
  return PERCENT_FORMAT.format(ratio);
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return String(Math.round(score));
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (Math.abs(value) < 1000) return String(value);
  return new Intl.NumberFormat("pt-BR", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function toDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: string | Date | null | undefined): string {
  const date = toDate(value);
  if (!date) return "—";
  return date.toLocaleDateString("pt-BR", {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

export function formatDateTime(value: string | Date | null | undefined): string {
  const date = toDate(value);
  if (!date) return "—";
  return date.toLocaleString("pt-BR", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function formatTime(value: string | Date | null | undefined): string {
  const date = toDate(value);
  if (!date) return "—";
  return date.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

/** "3 minutes ago" / "in 2 hours". */
export function formatRelativeTime(value: string | Date | null | undefined): string {
  const date = toDate(value);
  if (!date) return "—";

  const formatter = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });
  const deltaSeconds = (date.getTime() - Date.now()) / 1000;
  const thresholds: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["second", 60],
    ["minute", 60],
    ["hour", 24],
    ["day", 7],
    ["week", 4.34524],
    ["month", 12],
    ["year", Number.POSITIVE_INFINITY],
  ];

  let amount = deltaSeconds;
  for (const [unit, span] of thresholds) {
    if (Math.abs(amount) < span || unit === "year") {
      return formatter.format(Math.round(amount), unit);
    }
    amount /= span;
  }
  return formatter.format(Math.round(amount), "year");
}

export function formatDuration(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined,
): string {
  const start = toDate(startedAt);
  if (!start) return "—";
  const end = toDate(finishedAt) ?? new Date();
  const totalSeconds = Math.max(0, Math.round((end.getTime() - start.getTime()) / 1000));

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

export function truncate(text: string | null | undefined, maxLength = 120): string {
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trimEnd()}…`;
}

/** Turns "awaiting_review" into "Awaiting review". */
export function humanizeSnakeCase(value: string): string {
  const spaced = value.replace(/[_.]/g, " ").trim();
  if (!spaced) return "";
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[index]}`;
}

/* -------------------------------------------------------------------------- */
/* Presentation maps shared by pages and components                           */
/* -------------------------------------------------------------------------- */

export type ToneName = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

const BADGE_CLASS: Record<ToneName, string> = {
  neutral: "badge",
  accent: "badge badge-accent",
  success: "badge badge-success",
  warning: "badge badge-warning",
  danger: "badge badge-danger",
  info: "badge badge-info",
};

export function badgeClass(tone: ToneName): string {
  return BADGE_CLASS[tone];
}

const JOB_STATUS_TONE: Record<JobStatus, ToneName> = {
  discovered: "neutral",
  analyzed: "info",
  skipped: "neutral",
  queued: "accent",
  applied: "success",
  failed: "danger",
};

const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  discovered: "Descoberta",
  analyzed: "Analisada",
  skipped: "Pulada",
  queued: "Na fila",
  applied: "Candidatada",
  failed: "Falhou",
};

export function jobStatusTone(status: JobStatus): ToneName {
  return JOB_STATUS_TONE[status] ?? "neutral";
}

export function jobStatusLabel(status: JobStatus): string {
  return JOB_STATUS_LABEL[status] ?? humanizeSnakeCase(status);
}

const APPLICATION_STATUS_TONE: Record<ApplicationStatus, ToneName> = {
  draft: "neutral",
  preparing: "info",
  awaiting_review: "warning",
  submitting: "info",
  submitted: "success",
  discarded: "neutral",
  failed: "danger",
};

const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  draft: "Rascunho",
  preparing: "Preparando",
  awaiting_review: "Aguardando revisão",
  submitting: "Enviando",
  submitted: "Enviada",
  discarded: "Descartada",
  failed: "Falhou",
};

export function applicationStatusTone(status: ApplicationStatus): ToneName {
  return APPLICATION_STATUS_TONE[status] ?? "neutral";
}

export function applicationStatusLabel(status: ApplicationStatus): string {
  return APPLICATION_STATUS_LABEL[status] ?? humanizeSnakeCase(status);
}

const RUN_STATUS_TONE: Record<AutomationRunStatus, ToneName> = {
  pending: "neutral",
  running: "accent",
  paused: "warning",
  completed: "success",
  stopped: "neutral",
  failed: "danger",
  blocked: "danger",
};

export function runStatusTone(status: AutomationRunStatus): ToneName {
  return RUN_STATUS_TONE[status] ?? "neutral";
}

const RUN_STATUS_LABEL: Record<AutomationRunStatus, string> = {
  pending: "Pendente",
  running: "Em execução",
  paused: "Pausada",
  completed: "Concluída",
  stopped: "Parada",
  failed: "Falhou",
  blocked: "Bloqueada",
};

export function runStatusLabel(status: AutomationRunStatus): string {
  return RUN_STATUS_LABEL[status] ?? humanizeSnakeCase(status);
}

/**
 * Portuguese labels for the loose snake_case enum values rendered around the UI
 * (run kinds, remote/workplace filters, date-posted windows, event types).
 * Falls back to a humanized English form for anything not mapped.
 */
const ENUM_LABELS: Record<string, string> = {
  // Automation run kinds
  search: "Busca",
  prepare: "Preenchimento",
  submit: "Envio",
  apply: "Candidatura",
  // Remote / workplace type
  remote: "Remoto",
  hybrid: "Híbrido",
  on_site: "Presencial",
  "on-site": "Presencial",
  onsite: "Presencial",
  office: "Presencial",
  // Date-posted windows
  any_time: "Qualquer data",
  past_month: "Último mês",
  "past-month": "Último mês",
  past_week: "Última semana",
  "past-week": "Última semana",
  past_24_hours: "Últimas 24 horas",
  "past-24h": "Últimas 24 horas",
  // Application event types. Six of these were missing, so the trail fell back
  // to `humanizeSnakeCase` and printed "Job found" and "Cover letter generated"
  // in the middle of a Portuguese screen.
  created: "Criada",
  job_found: "Vaga encontrada",
  job_analyzed: "Vaga comparada com o seu perfil",
  score_assigned: "Nota atribuída",
  prepare_started: "Preenchimento iniciado",
  prepared: "Preparada",
  form_opened: "Formulário aberto",
  form_step_completed: "Etapa do formulário concluída",
  form_changed: "O formulário da vaga mudou",
  question_answered: "Pergunta respondida",
  cover_letter_generated: "Carta de apresentação gerada",
  resume_uploaded: "Currículo anexado",
  awaiting_review: "Parada para a sua revisão",
  user_edited: "Editada por você",
  user_approved: "Aprovada por você",
  resume_adapted: "Currículo adaptado",
  submitted: "Enviada",
  discarded: "Descartada",
  outcome_changed: "Desfecho alterado",
  checkpoint: "Verificação de segurança",
  error: "Erro",
};

export function enumLabel(value: string): string {
  return ENUM_LABELS[value] ?? humanizeSnakeCase(value);
}

/** Fields the backend names in a `user_edited` payload, in the user's words. */
const EDITED_FIELDS: Record<string, string> = {
  cover_letter: "a carta de apresentação",
  screening_answers: "as respostas de triagem",
  resume_filename: "o currículo anexado",
};

/**
 * The second line of a trail entry, composed here rather than taken from the API.
 *
 * The engine writes `message` in English — "Opened the Easy Apply form (4
 * steps)", "AI scored this job 86/100" — which is fine as a server log and wrong
 * as interface copy on a Portuguese screen. It is also redundant: the posting's
 * title is the page heading, the score is beside it, and the step count is a
 * badge under it, so the sentences were repeating what the reader had just
 * read.
 *
 * So the known events say their piece in Portuguese, using the payload where it
 * carries something the screen does not already show. Anything unrecognised —
 * and every error, where the text *is* the information — keeps the original
 * message rather than being silently dropped.
 */
export function applicationEventDetail(event: {
  event_type: string;
  message: string | null;
  payload?: Record<string, unknown> | null;
  is_error?: boolean;
}): string | null {
  if (event.is_error || event.event_type === "error") return event.message;

  if (event.event_type === "user_edited") {
    const fields = Array.isArray(event.payload?.fields)
      ? (event.payload?.fields as unknown[]).filter(
          (field): field is string => typeof field === "string",
        )
      : [];
    const named = fields.map((field) => EDITED_FIELDS[field] ?? field);
    // Three identical "the user edited the application" rows said nothing about
    // what changed; the payload has known it all along.
    return named.length > 0 ? `Você alterou ${joinTerms(named)}.` : null;
  }

  const composed: Record<string, string> = {
    job_found: "Encontrada por uma busca sua.",
    job_analyzed: "Comparada com o seu currículo; a nota está no topo desta página.",
    form_opened: "A automação abriu o formulário da vaga.",
    question_answered: "Resposta preenchida a partir do seu perfil, para você conferir.",
    cover_letter_generated: "Rascunho gerado para você revisar e editar.",
    awaiting_review: "Preenchida e parada aqui. Nada sai sem a sua aprovação.",
    user_approved: "Você aprovou o envio desta candidatura.",
    submitted: "Enviada ao portal da vaga.",
    resume_adapted: "Uma versão do seu currículo foi derivada para esta vaga.",
    form_changed: "As perguntas mudaram desde a sua revisão, então o envio foi recusado.",
  };
  return composed[event.event_type] ?? event.message;
}

/* -------------------------------------------------------------------------- */
/* Resume adaptation                                                          */
/* -------------------------------------------------------------------------- */

/**
 * "mar 2022 — atual" for one position.
 *
 * Composed here rather than on the backend: the API stores plain ISO dates, so
 * the wording and the locale stay in the one place the rest of the UI keeps them.
 */
export function experiencePeriod(
  startedOn: string | null,
  endedOn: string | null,
  isCurrent: boolean,
): string {
  const monthYear = (value: string | null): string | null => {
    const date = toDate(value);
    if (!date) return null;
    return date.toLocaleDateString("pt-BR", { month: "short", year: "numeric" });
  };

  const start = monthYear(startedOn);
  const end = isCurrent ? "atual" : monthYear(endedOn);
  if (start && end) return `${start} — ${end}`;
  if (start) return start;
  if (end) return end;
  return "—";
}

/**
 * Section headings for the change report, one per `ResumeChangeKind`.
 *
 * The backend emits the kind and the terms; the wording lives here because the
 * derivation is local and deterministic — generating Portuguese prose there
 * would leave the product with two vocabularies to keep in step.
 */
const RESUME_CHANGE_LABELS: Record<string, string> = {
  experience_prioritized: "Experiências priorizadas",
  experience_refocused: "Descrições reordenadas",
  skill_highlighted: "Competências destacadas",
  technology_emphasized: "Tecnologias enfatizadas",
  project_selected: "Projetos relevantes",
};

/** The order the review screen reads them in: biggest structural change first. */
export const RESUME_CHANGE_ORDER: readonly string[] = [
  "experience_prioritized",
  "experience_refocused",
  "skill_highlighted",
  "technology_emphasized",
  "project_selected",
];

export function resumeChangeLabel(kind: string): string {
  return RESUME_CHANGE_LABELS[kind] ?? humanizeSnakeCase(kind);
}

const FIT_FACTOR_LABELS: Record<string, string> = {
  technologies: "Tecnologias pedidas",
  experience: "Experiência mais próxima",
  skills: "Competências do perfil",
  seniority: "Tempo de experiência",
};

export function fitFactorLabel(factor: string): string {
  return FIT_FACTOR_LABELS[factor] ?? humanizeSnakeCase(factor);
}

/**
 * The band a score falls in, in words.
 *
 * Mirrors `app.domain.scoring.VERDICT_BANDS`. The backend sends the band name
 * and the frontend owns every sentence about it, so moving a boundary is a
 * one-file change on each side and never a disagreement between them.
 */
const VERDICT_LABELS: Record<string, string> = {
  strong: "Excelente compatibilidade",
  good: "Boa compatibilidade",
  moderate: "Compatibilidade parcial",
  weak: "Compatibilidade baixa",
  poor: "Pouca aderência",
};

export function verdictLabel(verdict: string | null | undefined): string {
  if (!verdict) return "Ainda não analisada";
  return VERDICT_LABELS[verdict] ?? humanizeSnakeCase(verdict);
}

/**
 * "A", "A e B", "A, B e C" — a list a person reads, not one a machine prints.
 *
 * Capped because these render inline inside a sentence: past three names the
 * sentence stops being read and starts being skimmed.
 */
export function joinTerms(terms: readonly string[], max = 3): string {
  const shown = terms.slice(0, max);
  if (shown.length === 0) return "";
  if (shown.length === 1) return shown[0];
  const rest = terms.length > max ? ` e mais ${terms.length - max}` : "";
  return `${shown.slice(0, -1).join(", ")} e ${shown[shown.length - 1]}${rest}`;
}

/** Score colour ramp for badges, bars and chart marks. */
export function scoreTone(score: number | null | undefined): ToneName {
  if (score === null || score === undefined) return "neutral";
  if (score >= 80) return "success";
  if (score >= 60) return "accent";
  if (score >= 40) return "warning";
  return "danger";
}

const LEVEL_TONE: Record<EventLevel, ToneName> = {
  info: "info",
  warning: "warning",
  error: "danger",
  success: "success",
};

export function eventLevelTone(level: EventLevel): ToneName {
  return LEVEL_TONE[level] ?? "info";
}

const LEVEL_TEXT_CLASS: Record<EventLevel, string> = {
  info: "text-content-muted",
  warning: "text-warning",
  error: "text-danger",
  success: "text-success",
};

export function eventLevelTextClass(level: EventLevel): string {
  return LEVEL_TEXT_CLASS[level] ?? "text-content-muted";
}
