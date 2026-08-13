import { ArrowLeft, Briefcase, CircleAlert, ExternalLink } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import { ApplicationReviewPanel } from '@/components/ApplicationReviewPanel';
import { EmptyState } from '@/components/EmptyState';
import { InterviewPanel } from '@/components/InterviewPanel';
import { Card, CardHeader, MetaRow, Note, Skeleton } from '@/components/primitives';
import { ScoreBadge } from '@/components/ScoreBadge';
import { StatusBadge } from '@/components/StatusBadge';
import { useApplication } from '@/hooks/useApi';
import { badgeClass, enumLabel, formatDateTime, formatTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { ApplicationEvent } from '@/types/api';

function Timeline({ events }: { events: ApplicationEvent[] }) {
  if (events.length === 0) {
    return (
      <EmptyState
        compact
        title="Nenhum evento ainda"
        description="Os passos que a automação executou serão registrados aqui."
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
              {enumLabel(event.event_type)}
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
          title="Candidatura não encontrada"
          description="Ela pode ter sido descartada, ou o link está desatualizado."
          action={
            <Link to="/applications" className="btn">
              Voltar às candidaturas
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
        Todas as candidaturas
      </Link>

      <Card className="px-5 py-5">
        <div className="flex flex-wrap items-start gap-4">
          <ScoreBadge score={job?.score ?? null} size="lg" />

          <div className="min-w-0 flex-1">
            <h1 className="text-xl leading-snug">
              {job ? job.title : `Candidatura #${application.id}`}
            </h1>
            <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-content-muted">
              <span>{job?.company ?? 'Empresa desconhecida'}</span>
              {job?.location ? <span>{job.location}</span> : null}
              {job ? (
                <Link
                  to={`/jobs/${job.id}`}
                  className="inline-flex items-center gap-1.5 text-accent-400 hover:underline"
                >
                  <Briefcase aria-hidden className="h-3.5 w-3.5" />
                  Detalhes da vaga
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
                  Anúncio
                </a>
              ) : null}
            </p>

            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <StatusBadge kind="application" status={application.status} />
              {application.was_dry_run ? (
                <span className={badgeClass('neutral')}>preenchida em modo de teste</span>
              ) : null}
              {showSteps ? (
                <span className={badgeClass('info')}>
                  etapa {application.current_step} de {application.total_steps}
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
            O formulário perguntou algo que a automação não conseguiu responder sozinha. Confira as
            respostas sinalizadas abaixo antes de aprovar.
          </Note>
        ) : null}
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <ApplicationReviewPanel application={application} className="lg:col-span-2" />

        <div className="space-y-4">
          <InterviewPanel
            applicationId={application.id}
            enabled={application.status === 'submitted'}
          />

          <Card>
            <CardHeader title="Linha do tempo" description="Tudo que aconteceu, do mais antigo ao mais recente." />
            <div className="card-body">
              <Timeline events={application.events} />
            </div>
          </Card>

          <Card>
            <CardHeader title="Detalhes" />
            <div className="card-body">
              <dl className="divide-y divide-line">
                <MetaRow label="Criada">{formatDateTime(application.created_at)}</MetaRow>
                <MetaRow label="Última atualização">{formatDateTime(application.updated_at)}</MetaRow>
                <MetaRow label="Aprovada">
                  {application.approved_at ? formatDateTime(application.approved_at) : '—'}
                </MetaRow>
                <MetaRow label="Enviada">
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
