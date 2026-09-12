import { ArrowRight, ClipboardCheck, FileUp, Search, Send } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Card, Skeleton } from '@/components/primitives';
import { ScoreBadge } from '@/components/ScoreBadge';
import { SessionStatusCard } from '@/components/SessionStatusCard';
import {
  useApplications,
  useJobs,
  useMasterResume,
  useOutcomeStats,
  useStats,
} from '@/hooks/useApi';
import { useAuth } from '@/hooks/useAuth';
import { formatRelativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';

/** Enough rows to act on without turning the page into a list screen. */
const QUEUE_SIZE = 4;

function firstName(fullName: string | null | undefined, email: string | undefined): string | null {
  const name = (fullName ?? '').trim();
  if (name) return name.split(/\s+/)[0];
  const local = (email ?? '').split('@')[0];
  return local || null;
}

/**
 * An account with no resume yet.
 *
 * Everything the dashboard shows is derived from one — the counters are zeroes,
 * the queue is empty. Showing all of that to someone who has not uploaded a CV
 * is six empty cards where one instruction belongs.
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

/**
 * One thing waiting for the user, with the action attached to it.
 *
 * The card is the action: a count with a button somewhere else is two steps
 * where one belongs, and it is what turns a dashboard into a scoreboard.
 */
function TaskCard({
  icon: Icon,
  count,
  title,
  description,
  to,
  action,
  tone = 'accent',
  children,
}: {
  icon: LucideIcon;
  count: number;
  title: string;
  description: string;
  to: string;
  action: string;
  tone?: 'accent' | 'neutral';
  children?: React.ReactNode;
}) {
  return (
    <Card className={cn('px-5 py-4', tone === 'accent' && 'border-accent-500/40')}>
      <div className="flex flex-wrap items-start gap-3">
        <span
          aria-hidden
          className={cn(
            'grid h-10 w-10 shrink-0 place-items-center rounded-xl border',
            tone === 'accent'
              ? 'border-accent-500/40 bg-accent-500/10 text-accent-400'
              : 'border-line bg-surface-sunken text-content-subtle',
          )}
        >
          <Icon className="h-4 w-4" />
        </span>

        <div className="min-w-0 flex-1">
          <p className="text-md font-semibold leading-snug text-content">
            <span className="tabular">{count}</span> {title}
          </p>
          <p className="mt-0.5 text-sm text-content-muted">{description}</p>
        </div>

        <Link
          to={to}
          className={cn('btn shrink-0', tone === 'accent' && 'btn-primary')}
        >
          {action}
          <ArrowRight aria-hidden className="h-4 w-4" />
        </Link>
      </div>
      {children}
    </Card>
  );
}

function ProgressStrip({
  submitted,
  interviews,
  waiting,
}: {
  submitted: number;
  interviews: number;
  waiting: number;
}) {
  const entries = [
    { value: submitted, label: submitted === 1 ? 'enviada' : 'enviadas' },
    { value: interviews, label: interviews === 1 ? 'entrevista' : 'entrevistas' },
    { value: waiting, label: 'sem resposta ainda' },
  ];

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-1">
      {entries.map((entry) => (
        <p key={entry.label} className="text-sm text-content-muted">
          <span className="tabular font-semibold text-content">{entry.value}</span> {entry.label}
        </p>
      ))}
      <Link to="/pipeline" className="text-sm text-accent-400 hover:underline">
        Ver o funil
      </Link>
    </div>
  );
}

/**
 * "O que eu faço agora?" — and nothing else above the fold.
 *
 * This used to be a scoreboard: counters, a score-distribution chart and a live
 * log, none of which answer that question. What replaced them is a queue, in
 * the order the work actually arrives — applications waiting on a human first,
 * because they are the only thing that cannot proceed without one.
 *
 * The numbers stayed, but as a consequence rather than as the content: one
 * strip at the bottom, and the charts moved to the funnel screen, where a
 * chart is read to decide something.
 */
