/**
 * The two guards that stand between untrusted input and a URL the browser acts on.
 *
 * Both are security boundaries, so the cases below are the evasions rather than
 * the happy path: a scheme hidden behind escapes, and a path that is "absolute"
 * to a reader but protocol-relative to a browser.
 */

import { describe, expect, it } from "vitest";

import { safeExternalUrl, safeRedirectPath } from "@/lib/utils";

describe("safeExternalUrl", () => {
  it("keeps an ordinary posting link", () => {
    expect(safeExternalUrl("https://www.linkedin.com/jobs/view/123")).toBe(
      "https://www.linkedin.com/jobs/view/123",
    );
    expect(safeExternalUrl("http://empresa.com.br/vaga")).toBe("http://empresa.com.br/vaga");
  });

  it("refuses a script URL", () => {
    // The portal adapters copy this field out of a third party's response, and
    // an href that runs script runs it in this origin.
    expect(safeExternalUrl("javascript:alert(document.cookie)")).toBeNull();
  });

  it("refuses the spellings that defeat a regex", () => {
    expect(safeExternalUrl("JaVaScRiPt:alert(1)")).toBeNull();
    expect(safeExternalUrl("  javascript:alert(1)  ")).toBeNull();
    expect(safeExternalUrl("java\nscript:alert(1)")).toBeNull();
    expect(safeExternalUrl("\tjavascript:alert(1)")).toBeNull();
  });

  it("refuses schemes that open attacker-authored documents", () => {
    expect(safeExternalUrl("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(safeExternalUrl("blob:https://app/whatever")).toBeNull();
    expect(safeExternalUrl("vbscript:msgbox(1)")).toBeNull();
    expect(safeExternalUrl("file:///etc/passwd")).toBeNull();
  });

  it("refuses a relative or missing URL", () => {
    expect(safeExternalUrl("/jobs/12")).toBeNull();
    expect(safeExternalUrl("not a url")).toBeNull();
    expect(safeExternalUrl("")).toBeNull();
    expect(safeExternalUrl(null)).toBeNull();
    expect(safeExternalUrl(undefined)).toBeNull();
  });
});

describe("safeRedirectPath", () => {
  it("keeps a real route, query string included", () => {
    expect(safeRedirectPath("/applications?status=awaiting_review")).toBe(
      "/applications?status=awaiting_review",
    );
    expect(safeRedirectPath("/admin")).toBe("/admin");
  });

  it("refuses a protocol-relative path", () => {
    // "https://app//evil.com" would otherwise send the user off-site right
    // after they typed their password.
    expect(safeRedirectPath("//evil.com")).toBe("/");
    expect(safeRedirectPath("///evil.com")).toBe("/");
  });

  it("refuses the backslash variants browsers normalise to //", () => {
    // This is the CVE-2025-68470 bypass the router still carries.
    expect(safeRedirectPath("/\\evil.com")).toBe("/");
    expect(safeRedirectPath("\\\\evil.com")).toBe("/");
  });

  it("refuses an absolute URL and falls back to the root", () => {
    expect(safeRedirectPath("https://evil.com")).toBe("/");
    expect(safeRedirectPath("javascript:alert(1)")).toBe("/");
    expect(safeRedirectPath("")).toBe("/");
    expect(safeRedirectPath(null)).toBe("/");
    expect(safeRedirectPath(undefined)).toBe("/");
  });
});
