/* eslint-disable react-refresh/only-export-components -- the filter shape and its defaults belong with the control */
import { RotateCcw, SlidersHorizontal } from 'lucide-react';

import { useSearches } from '@/hooks/useApi';
import { jobStatusLabel } from '@/lib/format';
import { cn } from '@/lib/utils';
import { JOB_STATUSES, type JobStatus } from '@/types/api';

import { Button, Card, Field, Select } from './primitives';

export type JobSort = 'score' | 'newest' | 'company';

export interface JobFiltersValue {
  status: JobStatus | 'all';
  minScore: number;
  searchId: number | 'all';
  sort: JobSort;
}

export const DEFAULT_JOB_FILTERS: JobFiltersValue = {
  status: 'all',
  minScore: 0,
  searchId: 'all',
  sort: 'score',
};

const SORT_LABEL: Record<JobSort, string> = {
  score: 'Highest score',
  newest: 'Most recent',
  company: 'Company A–Z',
};

export interface JobFiltersProps {
  value: JobFiltersValue;
  onChange: (next: JobFiltersValue) => void;
  className?: string;
}

export function JobFilters({ value, onChange, className }: JobFiltersProps) {
  const { data: searches } = useSearches();

  const isDefault =
    value.status === DEFAULT_JOB_FILTERS.status &&
    value.minScore === DEFAULT_JOB_FILTERS.minScore &&
    value.searchId === DEFAULT_JOB_FILTERS.searchId &&
    value.sort === DEFAULT_JOB_FILTERS.sort;

  const patch = (partial: Partial<JobFiltersValue>) => onChange({ ...value, ...partial });

  return (
    <Card className={cn('px-4 py-3.5 sm:px-5', className)}>
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-2xs font-semibold uppercase tracking-[0.1em] text-content-subtle">
          <SlidersHorizontal aria-hidden className="h-3.5 w-3.5" />
          Filters
        </p>
        {isDefault ? null : (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onChange(DEFAULT_JOB_FILTERS)}
            icon={<RotateCcw aria-hidden className="h-3.5 w-3.5" />}
          >
            Reset
          </Button>
        )}
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Field label="Status" htmlFor="job-filter-status">
          <Select
            id="job-filter-status"
            value={value.status}
            onChange={(event) =>
              patch({ status: event.target.value as JobFiltersValue['status'] })
            }
          >
            <option value="all">Any status</option>
            {JOB_STATUSES.map((status) => (
              <option key={status} value={status}>
                {jobStatusLabel(status)}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Saved search" htmlFor="job-filter-search">
          <Select
            id="job-filter-search"
            value={value.searchId === 'all' ? 'all' : String(value.searchId)}
            onChange={(event) =>
              patch({
                searchId: event.target.value === 'all' ? 'all' : Number(event.target.value),
              })
            }
          >
            <option value="all">Any search</option>
            {(searches ?? []).map((search) => (
              <option key={search.id} value={search.id}>
                {search.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Sort"
          htmlFor="job-filter-sort"
          hint="Sorts the jobs on this page."
        >
          <Select
            id="job-filter-sort"
            value={value.sort}
            onChange={(event) => patch({ sort: event.target.value as JobSort })}
          >
            {(Object.keys(SORT_LABEL) as JobSort[]).map((sort) => (
              <option key={sort} value={sort}>
                {SORT_LABEL[sort]}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label={
            <span className="flex w-full items-baseline justify-between gap-2">
              <span>Minimum score</span>
              <span className="tabular text-2xs font-semibold normal-case tracking-normal text-accent-400">
                {value.minScore}
              </span>
            </span>
          }
          htmlFor="job-filter-score"
        >
          <input
            id="job-filter-score"
            type="range"
            min={0}
            max={100}
            step={5}
            value={value.minScore}
            onChange={(event) => patch({ minScore: Number(event.target.value) })}
            aria-valuetext={`${value.minScore} out of 100`}
            className="h-9 w-full cursor-pointer accent-accent-500"
          />
        </Field>
      </div>
    </Card>
  );
}
