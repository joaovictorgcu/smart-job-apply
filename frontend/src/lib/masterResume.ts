/**
 * Helpers for editing the structured master resume.
 *
 * Separate from `MasterResumeEditor` so that file exports only components:
 * mixing the two breaks React Fast Refresh, which turns every keystroke in a
 * long resume form into a full remount and a lost cursor.
 */

import type { ResumeEducationEntry, ResumeExperience, ResumeProject } from "@/types/masterResume";

/**
 * Prefix marking an entry that exists only in this browser so far.
 *
 * The server derives a stable id from an entry's content when none is sent, and
 * that id is what a derived version points back at. A client-invented id would
 * be persisted as-is and stick around forever, so these are stripped on save
 * and exist purely as React keys until then.
 */
const TEMP_PREFIX = "novo:";

let temporaryCounter = 0;

function temporaryId(): string {
  temporaryCounter += 1;
  return `${TEMP_PREFIX}${temporaryCounter}`;
}

/** Replace client-only ids with null so the server assigns the real ones. */
export function stripTemporaryIds<T extends { id?: string | null }>(entries: T[]): T[] {
  return entries.map((entry) =>
    entry.id && entry.id.startsWith(TEMP_PREFIX) ? { ...entry, id: null } : entry,
  );
}

export function emptyExperience(): ResumeExperience {
  return {
    id: temporaryId(),
    role: "",
    company: "",
    start: "",
    end: "",
    location: "",
    summary: "",
    highlights: [],
    technologies: [],
  };
}

export function emptyProject(): ResumeProject {
  return { id: temporaryId(), name: "", description: "", outcome: "", technologies: [] };
}

export function emptyEducation(): ResumeEducationEntry {
  return { id: temporaryId(), degree: "", institution: "", start: "", end: "", detail: "" };
}

/** A React key for a list entry, falling back to its position. */
export function entryKey(entry: { id?: string | null }, index: number): string {
  return entry.id || `index-${index}`;
}

/** Move one entry within a list, returning the list unchanged when out of range. */
export function moveEntry<T>(entries: T[], from: number, to: number): T[] {
  if (to < 0 || to >= entries.length) return entries;
  const next = [...entries];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}
