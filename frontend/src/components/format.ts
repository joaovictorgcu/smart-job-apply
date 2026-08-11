/**
 * Display-only formatting helpers shared by the UI layer.
 *
 * Kept next to the components (rather than in `@/lib`) so the presentation
 * layer owns its own copy strings and never drifts from the data layer.
 */

type DateInput = string | number | Date | null | undefined;

function toDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === '') return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: DateInput, fallback = '—'): string {
  const date = toDate(value);
  if (!date) return fallback;
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
  });
}

export function formatDateTime(value: DateInput, fallback = '—'): string {
  const date = toDate(value);
  if (!date) return fallback;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatClock(value: DateInput, fallback = '--:--:--'): string {
  const date = toDate(value);
  if (!date) return fallback;
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

const RELATIVE_STEPS: Array<[limit: number, divisor: number, unit: string]> = [
  [60, 1, 's'],
  [3600, 60, 'm'],
  [86400, 3600, 'h'],
  [2592000, 86400, 'd'],
];

export function formatRelative(value: DateInput, fallback = '—'): string {
  const date = toDate(value);
  if (!date) return fallback;
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 5) return 'just now';
  const past = seconds >= 0;
  const magnitude = Math.abs(seconds);
  for (const [limit, divisor, unit] of RELATIVE_STEPS) {
    if (magnitude < limit) {
      const amount = Math.max(1, Math.floor(magnitude / divisor));
      return past ? `${amount}${unit} ago` : `in ${amount}${unit}`;
    }
  }
  return formatDate(date, fallback);
}

export function formatNumber(value: number | null | undefined, fallback = '—'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback;
  return value.toLocaleString();
}

export function formatScore(value: number | null | undefined, fallback = '—'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback;
  return String(Math.round(value));
}

export function formatDelayRange(min: number, max: number): string {
  const round = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));
  return `${round(min)}–${round(max)}s`;
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return count === 1 ? singular : plural;
}

/** Turns snake_case enum values into human labels ("awaiting_review" -> "Awaiting review"). */
export function humanizeToken(value: string): string {
  const spaced = value.replace(/[_.-]+/g, ' ').trim();
  if (!spaced) return value;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase();
}

export function truncate(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

export function initialsOf(name: string | null | undefined, email?: string | null): string {
  const source = (name ?? '').trim() || (email ?? '').split('@')[0] || '?';
  const parts = source.split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}
