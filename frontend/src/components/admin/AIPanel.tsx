import { Card, CardHeader, MetaRow, Note, Skeleton } from '@/components/primitives';
import { badgeClass, formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { AIHealth } from '@/types/api';

import { HealthPill } from './HealthStrip';

export interface AIPanelProps {
  ai?: AIHealth;
  isLoading?: boolean;
  className?: string;
}

/**
 * "Saúde da IA".
 *
 * Shows which provider is active, whether it is answering, and what it cost. The
 * provider *name* and the model only — the API never returns a key, and there is
 * no field here that could carry one.
 */
export function AIPanel({ ai, isLoading = false, className }: AIPanelProps) {
  if (isLoading || !ai) {
    return (
      <Card className={className} aria-busy="true">
        <CardHeader title="Saúde da IA" />
        <div className="space-y-2 px-4 py-3.5">
          <Skeleton className="h-14" />
          <Skeleton className="h-24" />
        </div>
      </Card>
    );
  }

  const tone = ai.status === 'problem' ? 'danger' : ai.status === 'attention' ? 'warning' : 'neutral';

  return (
    <Card className={cn('flex min-h-0 flex-col', className)}>
      <CardHeader
        title="Saúde da IA"
        description="Pontuação de vagas, cartas de apresentação e respostas de triagem."
        actions={<HealthPill status={ai.status} />}
      />

      <div className="space-y-3 px-4 py-3.5">
        <Note tone={tone}>
          <ul className="space-y-0.5">
            {ai.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </Note>

        <div className="flex flex-wrap items-center gap-2">
          <span className={badgeClass(ai.configured ? 'accent' : 'warning')}>
            Provider: {ai.provider}
          </span>
          <span className={badgeClass('neutral')}>{ai.model}</span>
          <span className={badgeClass(ai.configured ? 'success' : 'warning')}>
            {ai.configured ? 'Configurado' : 'Sem credencial'}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[
            { label: 'Chamadas', value: formatNumber(ai.calls) },
            { label: 'Concluídas', value: formatNumber(ai.succeeded) },
            { label: 'Com erro', value: formatNumber(ai.failed) },
            {
              label: 'Resposta média',
              value:
                ai.avg_latency_ms === null
                  ? '—'
                  : ai.avg_latency_ms >= 1000
                    ? `${(ai.avg_latency_ms / 1000).toFixed(1)} s`
                    : `${Math.round(ai.avg_latency_ms)} ms`,
            },
          ].map((tile) => (
            <div
              key={tile.label}
              className="rounded-lg border border-line bg-surface-sunken px-3 py-2"
            >
              <p className="text-2xs uppercase tracking-wider text-content-subtle">{tile.label}</p>
              <p className="tabular mt-0.5 text-lg font-semibold text-content">{tile.value}</p>
            </div>
          ))}
        </div>

        <dl className="divide-y divide-line/70">
          <MetaRow label="Tokens (entrada / saída)">
            {formatNumber(ai.tokens_input)} / {formatNumber(ai.tokens_output)}
          </MetaRow>
          <MetaRow label="Recusas do modelo">{formatNumber(ai.refusals)}</MetaRow>
          <MetaRow label="Custo estimado">
            {/* Null, not zero: only some providers price a call, and printing
                "US$ 0,00" for the others would read as "this was free". */}
            {ai.cost_usd === null ? (
              <span className="text-content-subtle">Este provider não informa custo</span>
            ) : (
              `US$ ${ai.cost_usd.toFixed(2)}`
            )}
          </MetaRow>
        </dl>
      </div>
    </Card>
  );
}
