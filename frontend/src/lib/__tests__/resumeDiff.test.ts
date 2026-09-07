/**
 * The difference the "Diferenças" tab is built from.
 *
 * A pure function over two documents, so these tests state exactly what the
 * user is told: what moved, what was re-worded, what was folded away — and,
 * separately, what a hand edit added that the master resume does not have.
 */

import { describe, expect, it } from "vitest";

import { diffResume } from "@/lib/resumeDiff";
import { buildApplicationResume, buildExperience, buildResumeDocument } from "@/test/factories";

describe("diffResume", () => {
  it("reports no differences when the version is the master", () => {
    const document = buildResumeDocument();

    const diff = diffResume(document, buildResumeDocument());

    expect(diff.hasChanges).toBe(false);
    expect(diff.changedCount).toBe(0);
  });

  it("reports a re-worded summary with both sentences", () => {
    const version = buildApplicationResume();

    const diff = diffResume(version.base_document, version.document);

    expect(diff.summaryChanged).toBe(true);
    expect(diff.baseSummary).toBe("Nove anos construindo produtos web.");
    expect(diff.summary).toContain("ênfase em .NET 8");
  });

  it("reports an experience that moved up, in positions a reader can use", () => {
    const base = buildResumeDocument();
    const document = buildResumeDocument({
      experiences: [base.experiences[1], base.experiences[0]],
    });

    const diff = diffResume(base, document);

    expect(diff.experiencesReordered).toBe(true);
    const promoted = diff.experiences.find((item) => item.key === "nexo-fullstack");
    expect(promoted?.basePosition).toBe(2);
    expect(promoted?.position).toBe(1);
    expect(promoted?.movedUpBy).toBe(1);
  });

  it("counts achievements folded away without calling them removed facts", () => {
    const base = buildResumeDocument();
    const document = buildResumeDocument({
      experiences: [
        buildExperience({ highlights: [base.experiences[0].highlights[0]] }),
        base.experiences[1],
      ],
    });

    const diff = diffResume(base, document);
    const experience = diff.experiences[0];

    expect(experience.highlightsHidden).toBe(1);
    expect(experience.highlightsAdded).toEqual([]);
    expect(experience.changed).toBe(true);
  });

  it("separates a promoted technology from one the master resume lacks", () => {
    const base = buildResumeDocument();
    const document = buildResumeDocument({
      experiences: [
        buildExperience({ technologies: ["SQL Server", ".NET 8", "Kubernetes"] }),
        base.experiences[1],
      ],
    });

    const diff = diffResume(base, document);
    const experience = diff.experiences[0];

    expect(experience.technologiesPromoted).toEqual(["SQL Server"]);
    expect(experience.technologiesAdded).toEqual(["Kubernetes"]);
    // Dropping one is reported too, and separately: omitting a technology and
    // inventing one are different acts, and only one of them needs a warning.
    expect(experience.technologiesRemoved).toEqual(["Blazor"]);
  });

  it("flags an achievement the user wrote that is not in the master", () => {
    const base = buildResumeDocument();
    const document = buildResumeDocument({
      experiences: [
        buildExperience({
          highlights: [
            ...base.experiences[0].highlights,
            { text: "Frase que eu escrevi agora.", technologies: [], impact: null },
          ],
        }),
        base.experiences[1],
      ],
    });

    const diff = diffResume(base, document);

    expect(diff.experiences[0].highlightsAdded).toEqual(["Frase que eu escrevi agora."]);
  });

  it("names an experience dropped from the version entirely", () => {
    const base = buildResumeDocument();
    const document = buildResumeDocument({ experiences: [base.experiences[0]] });

    const diff = diffResume(base, document);

    expect(diff.droppedExperiences).toEqual(["Engenheiro Full Stack — Nexo Digital"]);
    expect(diff.hasChanges).toBe(true);
  });
});
