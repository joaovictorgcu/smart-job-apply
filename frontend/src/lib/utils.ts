import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Conditional class names with Tailwind conflict resolution. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

/** Capped exponential backoff: attempt 0 -> base, doubling up to `max`. */
export function backoffDelay(attempt: number, base = 1000, max = 30000): number {
  const exponential = base * 2 ** Math.max(0, attempt);
  const jitter = Math.random() * base * 0.5;
  return Math.min(exponential + jitter, max);
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/** Serializes query params, dropping null/undefined/empty-string values. */
export function buildQuery(
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

/* -------------------------------------------------------------------------- */
/* Untrusted URLs                                                             */
/* -------------------------------------------------------------------------- */

/** The only two schemes a link from outside this app may use. */
const SAFE_SCHEMES = new Set(["http:", "https:"]);

/**
 * A posting's URL, or `null` when it is not safe to link to.
 *
 * `job.url` is *not* ours. The LinkedIn adapter builds it from a template, but
 * the Gupy one copies `jobUrl` out of that portal's JSON response, so the value
 * reaching `href` is third-party input. A `javascript:` URL in an `href`
 * executes in this origin the moment somebody clicks the link — with the
 * session token in `localStorage` right there — and `data:`/`blob:` URLs open
 * attacker-authored documents that look like they came from us.
 *
 * Parsing rather than pattern-matching: `URL` resolves the escapes, the
 * whitespace and the mixed case that defeat a regex ("java\nscript:", "JaVa
 * ScRiPt:", "%6Aavascript:"). A relative URL is rejected too — an external link
 * that is not absolute is not the link anyone meant.
 */
export function safeExternalUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return SAFE_SCHEMES.has(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

/**
 * A same-origin path to return to after logging in, or `/`.
 *
 * The guards record where the visitor was heading, and the login screen
 * navigates there afterwards — so the browser's own address bar decides the
 * argument. A path beginning `//` (or `/\`) is read as *protocol-relative* by
 * the router and by `window.location` alike, which turns `https://app//evil.com`
 * into an open redirect: the user signs in and lands on a page that is not this
 * app while believing it is. That is the phishing half of the React Router
 * advisories this project pinned past (GHSA-2j2x-hqr9-3h42), and the reason
 * this guard stays even on a patched router.
 *
 * Accepts only a single leading slash, which is every real route in this app.
 */
export function safeRedirectPath(path: string | null | undefined): string {
  if (!path || !path.startsWith("/")) return "/";
  // Backslashes included: browsers normalise "/\evil.com" to "//evil.com".
  if (/^[/\\]{2,}/.test(path)) return "/";
  return path;
}

export function uniqueBy<T, K>(items: T[], keyOf: (item: T) => K): T[] {
  const seen = new Set<K>();
  const result: T[] = [];
  for (const item of items) {
    const key = keyOf(item);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result;
}

export function groupBy<T, K extends string>(
  items: T[],
  keyOf: (item: T) => K,
): Record<K, T[]> {
  const result = {} as Record<K, T[]>;
  for (const item of items) {
    const key = keyOf(item);
    (result[key] ??= []).push(item);
  }
  return result;
}

/** Debounces a function on the trailing edge; returns a cancelable wrapper. */
export function debounce<Args extends unknown[]>(
  fn: (...args: Args) => void,
  waitMs = 250,
): ((...args: Args) => void) & { cancel: () => void } {
  let timer: number | undefined;
  const wrapped = (...args: Args) => {
    if (timer !== undefined) window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), waitMs);
  };
  wrapped.cancel = () => {
    if (timer !== undefined) window.clearTimeout(timer);
    timer = undefined;
  };
  return wrapped;
}
