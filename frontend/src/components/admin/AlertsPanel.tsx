import { ShieldCheck } from 'lucide-react';

import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader, Skeleton } from '@/components/primitives';
import { badgeClass } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { AdminAlert } from '@/types/api';

import { SEVERITY_ICON, SEVERITY_LABELS, SEVERITY_TONE } from './labels';

export interface AlertsPanelProps {
  alerts?: AdminAlert[];
  isLoading?: boolean;
  className?: string;
}

/**
 * Problems that crossed a real threshold.
 *
 * An empty list is the good outcome and says so explicitly. A panel that always
 * shows something is a panel nobody reads, so no alert is ever synthesised to
 * fill this card.
 */
export function AlertsPanel({ alerts, isLoading = false, className }: AlertsPanelProps) {
  if (isLoading || !alerts) {
    return (
      <Card className={className} aria-busy="true">
        <CardHeader title="Alertas" description="Problemas que pedem atenção agora." />
        <div className="space-y-2 px-4 py-3.5">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      </Card>
    );
  }

  return (
    <Card className={cn('flex min-h-0 flex-col', className)}>
      <CardHeader
        title="Alertas"
        description="Só o que cruzou um limite real. Nada é agendado nem inventado."
        actions={
          alerts.length > 0 ? (
            <span className={badgeClass('danger')}>{alerts.length}</span>
          ) : null
        }
      />

      {alerts.length === 0 ? (
        <EmptyState
          compact
          icon={ShieldCheck}
          title="Nenhum alerta"
          description="Nenhum indicador cruzou um limite no período selecionado."
        />
      ) : (
        <ul className="divide-y divide-line">
          {alerts.map((alert) => {
            const Icon = SEVERITY_ICON[alert.severity];
            const tone = SEVERITY_TONE[alert.severity];
            return (
              <li key={alert.key} className="flex gap-3 px-4 py-3">
                <Icon
                  aria-hidden
                  className={cn(
                    'mt-0.5 h-4 w-4 shrink-0',
                    tone === 'danger'
                      ? 'text-danger'
                      : tone === 'warning'
                        ? 'text-warning'
                        : 'text-info',
                  )}
                />
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-content">
                    {alert.title}
                    <span className={badgeClass(tone)}>{SEVERITY_LABELS[alert.severity]}</span>
                  </p>
                  <p className="mt-0.5 text-xs leading-relaxed text-content-muted">
                    {alert.detail}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
