import { ArrowRight, ClipboardCheck, Radio } from 'lucide-react';
import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { ActivityFeed } from '@/components/ActivityFeed';
import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader, PageHeader } from '@/components/primitives';
import { ScoreBadge } from '@/components/ScoreBadge';
import { ScoreChart } from '@/components/ScoreChart';
import { SessionStatusCard } from '@/components/SessionStatusCard';
import { StatsCards } from '@/components/StatsCards';
import { StatusBadge } from '@/components/StatusBadge';
import { useApplications, useJobs, useStats } from '@/hooks/useApi';
import { useRecentEvents } from '@/hooks/useEvents';
import { formatRelativeTime } from '@/lib/format';
import type { Job } from '@/types/api';

/** Applications carry only a job_id, so the job row is joined on the client. */
const JOB_JOIN_LIMIT = 200;

export function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useStats();
  const { data: reviewQueue, isLoading: queueLoading } = useApplications({
    status: 'awaiting_review',
    limit: 6,
  });
  const { data: jobsPage } = useJobs({ limit: JOB_JOIN_LIMIT });
  const recentEvents = useRecentEvents(10);

  const jobByApplication = useMemo(() => {
    const map = new Map<number, Job>();
    for (const job of jobsPage?.items ?? []) {
      if (job.application_id !== null) map.set(job.application_id, job);
    }
    return map;
  }, [jobsPage]);

  const queue = reviewQueue?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Search and scoring run on their own. Filling a form and submitting it are two separate, deliberate steps — the second one is always yours."
        actions={
          <Link to="/searches" className="btn btn-primary">
            Run a search
            <ArrowRight aria-hidden className="h-4 w-4" />
          </Link>
        }
      />

      <StatsCards stats={stats} isLoading={statsLoading} />

      <div className="grid gap-4 xl:grid-cols-3">
        <SessionStatusCard className="xl:col-span-1" />

        <Card className="flex min-h-0 flex-col xl:col-span-2">
          <CardHeader
            title="Needs your review"
            description="Forms already filled and paused at the review step."
            actions={
              queue.length > 0 ? (
                <Link to="/applications?status=awaiting_review" className="btn btn-sm">
                  See all
                </Link>
              ) : null
            }
          />

          {queueLoading ? (
            <div className="card-body space-y-2.5" aria-busy="true">
              <div className="skeleton h-12" />
              <div className="skeleton h-12" />
              <div className="skeleton h-12" />
            </div>
          ) : queue.length === 0 ? (
            <EmptyState
              icon={ClipboardCheck}
              title="Nothing waiting on you"
              description="When the automation fills an application it stops here for your approval."
              action={
                <Link to="/jobs" className="btn">
                  Pick jobs to prepare
                </Link>
              }
            />
          ) : (
            <ul className="divide-y divide-line">
              {queue.map((application) => {
                const job = jobByApplication.get(application.id);
                const flagged = application.screening_answers.filter(
                  (answer) => answer.needs_review,
                ).length;

                return (
                  <li
                    key={application.id}
                    className="flex items-center gap-3 px-5 py-3 transition-colors duration-150 hover:bg-surface-overlay/50"
                  >
                    <ScoreBadge score={job?.score ?? null} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-content">
                        {job?.title ?? `Application #${application.id}`}
                      </p>
                      <p className="truncate text-xs text-content-subtle">
                        {job?.company ?? 'Company unknown'} ·{' '}
                        {formatRelativeTime(application.updated_at ?? application.created_at)}
                        {flagged > 0
                          ? ` · ${flagged} ${flagged === 1 ? 'answer' : 'answers'} to check`
                          : ''}
                      </p>
                    </div>
                    <Link
                      to={`/applications/${application.id}`}
                      className="btn btn-sm btn-primary shrink-0"
                    >
                      Review
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>

      <ScoreChart
        distribution={stats?.score_distribution ?? []}
        daily={stats?.applications_last_7_days ?? []}
        isLoading={statsLoading}
      />

      <Card className="flex min-h-0 flex-col">
        <CardHeader
          title="Live activity"
          description="The last few events from the automation."
          actions={
            <Link to="/activity" className="btn btn-sm">
              Full log
            </Link>
          }
        />
        <div className="max-h-72">
          <ActivityFeed
            events={recentEvents}
            dense
            emptyTitle="No activity yet"
            emptyDescription="Start a browser session and run a search to see events stream in."
          />
        </div>
      </Card>

      <p className="flex items-center justify-center gap-1.5 text-2xs text-content-subtle">
        <Radio aria-hidden className="h-3 w-3" />
        Automating LinkedIn violates its Terms of Service. You run this tool at your own risk.
      </p>
    </div>
  );
}