export function Dashboard() {
  const { user } = useAuth();
  const { data: master, isLoading: masterLoading } = useMasterResume();
  const { data: stats } = useStats();
  const { data: outcomes } = useOutcomeStats();
  const { data: reviewQueue, isLoading: queueLoading } = useApplications({
    status: 'awaiting_review',
    limit: QUEUE_SIZE,
  });
  const { data: readyJobs } = useJobs({ status: 'analyzed', limit: 20 });

  const profileIsEmpty =
    master !== undefined &&
    master.experiences.length === 0 &&
    !master.headline &&
    !(master.resume_text ?? '').trim();

  if (masterLoading) return <div className="skeleton h-64" aria-busy="true" />;
  if (profileIsEmpty) return <StartHere />;

  const queue = reviewQueue?.items ?? [];
  const waitingCount = reviewQueue?.total ?? 0;
  // Scored, kept, and not yet turned into an application. `skipped` jobs are a
  // different status, so this is already "worth your time" rather than "found".
  const preparable = (readyJobs?.items ?? []).filter((job) => job.application_id === null);
  const name = firstName(user?.full_name, user?.email);

  const submitted = outcomes?.total_submitted ?? 0;
  const interviews = outcomes?.interviews ?? 0;
  const ghosted = outcomes?.ghosted ?? 0;
  const nothingToDo = waitingCount === 0 && preparable.length === 0;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-5">
      <div>
        <h1 className="text-xl leading-snug">
          {name ? `Olá, ${name}.` : 'Olá.'}{' '}
          <span className="text-content-muted">O que você quer fazer hoje?</span>
        </h1>
      </div>

      {queueLoading ? (
        <Skeleton className="h-24 rounded-xl" />
      ) : waitingCount > 0 ? (
        <TaskCard
          icon={ClipboardCheck}
          count={waitingCount}
          title={waitingCount === 1 ? 'candidatura espera você' : 'candidaturas esperam você'}
          description="Já estão preenchidas e paradas. Nada sai sem a sua aprovação."
          to="/applications?status=awaiting_review"
          action="Revisar"
        >
          <ul className="mt-3 divide-y divide-line border-t border-line">
            {queue.map((application) => {
              const flagged = application.screening_answers.filter(
                (answer) => answer.needs_review,
              ).length;
              return (
                <li key={application.id} className="flex items-center gap-3 py-2.5">
                  <ScoreBadge score={application.job_score} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-content">
                      {application.job_title ?? `Candidatura #${application.id}`}
                    </p>
                    <p className="truncate text-xs text-content-subtle">
                      {application.job_company ?? 'Empresa desconhecida'} ·{' '}
                      {formatRelativeTime(application.updated_at ?? application.created_at)}
                      {flagged > 0
                        ? ` · ${flagged} ${flagged === 1 ? 'resposta a confirmar' : 'respostas a confirmar'}`
                        : ''}
                    </p>
                  </div>
                  <Link
                    to={`/applications/${application.id}`}
                    className="btn btn-sm shrink-0"
                  >
                    Abrir
                  </Link>
                </li>
              );
            })}
          </ul>
        </TaskCard>
      ) : null}

      {preparable.length > 0 ? (
        <TaskCard
          icon={Send}
          count={preparable.length}
          title={preparable.length === 1 ? 'vaga recomendada' : 'vagas recomendadas'}
          description="Analisadas e guardadas para você. Escolha quais preparar."
          to="/jobs?status=analyzed"
          action="Escolher"
          tone={waitingCount > 0 ? 'neutral' : 'accent'}
        />
      ) : null}

      <TaskCard
        icon={Search}
        count={stats?.jobs_total ?? 0}
        title={(stats?.jobs_total ?? 0) === 1 ? 'vaga encontrada até agora' : 'vagas encontradas até agora'}
        description="Rode uma busca para trazer anúncios novos."
        to="/searches"
        action="Encontrar vagas"
        tone={nothingToDo ? 'accent' : 'neutral'}
      />

      <ProgressStrip
        submitted={submitted}
        interviews={interviews}
        waiting={Math.max(0, submitted - interviews - ghosted)}
      />

      {/* Operational, not a task: it only needs reading when something is off,
          and it is the one place to start a browser session. */}
      <SessionStatusCard />

      <p className="px-1 text-2xs leading-relaxed text-content-subtle">
        Automatizar o LinkedIn viola os Termos de Uso dele. Você usa esta ferramenta por sua conta e
        risco.
      </p>
    </div>
  );
}
