import type { ApplicationStatus, AutomationRunStatus, JobStatus } from "@/types/api";
import type { EventLevel } from "@/types/events";

const NUMBER_FORMAT = new Intl.NumberFormat("en-US");
const PERCENT_FORMAT = new Intl.NumberFormat("en-US", {
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
  return new Intl.NumberFormat("en-US", {
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
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

export function formatDateTime(value: string | Date | null | undefined): string {
  const date = toDate(value);
  if (!date) return "—";
  return date.toLocaleString("en-US", {
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
  return date.toLocaleTimeString("en-US", {
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

  const formatter = new Intl.RelativeTimeFormat("en-US", { numeric: "auto" });
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
  discovered: "Discovered",
  analyzed: "Analyzed",
  skipped: "Skipped",
  queued: "Queued",
  applied: "Applied",
  failed: "Failed",
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
  draft: "Draft",
  preparing: "Preparing",
  awaiting_review: "Awaiting review",
  submitting: "Submitting",
  submitted: "Submitted",
  discarded: "Discarded",
  failed: "Failed",
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

export function runStatusLabel(status: AutomationRunStatus): string {
  return humanizeSnakeCase(status);
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
