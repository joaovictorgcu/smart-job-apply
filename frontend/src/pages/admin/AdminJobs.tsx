import { AlertOctagon, Briefcase } from 'lucide-react';

import { useAdminPeriod } from '@/components/admin/period';
import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader, PageHeader, SectionLabel, Skeleton } from '@/components/primitives';
import { useAdminJobInsights } from '@/hooks/useApi';
import { formatNumber, formatPercent } from '@/lib/format';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';
import type { AdminLabelCount } from '@/types/api';

/** A ranked list as bars, scaled against the biggest entry. */
function TopList({
  title,
  description,
  rows,
  isLoading,
  emptyLabel,
}: {
  title: string;
  description?: string;
  rows: AdminLabelCount[];
  isLoading: boolean;
  emptyLabel: string;
}) {
  const max = rows.reduce((highest, row) => Math.max(highest, row.count), 0);

  return (
    <Card>
      <CardHeader title={title} description={description} />
      <div className="px-4 py-3.5">
        {isLoading ? (
          <div className="space-y-2" aria-busy="true">
            {Array.from({ length: 5 }, (_, index) => (
              <Skeleton key={index} className="h-7" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <p className="py-4 text-center text-xs text-content-subtle">{emptyLabel}</p>
        ) : (
          <ol className="space-y-2">
            {rows.map((row) => (
              <li key={row.label}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="truncate text-xs text-content">{row.label}</span>
                  <span className="tabular shrink-0 text-xs text-content-muted">
                    {formatNumber(row.count)}
                  </span>
                </div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken">
                  <div
                    className="h-full rounded-full bg-accent-500/70"
                    style={{ width: `${max > 0 ? (row.count / max) * 100 : 0}%` }}
                  />
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Card>
  );
}

function Tile({
  label,
  value,
  hint,
  className,
}: {
  label: string;
  value: string;
  hint?: string;
  className?: string;
}) {
  return (
    <Card className={cn('px-4 py-3.5', className)}>
      <SectionLabel>{label}</SectionLabel>
      <p className="tabular mt-1.5 text-2xl font-semibold leading-none text-content">{value}</p>
      {hint ? <p className="mt-1.5 text-2xs text-content-subtle">{hint}</p> : null}
    </Card>
  );
}

/**
 * What the platform is finding.
 *
 * Everything is a grouped count except the technologies, which are extracted
 * from the postings' own text — the caption reports how many postings were read,
 * because that number is a sample, not a census.
 */
export function AdminJobs() {
  const { query } = useAdminPeriod();
  const { data, isLoading, isError, error } = useAdminJobInsights(query);

  if (isError) {
    return (
      <div className="space-y-5">
        <PageHeader title="Vagas" description="O que a plataforma encontrou no período." />
        <Card>
          <EmptyState
            icon={AlertOctagon}
            title="Não foi possível carregar a análise de vagas"
            description={errorMessage(error, 'A API não respondeu.')}
          />
        </Card>
      </div>
    );
  }

  if (!isLoading && data && data.total === 0) {
    return (
      <div className="space-y-5">
        <PageHeader title="Vagas" description="O que a plataforma encontrou no período." />
        <Card>
          <EmptyState
            icon={Briefcase}
            title="Nenhuma vaga encontrada neste período"
            description="Escolha um período maior, ou aguarde a próxima busca de algum usuário."
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Vagas"
        description="O que a plataforma encontrou no período, e o que ela recomendou."
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Tile
          label="Processadas"
          value={isLoading ? '—' : formatNumber(data?.total ?? 0)}
          hint="Vagas descobertas no período."
        />
        <Tile
          label="Recomendadas"
          value={isLoading ? '—' : formatNumber(data?.recommended ?? 0)}
          hint="Analisadas, na fila ou já candidatadas."
        />
        <Tile
          label="Descartadas"
          value={isLoading ? '—' : formatNumber(data?.discarded ?? 0)}
          hint="Puladas por nota baixa ou decisão do usuário."
        />
        <Tile
          label="Nota média"
          value={
            isLoading
              ? '—'
              : data?.average_score === null || data?.average_score === undefined
                ? 'sem dados'
                : String(data.average_score)
          }
          hint="Média das notas de aderência atribuídas."
        />
        <Tile
          label="Com candidatura simplificada"
          value={
            isLoading
              ? '—'
              : data?.easy_apply_share === null || data?.easy_apply_share === undefined
                ? 'sem dados'
                : formatPercent(data.easy_apply_share)
          }
          hint="Parcela que a automação consegue preencher."
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <TopList
          title="Principais cargos"
          rows={data?.top_titles ?? []}
          isLoading={isLoading}
          emptyLabel="Nenhum cargo registrado neste período."
        />
        <TopList
          title="Principais tecnologias"
          description={
            data
              ? `Extraídas do texto de ${formatNumber(data.technologies_sampled)} vaga(s) — uma amostra das mais recentes, não o total.`
              : undefined
          }
          rows={data?.top_technologies ?? []}
          isLoading={isLoading}
          emptyLabel="Nenhuma tecnologia reconhecida no texto das vagas."
        />
        <TopList
          title="Principais localidades"
          rows={data?.top_locations ?? []}
          isLoading={isLoading}
          emptyLabel="Nenhuma localidade informada neste período."
        />
        <TopList
          title="Principais empresas"
          rows={data?.top_companies ?? []}
          isLoading={isLoading}
          emptyLabel="Nenhuma empresa registrada neste período."
        />
      </div>

      <TopList
        title="Origem das vagas"
        description="Qual portal descobriu cada vaga."
        rows={data?.top_sources ?? []}
        isLoading={isLoading}
        emptyLabel="Nenhuma origem registrada neste período."
      />
    </div>
  );
}
