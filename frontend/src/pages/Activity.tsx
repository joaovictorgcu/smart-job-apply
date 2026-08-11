import { Copy, Eraser, History } from 'lucide-react';
import { useMemo, useState } from 'react';

import { ActivityFeed } from '@/components/ActivityFeed';
import { EmptyState } from '@/components/EmptyState';
import { Button, Card, CardHeader, PageHeader, Skeleton } from '@/components/primitives';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/ToastProvider';
import { useRuns } from '@/hooks/useApi';
import { useEvents } from '@/hooks/useEvents';
import { formatDuration, formatNumber, formatRelativeTime, humanizeSnakeCase } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { EventLevel } from '@/types/events';

const LEVELS: Array<{ value: EventLevel; label: string; active: string }> = [
  { value: 'info', label: 'Info', active: 'border-info/45 bg-info/12 text-info' },
  { value: 'success', label: 'Success', active: 'border-success/45 bg-success/12 text-success' },
  { value: 'warning', label: 'Warning', active: 'border-warning/45 bg-warning/12 text-warning' },
  { value: 'error', label: 'Error', active: 'border-danger/45 bg-danger/12 text-danger' },
];

export function Activity() {
  const toast = useToast();
  const { events, connected, clearEvents } = useEvents();
  const { data: runs, isLoading: runsLoading } = useRuns(8);
  const [enabled, setEnabled] = useState<EventLevel[]>(['info', 'success', 'warning', 'error']);

  const filtered = useMemo(
    () => events.filter((event) => enabled.includes(event.level)),
    [events, enabled],
  );

  const toggleLevel = (level: EventLevel) =>
    setEnabled((current) =>
      current.includes(level) ? current.filter((value) => value !== level) : [...current, level],
    );

  const copyLog = async () => {
    const text = filtered
      .map(
        (event) =>
          `${event.timestamp} [${event.level}] ${event.name}${event.message ? ` — ${event.message}` : ''}`,
      )
      .join('\n');

    try {
      await navigator.clipboard.writeText(text);
      toast.success('Log copied', `${formatNumber(filtered.length)} lines on your clipboard.`);
    } catch {
      toast.error('Could not copy', 'Your browser blocked clipboard access.');
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Activity"
        description="Everything the automation reports, live. Nothing here can start or submit anything — it is a read-only window on the run."
      />

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="flex min-h-0 flex-col xl:col-span-2">
          <div className="card-header flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span aria-hidden className={cn('live-dot', !connected && 'live-dot-idle')} />
              <h2 className="text-md">{connected ? 'Streaming' : 'Disconnected'}</h2>
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              {LEVELS.map((level) => {
                const on = enabled.includes(level.value);
                return (
                  <button
                    key={level.value}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleLevel(level.value)}
                    className={cn(
                      'rounded-full border px-2.5 py-0.5 text-xs font-medium transition duration-150 ease-snap',
                      on
                        ? level.active
                        : 'border-line bg-surface-sunken text-content-subtle hover:text-content',
                    )}
                  >
                    {level.label}
                  </button>
                );
              })}
            </div>

            <div className="ml-auto flex items-center gap-2">
              <Button
                size="sm"
                onClick={copyLog}
                disabled={filtered.length === 0}
                icon={<Copy aria-hidden className="h-3.5 w-3.5" />}
              >
                Copy
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={clearEvents}
                disabled={events.length === 0}
                icon={<Eraser aria-hidden className="h-3.5 w-3.5" />}
              >
                Clear
              </Button>
            </div>
          </div>

          <div className="min-h-0 flex-1">
            <ActivityFeed
              events={filtered}
              autoScroll
              className="h-[68vh]"
              emptyTitle={
                events.length === 0 ? 'Waiting for events' : 'No events match these levels'
              }
              emptyDescription={
                events.length === 0
                  ? 'Start a browser session and run a search — every step shows up here as it happens.'
                  : 'Re-enable a level above to see the rest of the log.'
              }
            />
          </div>
        </Card>

        <Card className="flex min-h-0 flex-col">
          <CardHeader title="Recent runs" description="Searches and form-filling batches." />

          {runsLoading ? (
            <div className="card-body space-y-2.5" aria-busy="true">
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
            </div>
          ) : (runs ?? []).length === 0 ? (
            <EmptyState
              compact
              icon={History}
              title="No runs yet"
              description="Run a saved search to create the first one."
            />
          ) : (
            <ul className="divide-y divide-line">
              {(runs ?? []).map((run) => (
                <li key={run.id} className="px-5 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-content">
                      {humanizeSnakeCase(run.kind)} · #{run.id}
                    </p>
                    <StatusBadge kind="run" status={run.status} />
                  </div>

                  <p className="tabular mt-1 text-2xs text-content-subtle">
                    {formatRelativeTime(run.started_at ?? run.created_at)} ·{' '}
                    {formatDuration(run.started_at, run.finished_at)}
                    {run.dry_run ? ' · dry run' : ''}
                  </p>

                  <p className="tabular mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-2xs text-content-muted">
                    <span>{formatNumber(run.jobs_found)} found</span>
                    <span>{formatNumber(run.jobs_analyzed)} scored</span>
                    <span>{formatNumber(run.applications_prepared)} filled</span>
                    <span>{formatNumber(run.applications_submitted)} submitted</span>
                  </p>

                  {run.blocked_reason ? (
                    <p className="mt-1.5 text-2xs leading-relaxed text-danger">
                      Blocked: {run.blocked_reason}
                    </p>
                  ) : null}
                  {run.error_message ? (
                    <p className="mt-1.5 text-2xs leading-relaxed text-danger">
                      {run.error_message}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
