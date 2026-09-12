import { CircleCheck } from 'lucide-react';
import type { ReactNode } from 'react';

import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader, Skeleton } from '@/components/primitives';
import { badgeClass, formatTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { AdminErrorEntry } from '@/types/api';

import { ERROR_SOURCE_LABELS } from './labels';

const SOURCE_TONE: Record<string, 'danger' | 'warning' | 'info'> = {
  automation: 'warning',
  ai: 'info',
  application: 'danger',
};

export interface ErrorsPanelProps {
  errors?: AdminErrorEntry[];
  isLoading?: boolean;
  /** "Ver todos" — omitted on the page that already shows everything. */
  action?: ReactNode;
  className?: string;
}

/**
 * "Erros recentes", merged from the automation runs, the AI calls and the
 * application trails.
 *
 * One truncated line each. The columns these rows come from hold messages the
 * application wrote for a human; tracebacks go to the logs with `exc_info` and
 * are never persisted, so there is none here to leak.
 */
export function ErrorsPanel({
  errors,
  isLoading = false,
  action,
  className,
}: ErrorsPanelProps) {
  if (isLoading || !errors) {
    return (
      <Card className={className} aria-busy="true">
        <CardHeader title="Erros recentes" />
        <div className="space-y-2 px-4 py-3.5">
          {Array.from({ length: 3 }, (_, index) => (
            <Skeleton key={index} className="h-10" />
          ))}
        </div>
      </Card>
    );
  }

  return (
    <Card className={cn('flex min-h-0 flex-col', className)}>
      <CardHeader
        title="Erros recentes"
        description="Automação, IA e candidaturas, do mais recente para o mais antigo."
        actions={action}
      />

      {errors.length === 0 ? (
        <EmptyState
          compact
          icon={CircleCheck}
          title="Nenhum erro neste período"
          description="Execuções, chamadas de IA e candidaturas terminaram sem falhas registradas."
        />
      ) : (
        <ul className="divide-y divide-line">
          {errors.map((entry) => (
            <li key={entry.id} className="flex gap-3 px-4 py-2.5">
              <span className="tabular w-11 shrink-0 pt-0.5 text-xs text-content-subtle">
                {formatTime(entry.occurred_at)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2">
                  <span className={badgeClass(SOURCE_TONE[entry.source] ?? 'neutral')}>
                    {ERROR_SOURCE_LABELS[entry.source] ?? entry.source}
                  </span>
                  <span className="truncate text-sm text-content">{entry.summary}</span>
                </p>
                {entry.detail ? (
                  <p className="mt-0.5 truncate text-2xs text-content-subtle">{entry.detail}</p>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
