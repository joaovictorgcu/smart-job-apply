import {
  ArrowLeft,
  Building2,
  CircleAlert,
  ExternalLink,
  MapPin,
  Send,
  SkipForward,
  Sparkles,
  TriangleAlert,
  Wand2,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ConfirmPreviewDialog } from '@/components/ConfirmPreviewDialog';
import { EmptyState } from '@/components/EmptyState';
import {
  Button,
  Card,
  CardHeader,
  MetaRow,
  Note,
  SectionLabel,
  Skeleton,
} from '@/components/primitives';
import { ScoreBadge } from '@/components/ScoreBadge';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/ToastProvider';
import {
  useAnalyzeJob,
  useJob,
  usePrepareApplications,
  usePreviewJobs,
  useSessionStatus,
  useSkipJob,
} from '@/hooks/useApi';
import { badgeClass, formatDate, humanizeSnakeCase } from '@/lib/format';
import { errorMessage } from '@/services/client';

export function JobDetail() {
  const params = useParams<{ id: string }>();
  const jobId = Number(params.id);
  const toast = useToast();

  const { data: job, isLoading, isError } = useJob(jobId);
  const { data: session } = useSessionStatus();
  const [dialogOpen, setDialogOpen] = useState(false);

  const analyze = useAnalyzeJob({
    onSuccess: (updated) =>
      toast.success('Analysis complete', `The AI scored this job ${updated.score ?? 0}/100.`),
    onError: (error) => toast.error('Analysis failed', errorMessage(error)),
  });

  const skip = useSkipJob({
    onSuccess: () => toast.toast({ title: 'Job skipped', variant: 'info' }),
    onError: (error) => toast.error('Could not skip the job', errorMessage(error)),
  });

  const preview = usePreviewJobs();
  const prepare = usePrepareApplications({
    onSuccess: (run) => {
      setDialogOpen(false);
      toast.success(
        'Filling the application',
        `Run #${run.id} started. It will stop at the review step.`,
      );
    },
    onError: (error) => toast.error('Could not start filling', errorMessage(error)),
  });

  if (isLoading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-4 w-24" />
        <Card className="space-y-3 px-5 py-5">
          <Skeleton className="h-6 w-2/5" />
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-9 w-64" />
        </Card>
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !job) {
    return (
      <Card>
        <EmptyState
          icon={CircleAlert}
          title="Job not found"
          description="It may have been removed, or the link is out of date."
          action={
            <Link to="/jobs" className="btn">
              Back to jobs
            </Link>
          }
        />
      </Card>
    );
  }

  const canPrepare = job.easy_apply && job.status !== 'applied' && job.application_id === null;

  return (
    <div className="space-y-4">
      <Link
        to="/jobs"
        className="inline-flex items-center gap-1.5 text-xs font-medium text-content-muted hover:text-content"
      >
        <ArrowLeft aria-hidden className="h-3.5 w-3.5" />
        All jobs
      </Link>

      <Card className="px-5 py-5">
        <div className="flex flex-wrap items-start gap-4">
          <ScoreBadge score={job.score} size="lg" />

          <div className="min-w-0 flex-1">
            <h1 className="text-xl leading-snug">{job.title}</h1>
            <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-content-muted">
              <span className="inline-flex items-center gap-1.5">
                <Building2 aria-hidden className="h-4 w-4 text-content-subtle" />
                {job.company}
              </span>
              {job.location ? (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin aria-hidden className="h-4 w-4 text-content-subtle" />
                  {job.location}
                </span>
              ) : null}
              {job.url ? (
                <a
                  href={job.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1.5 text-accent-400 hover:underline"
                >
                  <ExternalLink aria-hidden className="h-4 w-4" />
                  Open on LinkedIn
                </a>
              ) : null}
            </p>

            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <StatusBadge kind="job" status={job.status} />
              {job.easy_apply ? (
                <span className={badgeClass('accent')}>Easy Apply</span>
              ) : (
                <span className={badgeClass('neutral')}>External form</span>
              )}
              {job.workplace_type ? (
                <span className={badgeClass('neutral')}>{humanizeSnakeCase(job.workplace_type)}</span>
              ) : null}
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-4">
          <Button
            loading={analyze.isPending}
            disabled={!session?.ai_configured}
            title={
              session?.ai_configured
                ? 'Score this job against your profile'
                : 'No AI API key is configured'
            }
            onClick={() => analyze.mutate(job.id)}
            icon={<Sparkles aria-hidden className="h-4 w-4" />}
          >
            {job.score === null ? 'Analyze with AI' : 'Re-analyze'}
          </Button>

          <Button
            loading={skip.isPending}
            disabled={job.status === 'applied' || job.status === 'skipped'}
            onClick={() => skip.mutate(job.id)}
            icon={<SkipForward aria-hidden className="h-4 w-4" />}
          >
            Skip
          </Button>

          {job.application_id !== null ? (
            <Link to={`/applications/${job.application_id}`} className="btn btn-primary">
              <Send aria-hidden className="h-4 w-4" />
              Open application
            </Link>
          ) : (
            <Button
              variant="primary"
              disabled={!canPrepare}
              title={
                canPrepare
                  ? 'Fill the Easy Apply form and stop for review'
                  : 'Only Easy Apply jobs without an application can be prepared'
              }
              onClick={() => {
                setDialogOpen(true);
                preview.mutate({ job_ids: [job.id] });
              }}
              icon={<Wand2 aria-hidden className="h-4 w-4" />}
            >
              Prepare application…
            </Button>
          )}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Job description" description="Exactly as scraped from the posting." />
          <div className="card-body">
            {job.description ? (
              <div className="whitespace-pre-wrap text-sm leading-relaxed text-content-muted">
                {job.description}
              </div>
            ) : (
              <EmptyState
                compact
                title="No description stored"
                description="The posting had no readable description, or it was not fetched."
              />
            )}
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="AI verdict"
              description={
                job.score === null ? 'Not analyzed yet.' : `Scored ${job.score} out of 100.`
              }
            />
            <div className="card-body space-y-4">
              {job.score === null ? (
                <Note tone="neutral">
                  Run the analysis to see how your profile matches this posting.
                </Note>
              ) : (
                <>
                  {job.score_reasons.length > 0 ? (
                    <div>
                      <SectionLabel>Why it fits</SectionLabel>
                      <ul className="mt-2 space-y-1.5">
                        {job.score_reasons.map((reason) => (
                          <li
                            key={reason}
                            className="flex items-start gap-2 text-xs leading-relaxed text-content-muted"
                          >
                            <Sparkles aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-400" />
                            <span>{reason}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {job.missing_requirements.length > 0 ? (
                    <div>
                      <SectionLabel>Requirements you may not meet</SectionLabel>
                      <ul className="mt-2 space-y-1.5">
                        {job.missing_requirements.map((requirement) => (
                          <li
                            key={requirement}
                            className="flex items-start gap-2 text-xs leading-relaxed text-content-muted"
                          >
                            <TriangleAlert aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                            <span>{requirement}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </>
              )}

              {job.skip_reason ? (
                <Note tone="neutral">Skipped: {job.skip_reason}</Note>
              ) : null}
            </div>
          </Card>

          <Card>
            <CardHeader title="Details" />
            <div className="card-body">
              <dl className="divide-y divide-line">
                <MetaRow label="Posted">{formatDate(job.posted_at)}</MetaRow>
                <MetaRow label="First seen">{formatDate(job.created_at)}</MetaRow>
                <MetaRow label="Language">
                  {job.detected_language ? job.detected_language.toUpperCase() : '—'}
                </MetaRow>
                <MetaRow label="LinkedIn ID">
                  <span className="font-mono text-xs">{job.external_id}</span>
                </MetaRow>
              </dl>
            </div>
          </Card>
        </div>
      </div>

      <ConfirmPreviewDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        preview={preview.data ?? null}
        isLoading={preview.isPending}
        isSubmitting={prepare.isPending}
        error={preview.error ? errorMessage(preview.error) : null}
        onConfirm={() => prepare.mutate({ job_ids: [job.id], confirmed: true })}
      />
    </div>
  );
}
