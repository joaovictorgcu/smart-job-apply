/**
 * Global test setup.
 *
 * Beyond the jest-dom matchers, this file makes the suite fail loudly on any
 * real network call: every test must stub what it needs, so a forgotten mock
 * shows up as an explicit error instead of a hanging or flaky request.
 */

import "@testing-library/jest-dom/vitest";

import { afterEach, beforeEach, vi } from "vitest";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("Unexpected network call in a test."))),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});
