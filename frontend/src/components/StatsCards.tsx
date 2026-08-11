import { Briefcase, ClipboardCheck, Gauge, TrendingUp } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';

import { formatNumber, formatScore } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { DashboardStats } from '@/types/api';

import { Card, ProgressRing, SectionLabel, Skeleton } from './primitives';

interface StatTileProps {
  icon: LucideIcon;
  label: string;
  value: string;
  suffix?: string;
  hint?: string;
  to?: string;
  emphasis?: boolean;
}

function StatTile({ icon: Icon, label, value, suffix, hint, to, emphasis }: StatTileProps) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>{label}</SectionLabel>
        <Icon
          aria-hidden
          className={cn('h-4 w-4 shrink-0', emphasis ? 'text-warning' : 'text-content-subtle')}
          strokeWidth={1.75}
        />
      </div>
      <p className="mt-2 flex items-baseline gap-1">
        <span className="tabular text-3xl font-semibold leading-none text-content">{value}</span>
        {suffix ? <span className="text-xs text-content-subtle">{suffix}</span> : null}
      </p>
      {hint ? <p className="mt-1.5 text-xs leading-snug text-content-subtle">{hint}</p> : null}
    </>
  );

  if (to) {
    return (
      <Link
        to={to}
        className={cn(
          'card card-hover block px-5 py-4',
          emphasis && 'border-warning/40 bg-warning/[0.06]',
        )}
      >
        {body}
      </Link>
    );
  }

  return <Card className={cn('px-5 py-4', emphasis && 'border-warning/40')}>{body}</Card>;
}

function TileSkeleton() {
  return (
    <Card className="space-y-3 px-5 py-4">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-8 w-16" />
      <Skeleton className="h-3 w-32" />
    </Card>
  );
}

export interface StatsCardsProps {
  stats?: DashboardStats;
  isLoading?: boolean;
  className?: string;
}

export function StatsCards({ stats, isLoading = false, className }: StatsCardsProps) {
  if (isLoading || !stats) {
    return (
      <div className={cn('grid gap-4 sm:grid-cols-2 xl:grid-cols-4', className)}>
        <TileSkeleton />
        <TileSkeleton />
        <TileSkeleton />
        <TileSkeleton />
      </div>
    );
  }

  const cap = stats.daily_cap;
  const today = stats.applications_today;
  const atCap = cap > 0 && today >= cap;

  return (
    <div className={cn('grid gap-4 sm:grid-cols-2 xl:grid-cols-4', className)}>
      <Card className="flex items-center gap-4 px-5 py-4">
        <ProgressRing value={today} max={cap} caption={`of ${cap}`} />
        <div className="min-w-0">
          <SectionLabel>Submitted today</SectionLabel>
          <p className="mt-1.5 text-sm font-medium text-content">
            {atCap ? 'Daily cap reached' : `${formatNumber(Math.max(0, cap - today))} left`}
          </p>
          <p className="mt-1 text-xs leading-snug text-content-subtle">
            {atCap
              ? 'No more submissions today. The cap protects the account from looking automated.'
              : 'The cap is a guard rail, not a target.'}
          </p>
        </div>
      </Card>

      <StatTile
        icon={ClipboardCheck}
        label="Awaiting review"
        value={formatNumber(stats.awaiting_review)}
        hint={
          stats.awaiting_review > 0
            ? 'Filled and stopped — waiting for your approval.'
            : 'Nothing is waiting on you.'
        }
        to="/applications?status=awaiting_review"
        emphasis={stats.awaiting_review > 0}
      />

      <StatTile
        icon={Briefcase}
        label="Jobs found"
        value={formatNumber(stats.jobs_total)}
        hint={`${formatNumber(stats.applications_total)} applications in total`}
        to="/jobs"
      />

      <StatTile
        icon={stats.average_score === null ? Gauge : TrendingUp}
        label="Average score"
        value={formatScore(stats.average_score)}
        suffix={stats.average_score === null ? undefined : '/ 100'}
        hint={
          stats.average_score === null
            ? 'No jobs have been scored yet.'
            : `${formatNumber(stats.ai_calls_total)} AI calls so far`
        }
      />
    </div>
  );
}
