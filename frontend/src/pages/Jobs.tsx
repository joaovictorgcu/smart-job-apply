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
        'Filling applications',
        `Run #${run.id} started. Each form stops at the review step — watch progress in Activity.`,
      );
    },
    onError: (error) => toast.error('Could not start filling', errorMessage(error)),
  });

  const items = useMemo(() => sortJobs(data?.items ?? [], filters.sort), [data, filters.sort]);
  const pageIds = items.map((job) => job.id);
  const allOnPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id));

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
        title="Jobs"
        description="Everything the searches found, with the AI's verdict. Selecting jobs here only fills forms for review — it never submits."
        actions={
          <Link to="/searches" className="btn">
            Run a search
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
            {allOnPageSelected ? 'Deselect this page' : 'Select this page'}
          </Button>
          <p className="tabular text-xs text-content-subtle">
            {isFetching ? 'Refreshing…' : `${formatNumber(data?.total ?? 0)} jobs match`}
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
            Create a search
          </Link>
        }
      />

      {data && data.total > PAGE_SIZE ? (
        <Pagination
          total={data.total}
          limit={data.limit}
          offset={data.offset}
          onOffsetChange={setOffset}
          unit="jobs"
        />
      ) : null}

      {selectedIds.length > 0 ? (
        <div className="sticky bottom-4 z-20 mx-auto w-full max-w-3xl">
          <Card className="flex flex-wrap items-center gap-3 border-accent-500/40 px-4 py-3 shadow-lifted">
            <p className="tabular text-sm font-medium text-content">
              {formatNumber(selectedIds.length)} selected
            </p>
            <Button size="sm" variant="ghost" onClick={() => setSelectedIds([])}>
              Clear
            </Button>
            <Button
              variant="primary"
              className="ml-auto"
              onClick={openPreview}
              icon={<Wand2 aria-hidden className="h-4 w-4" />}
            >
              Prepare applications…
            </Button>
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
