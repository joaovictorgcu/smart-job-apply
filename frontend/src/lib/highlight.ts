/**
 * Marking, inside a sentence, the words this vacancy actually asked for.
 *
 * The derivation already decided which of the candidate's terms a posting
 * matches — `AdaptedExperience.matched_terms` is that answer, computed on the
 * server. This does not re-decide it. It only finds those terms in the text so
 * the reader can see *why* a bullet is where it is, in the bullet itself.
 *
 * That distinction matters: an LLM-written resume can claim it tailored
 * something; this one can point at the words. Nothing here can introduce a term
 * that was not already in `matched_terms`.
 *
 * The boundary rule is ported from `app.domain.technologies._term_pattern` and
 * has to stay faithful to it, because the two are answering the same question
 * about the same strings. A `\b` boundary is wrong for this vocabulary: `\b.net`
 * never matches (the dot is already a non-word character) and `\bc#\b` never
 * matches either. Guarding on alphanumeric neighbours instead makes `.NET`, `C#`
 * and `Node.js` behave like the single words they are — while still refusing to
 * find `java` inside `javascript`.
 */

/** Same folding as `app.domain.language.fold`: lowercase, accents removed. */
export function fold(text: string): string {
  return text.normalize("NFKD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

export interface Segment {
  text: string;
  /** True when this segment is one of the terms the posting asked about. */
  matched: boolean;
}

const ESCAPE = /[.*+?^${}()|[\]\\#]/g;

function pattern(terms: readonly string[]): RegExp | null {
  const cleaned = terms
    .map((term) => term.trim())
    .filter((term) => term.length > 0)
    // Longest first, so ".NET Core" wins over ".NET" where both match.
    .sort((a, b) => b.length - a.length)
    .map((term) => fold(term).replace(ESCAPE, "\\$&"));

  if (cleaned.length === 0) return null;
  // Boundaries asserted against alphanumerics only — see the module comment.
  return new RegExp(`(?<![a-z0-9])(?:${cleaned.join("|")})(?![a-z0-9])`, "g");
}

/**
 * Split `text` into runs, flagging the ones that are a matched term.
 *
 * Indices are taken on the folded string and applied to the original, which is
 * safe only while folding preserves length. It does for this vocabulary — no
 * technology name is accented — and a mismatch would show up as a highlight one
 * character off rather than as wrong text, since the original is what renders.
 */
export function splitByTerms(text: string, terms: readonly string[]): Segment[] {
  const source = text ?? "";
  const expression = pattern(terms);
  if (!expression || source.length === 0) {
    return source ? [{ text: source, matched: false }] : [];
  }

  const folded = fold(source);
  if (folded.length !== source.length) {
    // Folding changed the length, so an index from it would land in the wrong
    // place. Render the sentence plain rather than highlight the wrong words.
    return [{ text: source, matched: false }];
  }

  const segments: Segment[] = [];
  let cursor = 0;
  for (const match of folded.matchAll(expression)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      segments.push({ text: source.slice(cursor, start), matched: false });
    }
    segments.push({ text: source.slice(start, start + match[0].length), matched: true });
    cursor = start + match[0].length;
  }
  if (cursor < source.length) {
    segments.push({ text: source.slice(cursor), matched: false });
  }
  return segments;
}
