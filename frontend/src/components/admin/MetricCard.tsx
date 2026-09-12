import { ArrowDownRight, ArrowRight, ArrowUpRight, Minus } from 'lucide-react';
import { Link } from 'react-router-dom';

import { CountUp } from '@/components/CountUp';
import { Card, SectionLabel, Skeleton } from '@/components/primitives';
import { cn } from '@/lib/utils';
import type { Metric } from '@/types/api';

import { metricCopy } from './labels';
import { formatDelta, formatMetricValue } from './metricFormat';

const TREND_ICON = {
  up: ArrowUpRight,
  down: ArrowDownRight,
  flat: Minus,
  none: Minus,
} as const;

/**
 * `inverse` lives on the copy, not on the API: whether "more" is bad is a
 * product judgement, and the service should not have to encode taste.
 */
type Decorated = Metric & { inverseGood?: boolean };

function trendClass(metric: Decorated): string {
  if (metric.trend === 'flat' || metric.trend === 'none') return 'text-content-subtle';
  const rising = metric.trend === 'up';
  // The arrow always points the way the number moved; only the colour flips.
  const good = metric.inverseGood ? !rising : rising;
  return good ? 'text-success' : 'text-danger';
}

export interface MetricCardProps {
  metric: Metric;
  className?: string;
  /** Compact tiles for the second row, where six share the width. */
  dense?: boolean;
}

export function MetricCard({ metric, className, dense = false }: MetricCardProps) {
  const copy = metricCopy(metric.key);
  const decorated: Decorated = { ...metric, inverseGood: copy.inverse };
  const TrendIcon = TREND_ICON[metric.trend];
  const delta = formatDelta(metric);
  const Icon = copy.icon;

  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <SectionLabel>{copy.label}</SectionLabel>
        <Icon aria-hidden className="h-4 w-4 shrink-0 text-content-subtle" strokeWidth={1.75} />
      </div>

      <p className="mt-2 flex items-baseline gap-1.5">
        {metric.has_data ? (
          <span
            className={cn(
              'tabular font-semibold leading-none text-content',
              dense ? 'text-2xl' : 'text-3xl',
            )}
          >
            {metric.unit === 'count' ? (
              <CountUp value={metric.value} />
            ) : (
              formatMetricValue(metric.value, metric.unit)
            )}
          </span>
        ) : (
          <span
            className={cn(
              'font-semibold leading-none text-content-subtle',
              dense ? 'text-xl' : 'text-2xl',
            )}
          >
            sem dados
          </span>
        )}
      </p>

      {metric.has_data && delta ? (
        <p className={cn('mt-1.5 flex items-center gap-1 text-xs font-medium', trendClass(decorated))}>
          <TrendIcon aria-hidden className="h-3.5 w-3.5 shrink-0" />
          <span className="tabular">{delta}</span>
          <span className="font-normal text-content-subtle">vs. período anterior</span>
        </p>
      ) : metric.has_data && metric.previous !== null ? (
        <p className="mt-1.5 text-xs text-content-subtle">
          Período anterior:{' '}
          <span className="tabular">{formatMetricValue(metric.previous, metric.unit)}</span>
        </p>
      ) : (
        <p className="mt-1.5 text-xs text-content-subtle">
          {metric.has_data ? 'Sem base de comparação.' : 'Nada registrado neste período.'}
        </p>
      )}

      {copy.hint ? (
        <p className="mt-1 text-2xs leading-snug text-content-subtle">{copy.hint}</p>
      ) : null}
    </>
  );

  if (copy.to) {
    return (
      <Link
        to={copy.to}
        className={cn('card card-hover group block px-4 py-3.5', className)}
        aria-label={`${copy.label}: ver detalhes`}
      >
        {body}
        <span className="mt-2 inline-flex items-center gap-1 text-2xs font-medium text-accent-400 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100">
          Ver detalhes
          <ArrowRight aria-hidden className="h-3 w-3" />
        </span>
      </Link>
    );
  }

  return <Card className={cn('px-4 py-3.5', className)}>{body}</Card>;
}

export function MetricCardSkeleton({ dense = false }: { dense?: boolean }) {
  return (
    <Card className="space-y-2.5 px-4 py-3.5" aria-hidden>
      <Skeleton className="h-3 w-24" />
      <Skeleton className={dense ? 'h-6 w-14' : 'h-8 w-20'} />
      <Skeleton className="h-3 w-32" />
    </Card>
  );
}

export interface MetricGridProps {
  metrics: Metric[];
  isLoading?: boolean;
  /** How many tiles the row holds at the widest breakpoint. */
  columns?: 3 | 4 | 6;
  dense?: boolean;
  className?: string;
}

const COLUMN_CLASS: Record<3 | 4 | 6, string> = {
  // Mobile first, and re-flowed rather than shrunk: two tiles a row on a phone,
  // three on a tablet, the full row only on a desktop.
  3: 'grid gap-3 sm:grid-cols-2 lg:grid-cols-3',
  4: 'grid gap-3 sm:grid-cols-2 xl:grid-cols-4',
  6: 'grid gap-3 grid-cols-2 sm:grid-cols-3 xl:grid-cols-6',
};

export function MetricGrid({
  metrics,
  isLoading = false,
  columns = 4,
  dense = false,
  className,
}: MetricGridProps) {
  if (isLoading) {
    return (
      <div className={cn(COLUMN_CLASS[columns], className)} aria-busy="true">
        {Array.from({ length: columns }, (_, index) => (
          <MetricCardSkeleton key={index} dense={dense} />
        ))}
      </div>
    );
  }

  return (
    <div className={cn(COLUMN_CLASS[columns], className)}>
      {metrics.map((metric) => (
        <MetricCard key={metric.key} metric={metric} dense={dense} />
      ))}
    </div>
  );
}
