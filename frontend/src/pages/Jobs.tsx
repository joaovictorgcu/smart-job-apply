import { CheckSquare, Square, Wand2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { ConfirmPreviewDialog } from '@/components/ConfirmPreviewDialog';
import { DEFAULT_JOB_FILTERS, JobFilters, type JobFiltersValue } from '@/components/JobFilters';
import { JobList } from '@/components/JobList';
import { Pagination } from '@/components/Pagination';
import { Button, Card, PageHeader } from '@/components/primitives';
import { useToast } from '@/components/ToastProvider';
import { useJobs, usePrepareApplications, usePreviewJobs } from '@/hooks/useApi';
import { formatNumber } from '@/lib/format';
import { errorMessage } from '@/services/client';
import type { Job } from '@/types/api';

const PAGE_SIZE = 20;
/** Mirrors the max_length on PrepareRequest.job_ids; more is rejected as a 422. */
const MAX_PREPARE_BATCH = 50;

function sortJobs(jobs: Job[], sort: JobFiltersValue['sort']): Job[] {
  const copy = [...jobs];
  switch (sort) {
    case 'score':
      return copy.sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
    case 'newest':
      return copy.sort(
        (a, b) =>
          new Date(b.posted_at ?? b.created_at ?? 0).getTime() -
          new Date(a.posted_at ?? a.created_at ?? 0).getTime(),
      );
    case 'company':
      return copy.sort((a, b) => a.company.localeCompare(b.company));
  }
}

export function Jobs() {
  const toast = useToast();
  const [filters, setFilters] = useState<JobFiltersValue>(DEFAULT_JOB_FILTERS);
  const [offset, setOffset] = useState(0);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);

  const { data, isLoading, isFetching } = useJobs({
    status: filters.status === 'all' ? undefined : filters.status,
    min_score: filters.minScore > 0 ? filters.minScore : undefined,
    search_id: filters.searchId === 'all' ? undefined : filters.searchId,
    limit: PAGE_SIZE,
    offset,
  });

  const preview = usePreviewJobs();
  const prepare = usePrepareApplications({
    onSuccess: (run) => {
      setDialogOpen(false);
      setSelectedIds([]);
      toast.success(
        'Preenchendo candidaturas',
        `Execução #${run.id} iniciada. Cada formulário para na etapa de revisão — acompanhe o progresso em Atividade.`,
      );
    },
    onError: (error) => toast.error('Não foi possível iniciar o preenchimento', errorMessage(error)),
  });

  const items = useMemo(() => sortJobs(data?.items ?? [], filters.sort), [data, filters.sort]);
  const pageIds = items.map((job) => job.id);
  const allOnPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id));
  const overBatchLimit = selectedIds.length > MAX_PREPARE_BATCH;

  const changeFilters = (next: JobFiltersValue) => {
    setFilters(next);
    setOffset(0);
  };

  const toggleSelect = (id: number) =>
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );

  const toggleAllOnPage = () =>
    setSelectedIds((current) =>
      allOnPageSelected
        ? current.filter((id) => !pageIds.includes(id))
        : Array.from(new Set([...current, ...pageIds])),
    );

  const openPreview = () => {
    setDialogOpen(true);
    preview.mutate({ job_ids: selectedIds });
  };

  const confirmPrepare = () => {
    const eligible = preview.data?.jobs.length ? preview.data.jobs.map((job) => job.id) : selectedIds;
    prepare.mutate({ job_ids: eligible, confirmed: true });
  };

  return (
    <div className="space-y-5 pb-24">
      <PageHeader
        title="Vagas"
        description="Tudo que as buscas encontraram, com o veredito da IA. Selecionar vagas aqui apenas preenche formulários para revisão — nunca envia."
        actions={
          <Link to="/searches" className="btn">
            Rodar uma busca
          </Link>
        }
      />

      <JobFilters value={filters} onChange={changeFilters} />

      {items.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button
            size="sm"
            variant="ghost"
            onClick={toggleAllOnPage}
            icon={
              allOnPageSelected ? (
                <CheckSquare aria-hidden className="h-3.5 w-3.5" />
              ) : (
                <Square aria-hidden className="h-3.5 w-3.5" />
              )
            }
          >
            {allOnPageSelected ? 'Desmarcar esta página' : 'Selecionar esta página'}
          </Button>
          <p className="tabular text-xs text-content-subtle">
            {isFetching ? 'Atualizando…' : `${formatNumber(data?.total ?? 0)} vagas encontradas`}
          </p>
        </div>
      ) : null}

      <JobList
        jobs={items}
        isLoading={isLoading}
        selectable
        selectedIds={selectedIds}
        onToggleSelect={toggleSelect}
        emptyAction={
          <Link to="/searches" className="btn btn-primary">
            Criar uma busca
          </Link>
        }
      />

      {data && data.total > PAGE_SIZE ? (
        <Pagination
          total={data.total}
          limit={data.limit}
          offset={data.offset}
          onOffsetChange={setOffset}
          unit="vagas"
        />
      ) : null}

      {selectedIds.length > 0 ? (
        <div className="sticky bottom-4 z-20 mx-auto w-full max-w-3xl">
          <Card className="flex flex-wrap items-center gap-3 border-accent-500/40 px-4 py-3 shadow-lifted">
            <p className="tabular text-sm font-medium text-content">
              {formatNumber(selectedIds.length)} selecionadas
            </p>
            <Button size="sm" variant="ghost" onClick={() => setSelectedIds([])}>
              Limpar
            </Button>
            <Button
              variant="primary"
              className="ml-auto"
              disabled={overBatchLimit}
              title={
                overBatchLimit
                  ? `Selecione no máximo ${MAX_PREPARE_BATCH} vagas por lote`
                  : 'Pré-visualize o que preencher esses formulários faria'
              }
              onClick={openPreview}
              icon={<Wand2 aria-hidden className="h-4 w-4" />}
            >
              Preparar candidaturas…
            </Button>

            {overBatchLimit ? (
              <p className="w-full text-xs leading-relaxed text-warning">
                Um lote é limitado a {MAX_PREPARE_BATCH} vagas. Desmarque{' '}
                {formatNumber(selectedIds.length - MAX_PREPARE_BATCH)} e rode o restante depois.
              </p>
            ) : null}
          </Card>
        </div>
      ) : null}

      <ConfirmPreviewDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        preview={preview.data ?? null}
        isLoading={preview.isPending}
        isSubmitting={prepare.isPending}
        error={preview.error ? errorMessage(preview.error) : null}
        onConfirm={confirmPrepare}
      />
    </div>
  );
}
