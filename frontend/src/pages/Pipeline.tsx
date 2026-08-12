import { CalendarCheck, Columns3, Percent, Send, Trophy } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { DragEvent, ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader, PageHeader, Select, Skeleton } from '@/components/primitives';
import { ScoreBadge } from '@/components/ScoreBadge';
import { useToast } from '@/components/ToastProvider';
import { useBoard, useOutcomeStats, useUpdateOutcome } from '@/hooks/useApi';
import { formatDate } from '@/lib/format';
import { errorMessage } from '@/services/client';
import type { ApplicationCard, ApplicationOutcome, OutcomeStats } from '@/types/api';

interface Column {
  outcome: ApplicationOutcome;
  label: string;
  text: string;
  dot: string;
}

const COLUMNS: Column[] = [
  { outcome: 'applied', label: 'Enviada', text: 'text-info', dot: 'bg-info' },
  { outcome: 'interview', label: 'Entrevista', text: 'text-accent-400', dot: 'bg-accent-500' },
  { outcome: 'offer', label: 'Proposta', text: 'text-success', dot: 'bg-success' },
  { outcome: 'rejected', label: 'Rejeitada', text: 'text-danger', dot: 'bg-danger' },
  { outcome: 'ghosted', label: 'Sem resposta', text: 'text-content-muted', dot: 'bg-content-subtle' },
];

function percent(rate: number | null): string {
  return rate === null ? '—' : `${Math.round(rate * 100)}%`;
}

