/**
 * Finding, inside a sentence, the terms the posting asked for.
 *
 * This is a port of `app.domain.technologies._term_pattern`, and the reason it
 * is tested this closely is that the two have to agree. The backend decided
 * which terms matched; if the frontend highlights a different set, the screen
 * stops explaining the ranking and starts contradicting it.
 *
 * The cases are the ones a word-boundary rule gets wrong: a leading dot, a
 * trailing hash, and one technology whose name contains another's.
 */

import { describe, expect, it } from "vitest";

import { splitByTerms } from "@/lib/highlight";

const matched = (text: string, terms: string[]) =>
  splitByTerms(text, terms)
    .filter((segment) => segment.matched)
    .map((segment) => segment.text);

describe("splitByTerms", () => {
  it("keeps the sentence intact when it joins the pieces back", () => {
    const text = "Construí APIs em .NET 8 sobre PostgreSQL.";
    const segments = splitByTerms(text, [".NET", "PostgreSQL"]);

    expect(segments.map((segment) => segment.text).join("")).toBe(text);
  });

  it("finds a term that starts with punctuation", () => {
    expect(matched("Migrei o serviço para .NET 8.", [".NET"])).toEqual([".NET"]);
  });

  it("finds a term that ends with punctuation", () => {
    expect(matched("Escrevi em C# e em Python.", ["C#", "Python"])).toEqual(["C#", "Python"]);
  });

  it("does not find one technology inside another's name", () => {
    // The failure this guards: `java` lighting up inside `javascript`, which
    // would claim the posting asked for something it did not.
    expect(matched("Trabalho com JavaScript no dia a dia.", ["Java"])).toEqual([]);
  });

  it("prefers the longer term when two overlap", () => {
    expect(matched("Serviços em .NET Core.", [".NET", ".NET Core"])).toEqual([".NET Core"]);
  });

  it("matches whatever case and accents the sentence used", () => {
    expect(matched("Experiência com REACT e com react.", ["React"])).toEqual(["REACT", "react"]);
  });

  it("marks nothing when the posting asked for nothing", () => {
    expect(matched("Uma frase qualquer.", [])).toEqual([]);
    expect(splitByTerms("Uma frase qualquer.", [])).toHaveLength(1);
  });

  it("cannot mark a term that was not handed to it", () => {
    // The whole guarantee: highlighting reads `matched_terms`, it does not
    // decide what matched.
    expect(matched("Orquestrei com Kubernetes e Docker.", ["Docker"])).toEqual(["Docker"]);
  });

  it("survives an empty sentence", () => {
    expect(splitByTerms("", ["React"])).toEqual([]);
  });
});
