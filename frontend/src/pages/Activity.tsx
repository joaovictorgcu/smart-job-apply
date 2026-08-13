import { Copy, Eraser, History, RotateCw } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ActivityFeed } from '@/components/ActivityFeed';
import { EmptyState } from '@/components/EmptyState';
import { Button, Card, CardHeader, PageHeader, Skeleton } from '@/components/primitives';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/ToastProvider';
import { queryKeys, useRuns } from '@/hooks/useApi';
import { useEvents } from '@/hooks/useEvents';
import { resumeRun } from '@/services/automation';
import { errorMessage } from '@/services/client';
import { enumLabel, formatDuration, formatNumber, formatRelativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { EventLevel } from '@/types/events';

const LEVELS: Array<{ value: EventLevel; label: string; active: string }> = [
  { value: 'info', label: 'Info', active: 'border-info/45 bg-info/12 text-info' },
  { value: 'success', label: 'Sucesso', active: 'border-success/45 bg-success/12 text-success' },
  { value: 'warning', label: 'Aviso', active: 'border-warning/45 bg-warning/12 text-warning' },
  { value: 'error', label: 'Erro', active: 'border-danger/45 bg-danger/12 text-danger' },
];

export function Activity() {
  const toast = useToast();
  const client = useQueryClient();
  const { events, connected, clearEvents } = useEvents();
  const { data: runs, isLoading: runsLoading } = useRuns(8);

  const resume = useMutation({
    mutationFn: (runId: number) => resumeRun(runId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.runsAll() });
      toast.success('Execução retomada', 'O que já foi processado será pulado.');
    },
    onError: (error) => toast.error('Não foi possível retomar', errorMessage(error)),
  });
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
      toast.success('Log copiado', `${formatNumber(filtered.length)} linhas na sua área de transferência.`);
    } catch {
      toast.error('Não foi possível copiar', 'O seu navegador bloqueou o acesso à área de transferência.');
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Atividade"
        description="Tudo que a automação reporta, ao vivo. Nada aqui pode iniciar ou enviar coisa alguma — é uma janela somente leitura sobre a execução."
      />

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="flex min-h-0 flex-col xl:col-span-2">
          <div className="card-header flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span aria-hidden className={cn('live-dot', !connected && 'live-dot-idle')} />
              <h2 className="text-md">{connected ? 'Transmitindo' : 'Desconectado'}</h2>
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
                Copiar
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={clearEvents}
                disabled={events.length === 0}
                icon={<Eraser aria-hidden className="h-3.5 w-3.5" />}
              >
                Limpar
              </Button>
            </div>
          </div>

          <div className="min-h-0 flex-1">
            <ActivityFeed
              events={filtered}
              autoScroll
              className="h-[68vh]"
              emptyTitle={
                events.length === 0 ? 'Aguardando eventos' : 'Nenhum evento corresponde a esses níveis'
              }
              emptyDescription={
                events.length === 0
                  ? 'Inicie uma sessão do navegador e rode uma busca — cada passo aparece aqui conforme acontece.'
                  : 'Reative um nível acima para ver o restante do log.'
              }
            />
          </div>
        </Card>

        <Card className="flex min-h-0 flex-col">
          <CardHeader title="Execuções recentes" description="Buscas e lotes de preenchimento." />

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
              title="Nenhuma execução ainda"
              description="Rode uma busca salva para criar a primeira."
            />
          ) : (
            <ul className="divide-y divide-line">
              {(runs ?? []).map((run) => (
                <li key={run.id} className="px-5 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-content">
                      {enumLabel(run.kind)} · #{run.id}
                    </p>
                    <StatusBadge kind="run" status={run.status} />
                  </div>

                  <p className="tabular mt-1 text-2xs text-content-subtle">
                    {formatRelativeTime(run.started_at ?? run.created_at)} ·{' '}
                    {formatDuration(run.started_at, run.finished_at)}
                    {run.dry_run ? ' · modo de teste' : ''}
                  </p>

                  <p className="tabular mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-2xs text-content-muted">
                    <span>{formatNumber(run.jobs_found)} encontradas</span>
                    <span>{formatNumber(run.jobs_analyzed)} pontuadas</span>
                    <span>{formatNumber(run.applications_prepared)} preenchidas</span>
                    <span>{formatNumber(run.applications_submitted)} enviadas</span>
                  </p>

                  {run.blocked_reason ? (
                    <p className="mt-1.5 text-2xs leading-relaxed text-danger">
                      Bloqueada: {run.blocked_reason}
                    </p>
                  ) : null}
                  {run.error_message ? (
                    <p className="mt-1.5 text-2xs leading-relaxed text-danger">
                      {run.error_message}
                    </p>
                  ) : null}
                  {run.resumable ? (
                    <Button
                      size="sm"
                      className="mt-2"
                      loading={resume.isPending && resume.variables === run.id}
                      disabled={resume.isPending}
                      onClick={() => resume.mutate(run.id)}
                      icon={<RotateCw aria-hidden className="h-3.5 w-3.5" />}
                    >
                      Retomar de onde parou
                    </Button>
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
