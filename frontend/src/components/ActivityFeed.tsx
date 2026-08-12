import { ArrowDownToLine, Radio } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { eventLevelTextClass, formatTime, humanizeSnakeCase } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { AppEvent } from '@/types/events';

import { EmptyState } from './EmptyState';
import { Button } from './primitives';

const LEVEL_DOT: Record<AppEvent['level'], string> = {
  info: 'bg-info',
  success: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-danger',
};

function EventRow({ event, dense }: { event: AppEvent; dense: boolean }) {
  const target =
    event.application_id !== null
      ? `/applications/${event.application_id}`
      : event.job_id !== null
        ? `/jobs/${event.job_id}`
        : null;

  return (
    <li
      className={cn(
        'flex items-start gap-2.5 px-3 transition-colors duration-150 hover:bg-surface-overlay/50',
        dense ? 'py-1.5' : 'py-2',
      )}
    >
      <span aria-hidden className={cn('mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full', LEVEL_DOT[event.level])} />
      <time
        dateTime={event.timestamp}
        className="tabular mt-px shrink-0 font-mono text-2xs text-content-subtle"
      >
        {formatTime(event.timestamp)}
      </time>
      <div className="min-w-0 flex-1">
        <p className={cn('break-words text-xs leading-relaxed', eventLevelTextClass(event.level))}>
          {event.message || humanizeSnakeCase(event.name)}
        </p>
        {!dense ? (
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-2xs text-content-subtle">
            <span className="font-mono">{event.name}</span>
            {event.run_id !== null ? <span>execução #{event.run_id}</span> : null}
            {target ? (
              <Link to={target} className="font-medium text-accent-400 hover:underline">
                {event.application_id !== null
                  ? `candidatura #${event.application_id}`
                  : `vaga #${event.job_id}`}
              </Link>
            ) : null}
          </p>
        ) : null}
      </div>
    </li>
  );
}

export interface ActivityFeedProps {
  /** Rendered in array order; the parent decides newest-first or chronological. */
  events: AppEvent[];
  /** Keeps the view pinned to the bottom until the user scrolls away from it. */
  autoScroll?: boolean;
  dense?: boolean;
  className?: string;
  emptyTitle?: string;
  emptyDescription?: string;
}

export function ActivityFeed({
  events,
  autoScroll = false,
  dense = false,
  className,
  emptyTitle = 'Nada aconteceu ainda',
  emptyDescription = 'Eventos ao vivo de buscas, pontuação e preenchimento aparecerão aqui.',
}: ActivityFeedProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);

  useEffect(() => {
    if (!autoScroll || !pinned) return;
    const container = containerRef.current;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
  }, [events.length, autoScroll, pinned]);

  const onScroll = () => {
    const container = containerRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    setPinned(distanceFromBottom < 48);
  };

  const jumpToLatest = () => {
    const container = containerRef.current;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
    setPinned(true);
  };

  if (events.length === 0) {
    return (
      <div className={className}>
        <EmptyState compact icon={Radio} title={emptyTitle} description={emptyDescription} />
      </div>
    );
  }

  return (
    <div className={cn('relative min-h-0', className)}>
      <div
        ref={containerRef}
        onScroll={autoScroll ? onScroll : undefined}
        className="scroll-area h-full"
      >
        <ul aria-live="polite" aria-relevant="additions" className="divide-y divide-line/60 py-1">
          {events.map((event, index) => (
            <EventRow key={`${event.timestamp}-${event.name}-${index}`} event={event} dense={dense} />
          ))}
        </ul>
      </div>

      {autoScroll && !pinned ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-2 flex justify-center">
          <Button
            size="sm"
            variant="primary"
            onClick={jumpToLatest}
            className="pointer-events-auto shadow-lifted"
            icon={<ArrowDownToLine aria-hidden className="h-3.5 w-3.5" />}
          >
            Rolagem automática pausada — ir para o mais recente
          </Button>
        </div>
      ) : null}
    </div>
  );
}
