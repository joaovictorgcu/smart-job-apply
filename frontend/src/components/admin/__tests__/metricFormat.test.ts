/**
 * How a metric prints.
 *
 * Worth its own test because both halves are the kind of thing a refactor
 * silently breaks: a duration that starts reading "8280" instead of "2,3 h", and
 * a rate whose eight-point rise is advertised as "+14,8%".
 */

import { describe, expect, it } from "vitest";

import { formatDelta, formatMetricValue } from "@/components/admin/metricFormat";
import type { Metric } from "@/types/api";

function metric(overrides: Partial<Metric> = {}): Metric {
  return {
    key: "jobs_found",
    value: 10,
    unit: "count",
    previous: null,
    delta_pct: null,
    trend: "none",
    has_data: true,
    ...overrides,
  };
}

describe("formatMetricValue", () => {
  it("prints a count with the pt-BR thousands separator", () => {
    expect(formatMetricValue(1248, "count")).toBe("1.248");
  });

  it("prints a rate as a percentage", () => {
    expect(formatMetricValue(0.62, "percent")).toBe("62%");
  });

  it("scales a duration to a unit a human reads", () => {
    expect(formatMetricValue(45, "seconds")).toBe("45 s");
    expect(formatMetricValue(600, "seconds")).toBe("10 min");
    expect(formatMetricValue(8280, "seconds")).toBe("2.3 h");
  });

  it("prints sub-second latency in milliseconds and the rest in seconds", () => {
    expect(formatMetricValue(420, "milliseconds")).toBe("420 ms");
    expect(formatMetricValue(1500, "milliseconds")).toBe("1.5 s");
  });

  it("prints a cost with its currency", () => {
    expect(formatMetricValue(0.1234, "usd")).toBe("US$ 0.12");
  });
});

describe("formatDelta", () => {
  it("reports a count's change relatively", () => {
    expect(formatDelta(metric({ delta_pct: 0.142, trend: "up" }))).toBe("+14,2%");
  });

  it("reports a rate's change in percentage points", () => {
    // 54% -> 62% is eight points. Printing "+14,8%" would be the flattering lie.
    const delta = formatDelta(
      metric({ key: "success_rate", unit: "percent", delta_pct: 0.08, trend: "up" }),
    );
    expect(delta).toBe("+8,0 p.p.");
  });

  it("marks a fall with a minus sign", () => {
    expect(formatDelta(metric({ delta_pct: -0.25, trend: "down" }))).toBe("−25,0%");
  });

  it("prints nothing when there is no comparison to make", () => {
    expect(formatDelta(metric({ previous: 0, trend: "none" }))).toBeNull();
  });
});
