import { Radio } from 'lucide-react';
import type { ReactNode } from 'react';

import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader, Skeleton } from '@/components/primitives';
import { formatRelativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { AdminActivityEntry } from '@/types/api';

const LEVEL_DOT: Record<string, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-danger',
  info: 'bg-accent-500',
};

export interface ActivityTimelineProps {
  activity?: AdminActivityEntry[];
  isLoading?: boolean;
  action?: ReactNode;
  className?: string;
}

/**
 * "Atividade recente" as a timeline of notable events.
 *
 * Deliberately not a log: signups, finished runs and the application milestones,
 * and nothing else. Every technical event is already in the per-account activity
 * screen, where it belongs.
 */
export function ActivityTimeline({
  activity,
  isLoading = false,
  action,
  className,
}: ActivityTimelineProps) {
  if (isLoading || !activity) {
    return (
      <Card className={className} aria-busy="true">
        <CardHeader title="Atividade recente" />
        <div className="space-y-2 px-4 py-3.5">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-8" />
          ))}
        </div>
      </Card>
    );
  }

  return (
    <Card className={cn('flex min-h-0 flex-col', className)}>
      <CardHeader
        title="Atividade recente"
        description="Cadastros, execuções e marcos das candidaturas. Endereços de e-mail são mascarados."
        actions={action}
      />

      {activity.length === 0 ? (
        <EmptyState
          compact
          icon={Radio}
          title="Nenhuma atividade neste período"
          description="Cadastros e execuções aparecem aqui assim que acontecerem."
        />
      ) : (
        <ol className="px-4 py-3.5">
          {activity.map((entry, index) => (
            <li key={entry.id} className="relative flex gap-3 pb-3 last:pb-0">
              {index < activity.length - 1 ? (
                <span aria-hidden className="absolute left-[3px] top-3 h-full w-px bg-line" />
              ) : null}
              <span
                aria-hidden
                className={cn(
                  'relative mt-1.5 h-[7px] w-[7px] shrink-0 rounded-full',
                  LEVEL_DOT[entry.level] ?? LEVEL_DOT.info,
                )}
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm leading-snug text-content">{entry.summary}</p>
                <p className="text-2xs text-content-subtle">
                  {formatRelativeTime(entry.occurred_at)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
