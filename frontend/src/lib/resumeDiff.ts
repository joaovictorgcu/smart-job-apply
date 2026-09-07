/**
 * What one application's resume changed relative to the master it came from.
 *
 * The server already sends *why* it changed (`changes`, written by the
 * derivation). This computes *what* changed, item by item, so the difference
 * can be shown against the actual document rather than described in prose —
 * and so an edit the user made by hand shows up too, which the server's change
 * list, written at derivation time, would not mention.
 *
 * Both documents come down in the same payload, so this is a pure function over
 * data already in hand: no request, no server-side diff endpoint.
 */

import type { ResumeDocument, ResumeExperience } from "@/types/api";

/** Items whose position moved forward, in their new order. */
function promoted(base: string[], next: string[]): string[] {
  return next.filter((item, index) => {
    const before = base.indexOf(item);
    return before > index;
  });
}

function sameOrder(base: string[], next: string[]): boolean {
  return base.length === next.length && base.every((item, index) => item === next[index]);
}

export interface ExperienceDiff {
  key: string;
  company: string;
  role: string;
  /** 1-based, so it reads as "3rd → 1st" without arithmetic in the view. */
  basePosition: number;
  position: number;
  /** Positive when this experience moved up the resume. */
  movedUpBy: number;
  summaryChanged: boolean;
  baseSummary: string | null;
  summary: string | null;
  /** The posting's terms this experience is being used to answer. */
  focus: string[];
  highlightsReordered: boolean;
  /** Achievements folded away because nothing here matched the posting. */
  highlightsHidden: number;
  /** Achievement text the master does not have — only a hand edit can do this. */
  highlightsAdded: string[];
  technologiesPromoted: string[];
  technologiesAdded: string[];
  technologiesRemoved: string[];
  projectsReordered: boolean;
  changed: boolean;
}

export interface ResumeDiff {
  summaryChanged: boolean;
  baseSummary: string | null;
  summary: string | null;
  experiencesReordered: boolean;
  skillsPromoted: string[];
  technologiesPromoted: string[];
  projectsReordered: boolean;
  experiences: ExperienceDiff[];
  /** Experiences the master has that this version dropped entirely. */
  droppedExperiences: string[];
  changedCount: number;
  hasChanges: boolean;
}

function experienceDiff(
  base: ResumeExperience,
  next: ResumeExperience,
  basePosition: number,
  position: number,
): ExperienceDiff {
  const baseHighlights = base.highlights.map((item) => item.text);
  const nextHighlights = next.highlights.map((item) => item.text);
  const kept = nextHighlights.filter((text) => baseHighlights.includes(text));

  const technologiesAdded = next.technologies.filter(
    (item) => !base.technologies.includes(item),
  );
  const technologiesRemoved = base.technologies.filter(
    (item) => !next.technologies.includes(item),
  );

  const diff: ExperienceDiff = {
    key: next.key,
    company: next.company,
    role: next.role,
    basePosition,
    position,
    movedUpBy: basePosition - position,
    summaryChanged: (base.summary ?? "") !== (next.summary ?? ""),
    baseSummary: base.summary,
    summary: next.summary,
    focus: next.focus,
    // Reordering is only meaningful among the achievements that survived.
    highlightsReordered: !sameOrder(
      baseHighlights.filter((text) => kept.includes(text)),
      kept,
    ),
    highlightsHidden: baseHighlights.filter((text) => !nextHighlights.includes(text)).length,
    highlightsAdded: nextHighlights.filter((text) => !baseHighlights.includes(text)),
    technologiesPromoted: promoted(base.technologies, next.technologies),
    technologiesAdded,
    technologiesRemoved,
    projectsReordered: !sameOrder(
      base.projects.map((item) => item.name),
      next.projects.map((item) => item.name),
    ),
    changed: false,
  };

  diff.changed =
    diff.movedUpBy !== 0 ||
    diff.summaryChanged ||
    diff.highlightsReordered ||
    diff.highlightsHidden > 0 ||
    diff.highlightsAdded.length > 0 ||
    diff.technologiesPromoted.length > 0 ||
    technologiesAdded.length > 0 ||
    technologiesRemoved.length > 0 ||
    diff.projectsReordered;

  return diff;
}

/**
 * Compare an application's resume against the master snapshot it was built from.
 *
 * The snapshot, not the live master: this answers "how does this application
 * present me differently", and comparing against a profile the user edited
 * afterwards would blame the version for changes it never made. Staleness
 * against the live master is a separate flag the server sends.
 */
export function diffResume(base: ResumeDocument, document: ResumeDocument): ResumeDiff {
  const basePositions = new Map(base.experiences.map((item, index) => [item.key, index]));

  const experiences = document.experiences.map((experience, index) => {
    const basePosition = basePositions.get(experience.key);
    const source =
      basePosition === undefined ? experience : base.experiences[basePosition] ?? experience;
    return experienceDiff(
      source,
      experience,
      (basePosition ?? index) + 1,
      index + 1,
    );
  });

  const documentKeys = new Set(document.experiences.map((item) => item.key));
  const diff: ResumeDiff = {
    summaryChanged: (base.summary ?? "") !== (document.summary ?? ""),
    baseSummary: base.summary,
    summary: document.summary,
    experiencesReordered: !sameOrder(
      base.experiences.map((item) => item.key),
      document.experiences.map((item) => item.key),
    ),
    skillsPromoted: promoted(base.skills, document.skills),
    technologiesPromoted: promoted(base.technologies, document.technologies),
    projectsReordered: !sameOrder(
      base.projects.map((item) => item.name),
      document.projects.map((item) => item.name),
    ),
    experiences,
    droppedExperiences: base.experiences
      .filter((item) => !documentKeys.has(item.key))
      .map((item) => `${item.role} — ${item.company}`),
    changedCount: 0,
    hasChanges: false,
  };

  diff.changedCount =
    experiences.filter((item) => item.changed).length +
    (diff.summaryChanged ? 1 : 0) +
    (diff.skillsPromoted.length > 0 ? 1 : 0) +
    (diff.technologiesPromoted.length > 0 ? 1 : 0) +
    (diff.projectsReordered ? 1 : 0);
  diff.hasChanges = diff.changedCount > 0 || diff.droppedExperiences.length > 0;

  return diff;
}
