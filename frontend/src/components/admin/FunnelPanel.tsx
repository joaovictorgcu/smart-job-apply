import { Filter } from 'lucide-react';

import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader, Skeleton } from '@/components/primitives';
import { formatNumber, formatPercent } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { FunnelStage } from '@/types/api';

import { FUNNEL_LABELS } from './labels';

export interface FunnelPanelProps {
  funnel?: FunnelStage[];
  isLoading?: boolean;
  className?: string;
}

/**
 * Where the flow narrows, from posting found to interview.
 *
 * Horizontal bars scaled against the first stage, so the drop-off is the shape
 * of the panel rather than a number to compute. Each stage counts events inside
 * the window, not the fate of one cohort — the caption says so, because a funnel
 * that quietly mixes the two invites the wrong conclusion.
 */
export function FunnelPanel({ funnel, isLoading = false, className }: FunnelPanelProps) {
  if (isLoading || !funnel) {
    return (
      <Card className={className} aria-busy="true">
        <CardHeader title="Funil de candidaturas" />
        <div className="space-y-2.5 px-4 py-3.5">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-9" />
          ))}
        </div>
      </Card>
    );
  }

  const first = funnel[0]?.count ?? 0;

  return (
    <Card className={cn('flex min-h-0 flex-col', className)}>
      <CardHeader
        title="Funil de candidaturas"
        description="Cada etapa conta o que aconteceu no período, não o destino de um mesmo grupo de vagas."
      />

      {first === 0 ? (
        <EmptyState
          compact
          icon={Filter}
          title="Nenhuma vaga encontrada neste período"
          description="O funil se preenche a partir da primeira busca com resultado."
        />
      ) : (
        <ol className="space-y-2.5 px-4 py-3.5">
          {funnel.map((stage, index) => {
            const share = first > 0 ? stage.count / first : 0;
            return (
              <li key={stage.key}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="truncate text-xs font-medium text-content">
                    {FUNNEL_LABELS[stage.key] ?? stage.key}
                  </span>
                  <span className="tabular shrink-0 text-xs text-content-muted">
                    {formatNumber(stage.count)}
                    {index > 0 && stage.conversion_from_previous !== null ? (
                      <span className="ml-2 text-content-subtle">
                        {formatPercent(stage.conversion_from_previous)} da etapa anterior
                      </span>
                    ) : null}
                  </span>
                </div>
                <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-sunken">
                  <div
                    className="h-full origin-left rounded-full bg-accent-500/80 animate-bar-in"
                    style={{ width: `${Math.max(share * 100, stage.count > 0 ? 2 : 0)}%` }}
                    role="img"
                    aria-label={`${FUNNEL_LABELS[stage.key] ?? stage.key}: ${stage.count}${
                      stage.conversion_from_start !== null
                        ? `, ${formatPercent(stage.conversion_from_start)} do topo do funil`
                        : ''
                    }`}
                  />
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
