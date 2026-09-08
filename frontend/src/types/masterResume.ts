/**
 * Master-resume shapes for the structured-profile editor.
 *
 * Three branches implemented the tailored resume in parallel and all three are
 * on main. These are one of those branches' types, kept in their own module
 * because `ResumeProject` collides by name with a differently shaped type in
 * `types/api.ts` — the one the live implementation uses. Importing from here
 * makes which of the two a file means unambiguous.
 */

export interface ResumeHighlight {
  text: string;
  technologies: string[];
}

export interface ResumeProject {
  id?: string | null;
  name: string;
  description: string;
  outcome: string;
  technologies: string[];
}

export interface ResumeExperience {
  /** Stable across edits; assigned by the server when absent. */
  id?: string | null;
  role: string;
  company: string;
  start: string;
  end: string;
  location: string;
  /** The neutral description, used for a posting that matches no highlight. */
  summary: string;
  highlights: ResumeHighlight[];
  technologies: string[];
}

export interface ResumeEducationEntry {
  id?: string | null;
  degree: string;
  institution: string;
  start: string;
  end: string;
  detail: string;
}
