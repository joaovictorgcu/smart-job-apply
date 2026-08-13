import { Briefcase, ClipboardCheck, Gauge, TrendingUp } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { CountUp } from '@/components/CountUp';
import { formatNumber, formatScore } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { DashboardStats } from '@/types/api';

import { Card, ProgressRing, SectionLabel, Skeleton } from './primitives';

interface StatTileProps {
  icon: LucideIcon;
  label: string;
  value: ReactNode;
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
        <ProgressRing value={today} max={cap} caption={`de ${cap}`} />
        <div className="min-w-0">
          <SectionLabel>Enviadas hoje</SectionLabel>
          <p className="mt-1.5 text-sm font-medium text-content">
            {atCap ? 'Limite diário atingido' : `${formatNumber(Math.max(0, cap - today))} restantes`}
          </p>
          <p className="mt-1 text-xs leading-snug text-content-subtle">
            {atCap
              ? 'Nenhum envio a mais hoje. O limite protege a conta de parecer automatizada.'
              : 'O limite é uma salvaguarda, não uma meta.'}
          </p>
        </div>
      </Card>

      <StatTile
        icon={ClipboardCheck}
        label="Aguardando revisão"
        value={<CountUp value={stats.awaiting_review} />}
        hint={
          stats.awaiting_review > 0
            ? 'Preenchidas e paradas — aguardando a sua aprovação.'
            : 'Nada esperando por você.'
        }
        to="/applications?status=awaiting_review"
        emphasis={stats.awaiting_review > 0}
      />

      <StatTile
        icon={Briefcase}
        label="Vagas encontradas"
        value={<CountUp value={stats.jobs_total} />}
        hint={`${formatNumber(stats.applications_total)} candidaturas no total`}
        to="/jobs"
      />

      <StatTile
        icon={stats.average_score === null ? Gauge : TrendingUp}
        label="Nota média"
        value={formatScore(stats.average_score)}
        suffix={stats.average_score === null ? undefined : '/ 100'}
        hint={
          stats.average_score === null
            ? 'Nenhuma vaga foi pontuada ainda.'
            : `${formatNumber(stats.ai_calls_total)} chamadas de IA até agora`
        }
      />
    </div>
  );
}
