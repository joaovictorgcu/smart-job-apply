import { Building2, ExternalLink, MapPin, Sparkles, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';

import { badgeClass, formatRelativeTime, humanizeSnakeCase, truncate } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Job } from '@/types/api';

import { ScoreBadge } from './ScoreBadge';
import { StatusBadge } from './StatusBadge';

export interface JobCardProps {
  job: Job;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: (id: number) => void;
  className?: string;
}

export function JobCard({
  job,
  selectable = false,
  selected = false,
  onToggleSelect,
  className,
}: JobCardProps) {
  const topReason = job.score_reasons[0];
  const checkboxId = `job-select-${job.id}`;

  return (
    <article
      className={cn(
        'card card-hover flex gap-3 px-4 py-3.5 transition-colors sm:gap-4 sm:px-5',
        selected && 'border-accent-500/50 bg-accent-500/[0.05]',
        className,
      )}
    >
      {selectable ? (
        <div className="flex items-start pt-1">
          <input
            id={checkboxId}
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect?.(job.id)}
            className="h-4 w-4 cursor-pointer rounded border-line-strong bg-surface-sunken accent-accent-500"
          />
          <label htmlFor={checkboxId} className="sr-only">
            Select {job.title} at {job.company}
          </label>
        </div>
      ) : null}

      <ScoreBadge score={job.score} size="md" className="mt-0.5 shrink-0" />

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <h3 className="min-w-0 text-md font-semibold leading-snug">
            <Link
              to={`/jobs/${job.id}`}
              className="text-content hover:text-accent-400 hover:underline"
            >
              {job.title}
            </Link>
          </h3>
          <span className="shrink-0 whitespace-nowrap text-2xs text-content-subtle">
            {formatRelativeTime(job.posted_at ?? job.created_at)}
          </span>
        </div>

        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-content-muted">
          <span className="inline-flex min-w-0 items-center gap-1">
            <Building2 aria-hidden className="h-3.5 w-3.5 shrink-0 text-content-subtle" />
            <span className="truncate">{job.company}</span>
          </span>
          {job.location ? (
            <span className="inline-flex min-w-0 items-center gap-1">
              <MapPin aria-hidden className="h-3.5 w-3.5 shrink-0 text-content-subtle" />
              <span className="truncate">{job.location}</span>
            </span>
          ) : null}
          {job.url ? (
            <a
              href={job.url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-content-subtle hover:text-accent-400 hover:underline"
            >
              <ExternalLink aria-hidden className="h-3.5 w-3.5" />
              LinkedIn
            </a>
          ) : null}
        </p>

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <StatusBadge kind="job" status={job.status} />
          {job.easy_apply ? (
            <span className={badgeClass('accent')}>
              <Zap aria-hidden className="h-3 w-3" />
              Easy Apply
            </span>
          ) : (
            <span className={badgeClass('neutral')}>External form</span>
          )}
          {job.workplace_type ? (
            <span className={badgeClass('neutral')}>{humanizeSnakeCase(job.workplace_type)}</span>
          ) : null}
        </div>

        {topReason ? (
          <p className="mt-2.5 flex items-start gap-1.5 text-xs leading-relaxed text-content-muted">
            <Sparkles aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-400" />
            <span>{truncate(topReason, 180)}</span>
          </p>
        ) : job.skip_reason ? (
          <p className="mt-2.5 text-xs leading-relaxed text-content-subtle">
            Skipped: {truncate(job.skip_reason, 160)}
          </p>
        ) : null}
      </div>
    </article>
  );
}
