import { ArrowRight, ClipboardCheck, FileUp, Radio } from 'lucide-react';
import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { ActivityFeed } from '@/components/ActivityFeed';
import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader, PageHeader } from '@/components/primitives';
import { ScoreBadge } from '@/components/ScoreBadge';
import { ScoreChart } from '@/components/ScoreChart';
import { SessionStatusCard } from '@/components/SessionStatusCard';
import { StatsCards } from '@/components/StatsCards';
import { useApplications, useJobs, useMasterResume, useStats } from '@/hooks/useApi';
import { useRecentEvents } from '@/hooks/useEvents';
import { formatRelativeTime } from '@/lib/format';
import type { Job } from '@/types/api';

/** Applications carry only a job_id, so the job row is joined on the client. */
const JOB_JOIN_LIMIT = 200;

/**
 * An account with no resume yet.
 *
 * Everything the dashboard normally shows is derived from one — the counters
 * are zeroes, the queue is empty, the chart has no bars. Showing all of that to
 * someone who has not uploaded a CV is six empty cards where one instruction
 * belongs.
 */
function StartHere() {
  return (
    <div className="mx-auto w-full max-w-xl space-y-6 py-6">
      <div className="text-center">
        <span
          aria-hidden
          className="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-accent-500/40 bg-accent-500/10 text-accent-400"
        >
          <FileUp className="h-5 w-5" />
        </span>
        <h1 className="mt-3 text-xl leading-snug">Comece pelo seu currículo</h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-content-muted">
          Envie o PDF que você já usa. A gente lê, mostra o que encontrou para você conferir, e a
          partir daí encontra vagas e prepara cada candidatura.
        </p>
        <Link to="/onboarding" className="btn btn-primary mt-5">
          Enviar meu currículo
          <ArrowRight aria-hidden className="h-4 w-4" />
        </Link>
      </div>
    </div>
  );
}

export function Dashboard() {
  const { data: master, isLoading: masterLoading } = useMasterResume();
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

  const profileIsEmpty =
    master !== undefined &&
    master.experiences.length === 0 &&
    !master.headline &&
    !(master.resume_text ?? '').trim();

  if (masterLoading || profileIsEmpty) {
    return masterLoading ? <div className="skeleton h-64" aria-busy="true" /> : <StartHere />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Painel"
        description="A busca e a pontuação rodam sozinhas. Preencher um formulário e enviá-lo são dois passos separados e deliberados — o segundo é sempre seu."
        actions={
          <Link to="/searches" className="btn btn-primary">
            Rodar uma busca
            <ArrowRight aria-hidden className="h-4 w-4" />
          </Link>
        }
      />

      <StatsCards stats={stats} isLoading={statsLoading} />

      <div className="grid gap-4 xl:grid-cols-3">
        <SessionStatusCard className="xl:col-span-1" />

        <Card className="flex min-h-0 flex-col xl:col-span-2">
          <CardHeader
            title="Precisa da sua revisão"
            description="Formulários já preenchidos e pausados na etapa de revisão."
            actions={
              queue.length > 0 ? (
                <Link to="/applications?status=awaiting_review" className="btn btn-sm">
                  Ver todas
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
              title="Nada esperando por você"
              description="Quando a automação preenche uma candidatura, ela para aqui para a sua aprovação."
              action={
                <Link to="/jobs" className="btn">
                  Escolher vagas para preparar
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
                        {job?.title ?? `Candidatura #${application.id}`}
                      </p>
                      <p className="truncate text-xs text-content-subtle">
                        {job?.company ?? 'Empresa desconhecida'} ·{' '}
                        {formatRelativeTime(application.updated_at ?? application.created_at)}
                        {flagged > 0
                          ? ` · ${flagged} ${flagged === 1 ? 'resposta' : 'respostas'} a conferir`
                          : ''}
                      </p>
                    </div>
                    <Link
                      to={`/applications/${application.id}`}
                      className="btn btn-sm btn-primary shrink-0"
                    >
                      Revisar
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
          title="Atividade ao vivo"
          description="Os últimos eventos da automação."
          actions={
            <Link to="/activity" className="btn btn-sm">
              Log completo
            </Link>
          }
        />
        <div className="max-h-72">
          <ActivityFeed
            events={recentEvents}
            dense
            emptyTitle="Nenhuma atividade ainda"
            emptyDescription="Inicie uma sessão do navegador e rode uma busca para ver os eventos aparecerem."
          />
        </div>
      </Card>

      <p className="flex items-center justify-center gap-1.5 text-2xs text-content-subtle">
        <Radio aria-hidden className="h-3 w-3" />
        Automatizar o LinkedIn viola os Termos de Uso dele. Você usa esta ferramenta por sua conta e risco.
      </p>
    </div>
  );
}
