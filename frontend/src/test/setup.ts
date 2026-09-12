/**
 * Global test setup.
 *
 * Beyond the jest-dom matchers, this file makes the suite fail loudly on any
 * real network call: every test must stub what it needs, so a forgotten mock
 * shows up as an explicit error instead of a hanging or flaky request.
 */

import "@testing-library/jest-dom/vitest";

import { afterEach, beforeEach, vi } from "vitest";

/*
 * jsdom implements no media queries at all, and components that animate ask for
 * `prefers-reduced-motion` on mount (see `useCountUp`) — without this they throw
 * "window.matchMedia is not a function" from inside an effect.
 *
 * It answers *yes* to reduced motion on purpose: the value then snaps to its
 * target instead of easing towards it over 700ms of requestAnimationFrame, so a
 * test asserting "1.248" reads the final number rather than racing the
 * animation. Every other query answers no.
 */
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes("prefers-reduced-motion"),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

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
