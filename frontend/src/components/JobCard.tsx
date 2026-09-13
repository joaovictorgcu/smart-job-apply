import { Building2, ExternalLink, MapPin, Quote } from 'lucide-react';
import { Link } from 'react-router-dom';

import { badgeClass, formatRelativeTime, truncate } from '@/lib/format';
import { cn, safeExternalUrl } from '@/lib/utils';
import type { Job } from '@/types/api';

import { MatchSummary } from './MatchSummary';
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
  // The posting's URL comes from the portal, not from us — see `safeExternalUrl`.
  const jobUrl = safeExternalUrl(job.url);
  // Every job starts `discovered`, so that word on a card distinguishes it from
  // nothing. The states worth a badge are the ones a run or the user produced.
  const showsState = job.status !== 'discovered';
  // A posting already dealt with is still worth finding, and no longer worth
  // reading first. It recedes instead of leaving the list.
  const settled = job.status === 'applied' || job.status === 'skipped';

  return (
    <article
      className={cn(
        // No hover lift: only the title navigates, so raising the whole card
        // promised a click target that is not there.
        'card flex gap-3 px-4 py-3.5 transition-colors sm:gap-4 sm:px-5',
        settled && 'bg-surface-sunken/40 shadow-none',
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
            Selecionar {job.title} em {job.company}
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
          {jobUrl ? (
            <a
              href={jobUrl}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-content-subtle hover:text-accent-400 hover:underline"
            >
              <ExternalLink aria-hidden className="h-3.5 w-3.5" />
              LinkedIn
            </a>
          ) : null}
        </p>

        {/*
         * Only what distinguishes this posting from the one below it.
         *
         * There were five badges here, three of which said the same thing on
         * every card in the list: "Candidatura Simplificada" is true of nearly
         * all of them, the work model repeated the location line verbatim
         * ("Remote" above, "Remoto" here), and "Descoberta" is the state every
         * job starts in. A mark that never varies is not a signal, and a row of
         * identical pills reads as one stripe of colour rather than as four
         * separate facts.
         *
         * What is left either changes between rows or stops the user from
         * wasting a click: a state that is past discovery, a posting that can no
         * longer be applied to, a form that lives on the company's own site, and
         * a portal that is not the usual one.
         */}
        {showsState || job.is_stale || !job.easy_apply || job.source !== 'linkedin' ? (
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {showsState ? <StatusBadge kind="job" status={job.status} /> : null}
            {job.is_stale ? (
              <span className={badgeClass('warning')}>
                {job.expired_at ? 'anúncio saiu do ar' : 'prazo encerrado'}
              </span>
            ) : null}
            {!job.easy_apply ? (
              <span className={badgeClass('neutral')}>formulário no site da empresa</span>
            ) : null}
            {job.source !== 'linkedin' ? (
              <span className={badgeClass('neutral')}>{job.source}</span>
            ) : null}
          </div>
        ) : null}

        {/* Before the model's prose on purpose: which requirements you meet is
            checkable, and a sentence about the score is not. */}
        <MatchSummary recommendation={job.recommendation} compact className="mt-2.5" />

        {topReason ? (
          <p className="mt-2.5 flex items-start gap-1.5 text-xs leading-relaxed text-content-muted">
            <Quote aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-content-subtle" />
            <span>{truncate(topReason, 180)}</span>
          </p>
        ) : job.skip_reason ? (
          <p className="mt-2.5 text-xs leading-relaxed text-content-subtle">
            Pulada: {truncate(job.skip_reason, 160)}
          </p>
        ) : null}
      </div>
    </article>
  );
}
