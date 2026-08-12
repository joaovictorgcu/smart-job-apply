import { Send } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { EmptyState } from '@/components/EmptyState';
import { Pagination } from '@/components/Pagination';
import { Card, Field, PageHeader, Select, Skeleton } from '@/components/primitives';
import { ScoreBadge } from '@/components/ScoreBadge';
import { StatusBadge } from '@/components/StatusBadge';
import { useApplications, useJobs } from '@/hooks/useApi';
import { applicationStatusLabel, badgeClass, formatDateTime, formatNumber } from '@/lib/format';
import { APPLICATION_STATUSES, type ApplicationStatus, type Job } from '@/types/api';

const PAGE_SIZE = 20;
const JOB_JOIN_LIMIT = 200;

function parseStatus(value: string | null): ApplicationStatus | 'all' {
  if (value && (APPLICATION_STATUSES as readonly string[]).includes(value)) {
    return value as ApplicationStatus;
  }
  return 'all';
}

export function Applications() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const status = parseStatus(searchParams.get('status'));

  const { data, isLoading } = useApplications({
    status: status === 'all' ? undefined : status,
    limit: PAGE_SIZE,
    offset,
  });
  const { data: jobsPage } = useJobs({ limit: JOB_JOIN_LIMIT });

  // Applications carry only a job_id, so the job columns are joined client-side.
  const jobByApplication = useMemo(() => {
    const map = new Map<number, Job>();
    for (const job of jobsPage?.items ?? []) {
      if (job.application_id !== null) map.set(job.application_id, job);
    }
    return map;
  }, [jobsPage]);

  const changeStatus = (value: string) => {
    setOffset(0);
    const next = new URLSearchParams(searchParams);
    if (value === 'all') {
      next.delete('status');
    } else {
      next.set('status', value);
    }
    setSearchParams(next, { replace: true });
  };

  const items = data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Candidaturas"
        description="Todo rascunho que a automação preencheu e toda candidatura que você aprovou."
      />

      <Card className="px-4 py-3.5 sm:px-5">
        <div className="grid gap-3 sm:max-w-xs">
          <Field label="Status" htmlFor="application-status">
            <Select
              id="application-status"
              value={status}
              onChange={(event) => changeStatus(event.target.value)}
            >
              <option value="all">Qualquer status</option>
              {APPLICATION_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {applicationStatusLabel(value)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Card>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="space-y-2 p-4" aria-busy="true">
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={Send}
            title={status === 'all' ? 'Nenhuma candidatura ainda' : 'Nada com este status'}
            description={
              status === 'all'
                ? 'Escolha vagas na página Vagas para preencher os formulários. Elas aparecem aqui aguardando a sua revisão.'
                : 'Tente outro filtro de status.'
            }
            action={
              <Link to="/jobs" className="btn btn-primary">
                Ir para vagas
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <caption className="sr-only">
                Candidaturas, {formatNumber(data?.total ?? 0)} no total
              </caption>
              <thead>
                <tr>
                  <th scope="col">Status</th>
                  <th scope="col">Nota</th>
                  <th scope="col">Vaga</th>
                  <th scope="col">Empresa</th>
                  <th scope="col">Última atualização</th>
                  <th scope="col">Enviada</th>
                  <th scope="col">
                    <span className="sr-only">Ações</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((application) => {
                  const job = jobByApplication.get(application.id);
                  const flagged = application.screening_answers.filter(
                    (answer) => answer.needs_review,
                  ).length;

                  return (
                    <tr key={application.id}>
                      <td>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <StatusBadge kind="application" status={application.status} />
                          {application.was_dry_run ? (
                            <span className={badgeClass('neutral')}>modo de teste</span>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <ScoreBadge score={job?.score ?? null} size="sm" />
                      </td>
                      <td className="max-w-[18rem]">
                        <Link
                          to={`/applications/${application.id}`}
                          className="block truncate font-medium text-content hover:text-accent-400 hover:underline"
                          title={job?.title ?? undefined}
                        >
                          {job?.title ?? `Candidatura #${application.id}`}
                        </Link>
                        {flagged > 0 ? (
                          <span className="text-2xs text-warning">
                            {flagged} {flagged === 1 ? 'resposta precisa' : 'respostas precisam'} de revisão
                          </span>
                        ) : null}
                      </td>
                      <td className="max-w-[12rem]">
                        <span className="block truncate">{job?.company ?? '—'}</span>
                      </td>
                      <td className="tabular whitespace-nowrap text-xs">
                        {formatDateTime(application.updated_at ?? application.created_at)}
                      </td>
                      <td className="tabular whitespace-nowrap text-xs">
                        {application.submitted_at ? formatDateTime(application.submitted_at) : '—'}
                      </td>
                      <td className="text-right">
                        <Link to={`/applications/${application.id}`} className="btn btn-sm">
                          {application.status === 'awaiting_review' ? 'Revisar' : 'Abrir'}
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {data && data.total > PAGE_SIZE ? (
        <Pagination
          total={data.total}
          limit={data.limit}
          offset={data.offset}
          onOffsetChange={setOffset}
          unit="candidaturas"
        />
      ) : null}
    </div>
  );
}
