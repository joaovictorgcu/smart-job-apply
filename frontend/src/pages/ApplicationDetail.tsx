import { ArrowLeft, Briefcase, CircleAlert, ExternalLink } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import { ApplicationReviewPanel } from '@/components/ApplicationReviewPanel';
import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader, MetaRow, Note, Skeleton } from '@/components/primitives';
import { ScoreBadge } from '@/components/ScoreBadge';
import { StatusBadge } from '@/components/StatusBadge';
import { useApplication } from '@/hooks/useApi';
import { badgeClass, formatDateTime, formatTime, humanizeSnakeCase } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { ApplicationEvent } from '@/types/api';

function Timeline({ events }: { events: ApplicationEvent[] }) {
  if (events.length === 0) {
    return (
      <EmptyState
        compact
        title="No events yet"
        description="Steps the automation took will be logged here."
      />
    );
  }

  return (
    <ol className="relative space-y-4 pl-5">
      <span aria-hidden className="absolute inset-y-1 left-[5px] w-px bg-line" />
      {events.map((event) => (
        <li key={event.id} className="relative">
          <span
            aria-hidden
            className={cn(
              'absolute -left-5 top-1 h-[9px] w-[9px] rounded-full ring-2 ring-surface-raised',
              event.is_error ? 'bg-danger' : 'bg-accent-500',
            )}
          />
          <div className="flex items-baseline justify-between gap-2">
            <p
              className={cn(
                'text-xs font-semibold',
                event.is_error ? 'text-danger' : 'text-content',
              )}
            >
              {humanizeSnakeCase(event.event_type)}
            </p>
            <time
              dateTime={event.created_at}
              className="tabular shrink-0 font-mono text-2xs text-content-subtle"
            >
              {formatTime(event.created_at)}
            </time>
          </div>
          {event.message ? (
            <p className="mt-0.5 break-words text-xs leading-relaxed text-content-muted">
              {event.message}
            </p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

export function ApplicationDetail() {
  const params = useParams<{ id: string }>();
  const applicationId = Number(params.id);
  const { data: application, isLoading, isError } = useApplication(applicationId);

  if (isLoading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-4 w-32" />
        <Card className="space-y-3 px-5 py-5">
          <Skeleton className="h-6 w-2/5" />
          <Skeleton className="h-4 w-1/4" />
        </Card>
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !application) {
    return (
      <Card>
        <EmptyState
          icon={CircleAlert}
          title="Application not found"
          description="It may have been discarded, or the link is out of date."
          action={
            <Link to="/applications" className="btn">
              Back to applications
            </Link>
          }
        />
      </Card>
    );
  }

  const job = application.job;
  const showSteps =
    application.total_steps !== null &&
    application.total_steps > 0 &&
    application.current_step !== null;

  return (
    <div className="space-y-4">
      <Link
        to="/applications"
        className="inline-flex items-center gap-1.5 text-xs font-medium text-content-muted hover:text-content"
      >
        <ArrowLeft aria-hidden className="h-3.5 w-3.5" />
        All applications
      </Link>

      <Card className="px-5 py-5">
        <div className="flex flex-wrap items-start gap-4">
          <ScoreBadge score={job?.score ?? null} size="lg" />

          <div className="min-w-0 flex-1">
            <h1 className="text-xl leading-snug">
              {job ? job.title : `Application #${application.id}`}
            </h1>
            <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-content-muted">
              <span>{job?.company ?? 'Company unknown'}</span>
              {job?.location ? <span>{job.location}</span> : null}
              {job ? (
                <Link
                  to={`/jobs/${job.id}`}
                  className="inline-flex items-center gap-1.5 text-accent-400 hover:underline"
                >
                  <Briefcase aria-hidden className="h-3.5 w-3.5" />
                  Job details
                </Link>
              ) : null}
              {job?.url ? (
                <a
                  href={job.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1.5 text-accent-400 hover:underline"
                >
                  <ExternalLink aria-hidden className="h-3.5 w-3.5" />
                  Posting
                </a>
              ) : null}
            </p>

            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <StatusBadge kind="application" status={application.status} />
              {application.was_dry_run ? (
                <span className={badgeClass('neutral')}>filled in dry run</span>
              ) : null}
              {showSteps ? (
                <span className={badgeClass('info')}>
                  step {application.current_step} of {application.total_steps}
                </span>
              ) : null}
              {application.resume_filename ? (
                <span className={badgeClass('neutral')}>{application.resume_filename}</span>
              ) : null}
            </div>
          </div>
        </div>

        {application.error_message ? (
          <Note tone="danger" className="mt-4" icon={<CircleAlert aria-hidden className="h-3.5 w-3.5" />}>
            {application.error_message}
          </Note>
        ) : null}

        {application.needs_human_input ? (
          <Note tone="warning" className="mt-3">
            The form asked something the automation could not answer on its own. Check the flagged
            answers below before approving.
          </Note>
        ) : null}
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <ApplicationReviewPanel application={application} className="lg:col-span-2" />

        <div className="space-y-4">
          <Card>
            <CardHeader title="Timeline" description="Everything that happened, oldest first." />
            <div className="card-body">
              <Timeline events={application.events} />
            </div>
          </Card>

          <Card>
            <CardHeader title="Details" />
            <div className="card-body">
              <dl className="divide-y divide-line">
                <MetaRow label="Created">{formatDateTime(application.created_at)}</MetaRow>
                <MetaRow label="Last update">{formatDateTime(application.updated_at)}</MetaRow>
                <MetaRow label="Approved">
                  {application.approved_at ? formatDateTime(application.approved_at) : '—'}
                </MetaRow>
                <MetaRow label="Submitted">
                  {application.submitted_at ? formatDateTime(application.submitted_at) : '—'}
                </MetaRow>
              </dl>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
