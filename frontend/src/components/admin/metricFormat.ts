/**
 * How a metric is printed. Its own module so it stays testable without
 * rendering, and so `MetricCard.tsx` exports nothing but components.
 */

import { formatNumber, formatPercent } from '@/lib/format';
import type { Metric, MetricUnit } from '@/types/api';

/** A metric's value, in its own unit. */
export function formatMetricValue(value: number, unit: MetricUnit): string {
  switch (unit) {
    case 'percent':
      return formatPercent(value);
    case 'milliseconds':
      return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`;
    case 'seconds':
      // Coarser as the number grows: "2,3 h" beats "8280 s" for a duration
      // nobody is going to subtract from anything.
      if (value < 90) return `${Math.round(value)} s`;
      if (value < 5400) return `${(value / 60).toFixed(0)} min`;
      if (value < 172800) return `${(value / 3600).toFixed(1)} h`;
      return `${(value / 86400).toFixed(1)} d`;
    case 'usd':
      return `US$ ${value.toFixed(2)}`;
    case 'count':
    default:
      return formatNumber(value);
  }
}

/**
 * The comparison line: "+14,2%" for a count, "+8,0 p.p." for a rate.
 *
 * A rate moves in percentage *points* and a count moves relatively; the two
 * cannot share a suffix without one of them lying. The backend already decided
 * which meaning `delta_pct` carries — this only prints it with the right unit.
 */
export function formatDelta(metric: Metric): string | null {
  if (metric.delta_pct === null || metric.trend === 'none') return null;
  const signed = metric.delta_pct >= 0 ? '+' : '−';
  const magnitude = Math.abs(metric.delta_pct) * 100;
  const suffix = metric.unit === 'percent' ? 'p.p.' : '%';
  const printed = magnitude.toFixed(1).replace('.', ',');
  return metric.unit === 'percent' ? `${signed}${printed} ${suffix}` : `${signed}${printed}${suffix}`;
}