export function Pipeline() {
  const toast = useToast();
  const { data: cards, isLoading } = useBoard();
  const { data: stats } = useOutcomeStats();
  const move = useUpdateOutcome({
    onError: (error) => toast.error('Não foi possível mover a candidatura', errorMessage(error)),
  });
  const [overColumn, setOverColumn] = useState<ApplicationOutcome | null>(null);

  const grouped = useMemo(() => {
    const byOutcome = new Map<ApplicationOutcome, ApplicationCard[]>(
      COLUMNS.map((column) => [column.outcome, []]),
    );
    for (const card of cards ?? []) {
      byOutcome.get(card.outcome)?.push(card);
    }
    return byOutcome;
  }, [cards]);

  function onDrop(outcome: ApplicationOutcome, event: DragEvent) {
    event.preventDefault();
    setOverColumn(null);
    const id = Number(event.dataTransfer.getData('text/plain'));
    const card = (cards ?? []).find((item) => item.id === id);
    if (card && card.outcome !== outcome) {
      move.mutate({ id, outcome });
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Funil"
        description="O que aconteceu depois que você se candidatou. Arraste um card, ou use o menu dele, para registrar o desfecho."
      />

      <OutcomeAnalytics
        stats={
          stats ?? {
            total_submitted: 0,
            interviews: 0,
            offers: 0,
            rejected: 0,
            ghosted: 0,
            interview_rate: null,
            by_outcome: [],
            interview_rate_by_band: [],
          }
        }
      />

      {isLoading ? (
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
          {COLUMNS.map((column) => (
            <Skeleton key={column.outcome} className="h-64 w-full rounded-xl" />
          ))}
        </div>
      ) : (cards ?? []).length === 0 ? (
        <Card>
          <EmptyState
            icon={Columns3}
            title="Nada enviado ainda"
            description="Quando você aprovar e enviar uma candidatura, ela aparece aqui para você acompanhar se vira entrevista."
            action={
              <Link to="/applications" className="btn">
                Ir para candidaturas
              </Link>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
          {COLUMNS.map((column) => {
            const items = grouped.get(column.outcome) ?? [];
            const active = overColumn === column.outcome;
            return (
              <section
                key={column.outcome}
                onDragOver={(event) => {
                  event.preventDefault();
                  setOverColumn(column.outcome);
                }}
                onDragLeave={() =>
                  setOverColumn((current) => (current === column.outcome ? null : current))
                }
                onDrop={(event) => onDrop(column.outcome, event)}
                className={`flex flex-col rounded-xl border bg-surface-sunken/40 p-2 transition-colors ${
                  active ? 'border-accent-500 bg-accent-500/5' : 'border-line'
                }`}
              >
                <header className="flex items-center justify-between px-1.5 py-1">
                  <span className="inline-flex items-center gap-1.5 text-sm font-medium text-content">
                    <span className={`h-2 w-2 rounded-full ${column.dot}`} aria-hidden />
                    {column.label}
                  </span>
                  <span className="text-2xs font-semibold text-content-subtle tabular">
                    {items.length}
                  </span>
                </header>

                <div className="flex flex-1 flex-col gap-2 pt-1">
                  {items.length === 0 ? (
                    <p className="px-1.5 py-6 text-center text-xs text-content-subtle">
                      Solte um card aqui
                    </p>
                  ) : (
                    items.map((card) => (
                      <article
                        key={card.id}
                        draggable
                        onDragStart={(event) =>
                          event.dataTransfer.setData('text/plain', String(card.id))
                        }
                        className="cursor-grab rounded-lg border border-line bg-surface p-2.5 shadow-sm active:cursor-grabbing"
                      >
                        <div className="flex items-start gap-2">
                          <ScoreBadge score={card.score} size="sm" />
                          <div className="min-w-0 flex-1">
                            <Link
                              to={`/applications/${card.id}`}
                              className="block truncate text-sm font-medium text-content hover:text-accent-400"
                              title={card.title}
                            >
                              {card.title}
                            </Link>
                            <p className="truncate text-xs text-content-muted">{card.company}</p>
                          </div>
                        </div>
                        <div className="mt-2 flex items-center justify-between gap-2">
                          <span className="text-2xs text-content-subtle">
                            {card.submitted_at ? `Enviada em ${formatDate(card.submitted_at)}` : ''}
                          </span>
                          <Select
                            aria-label={`Desfecho de ${card.title}`}
                            value={card.outcome}
                            onChange={(event) =>
                              move.mutate({
                                id: card.id,
                                outcome: event.target.value as ApplicationOutcome,
                              })
                            }
                            className="h-7 w-28 py-0 text-xs"
                          >
                            {COLUMNS.map((option) => (
                              <option key={option.outcome} value={option.outcome}>
                                {option.label}
                              </option>
                            ))}
                          </Select>
                        </div>
                      </article>
                    ))
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface AnalyticsProps {
  stats: OutcomeStats;
}

function OutcomeAnalytics({ stats }: AnalyticsProps) {
  const tiles: { label: string; value: ReactNode; icon: typeof Send; hint?: string }[] = [
    { label: 'Enviadas', value: stats.total_submitted, icon: Send },
    { label: 'Entrevistas', value: stats.interviews, icon: CalendarCheck, hint: 'entrevista ou proposta' },
    { label: 'Propostas', value: stats.offers, icon: Trophy },
    { label: 'Taxa de entrevista', value: percent(stats.interview_rate), icon: Percent },
  ];

  const bands = stats.interview_rate_by_band;
  const hasData = stats.total_submitted > 0;

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="grid grid-cols-2 gap-3 lg:col-span-2">
        {tiles.map((tile) => (
          <Card key={tile.label} className="px-4 py-3">
            <div className="flex items-center justify-between">
              <p className="text-2xs font-semibold uppercase tracking-wider text-content-subtle">
                {tile.label}
              </p>
              <tile.icon aria-hidden className="h-4 w-4 text-content-subtle" />
            </div>
            <p className="mt-1 text-3xl font-semibold leading-none text-content tabular">
              {tile.value}
            </p>
            {tile.hint ? (
              <p className="mt-1 text-2xs text-content-subtle">{tile.hint}</p>
            ) : null}
          </Card>
        ))}
      </div>

      <Card className="lg:col-span-3">
        <CardHeader
          title="Uma nota maior significa entrevista?"
          description="Taxa de entrevista por faixa de nota de aderência da IA, sobre as suas candidaturas enviadas."
        />
        <div className="card-body">
          {!hasData ? (
            <EmptyState
              compact
              title="Dados insuficientes ainda"
              description="Envie candidaturas e registre os desfechos para ver se a nota prevê entrevistas."
            />
          ) : (
            <div className="space-y-2.5">
              {bands.map((band) => (
                <div key={band.label} className="flex items-center gap-3">
                  <span className="w-14 shrink-0 text-xs font-medium text-content-muted tabular">
                    {band.label}
                  </span>
                  <div className="h-5 flex-1 overflow-hidden rounded bg-surface-sunken">
                    <div
                      className="h-full rounded bg-accent-500 transition-[width]"
                      style={{ width: `${Math.round((band.rate ?? 0) * 100)}%` }}
                    />
                  </div>
                  <span className="w-24 shrink-0 text-right text-xs text-content-muted tabular">
                    {percent(band.rate)}
                    <span className="ml-1 text-content-subtle">
                      ({band.interviews}/{band.total})
                    </span>
                  </span>
                </div>
              ))}
              <p className="pt-1 text-2xs text-content-subtle">
                "Entrevista" conta as candidaturas atualmente em Entrevista ou Proposta — um piso, já
                que uma rejeição após a entrevista é registrada como Rejeitada.
              </p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
