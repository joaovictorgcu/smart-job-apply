import { Card, CardHeader, MetaRow, Note, Skeleton } from '@/components/primitives';
import { formatDateTime, formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { AutomationHealth } from '@/types/api';

import { HealthPill } from './HealthStrip';

function duration(seconds: number | null): string {
  if (seconds === null) return '—';
  if (seconds < 90) return `${Math.round(seconds)} s`;
  if (seconds < 5400) return `${(seconds / 60).toFixed(1)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

export interface AutomationPanelProps {
  automation?: AutomationHealth;
  isLoading?: boolean;
  className?: string;
}

/**
 * "Saúde da automação".
 *
 * The verdict comes first and the numbers explain it — the reverse of a card
 * that lists seven counters and leaves the reading to the viewer. `reasons` is
 * the service's own justification for the verdict, printed verbatim so the
 * badge can be argued with.
 */
export function AutomationPanel({
  automation,
  isLoading = false,
  className,
}: AutomationPanelProps) {
  if (isLoading || !automation) {
    return (
      <Card className={className} aria-busy="true">
        <CardHeader title="Saúde da automação" />
        <div className="space-y-2 px-4 py-3.5">
          <Skeleton className="h-14" />
          <Skeleton className="h-24" />
        </div>
      </Card>
    );
  }

  const tone =
    automation.status === 'problem'
      ? 'danger'
      : automation.status === 'attention'
        ? 'warning'
        : 'neutral';

  return (
    <Card className={cn('flex min-h-0 flex-col', className)}>
      <CardHeader
        title="Saúde da automação"
        description="Buscas, preenchimentos e envios executados pelo motor."
        actions={<HealthPill status={automation.status} />}
      />

      <div className="space-y-3 px-4 py-3.5">
        <Note tone={tone}>
          <ul className="space-y-0.5">
            {automation.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </Note>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[
            { label: 'Hoje', value: automation.runs_today },
            { label: 'Concluídas', value: automation.completed },
            { label: 'Com erro', value: automation.failed },
            { label: 'Ativas agora', value: automation.active_runs },
          ].map((tile) => (
            <div
              key={tile.label}
              className="rounded-lg border border-line bg-surface-sunken px-3 py-2"
            >
              <p className="text-2xs uppercase tracking-wider text-content-subtle">{tile.label}</p>
              <p className="tabular mt-0.5 text-lg font-semibold text-content">
                {formatNumber(tile.value)}
              </p>
            </div>
          ))}
        </div>

        <dl className="divide-y divide-line/70">
          <MetaRow label="Última execução">
            {automation.last_run_at ? formatDateTime(automation.last_run_at) : 'Nenhuma ainda'}
          </MetaRow>
          <MetaRow label="Tempo médio de execução">
            {duration(automation.avg_duration_seconds)}
          </MetaRow>
          <MetaRow label="Próxima execução">
            {/* Not unknown — nonexistent. Nothing schedules runs, and a made-up
                timestamp would be the one number here that cannot be checked. */}
            <span className="text-content-subtle">
              Sem agendador: cada execução é iniciada por um usuário
            </span>
          </MetaRow>
          <MetaRow label="Bloqueadas por verificação">
            {formatNumber(automation.blocked)}
          </MetaRow>
        </dl>
      </div>
    </Card>
  );
}
