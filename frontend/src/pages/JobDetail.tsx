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
import { CVTailorPanel } from '@/components/CVTailorPanel';
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
import type { GateName, ScoreDimensionName } from '@/types/api';

const GATE_LABELS: Record<GateName, string> = {
  eligibility: 'elegibilidade',
  language: 'idioma',
};

const DIMENSION_LABELS: Record<ScoreDimensionName, string> = {
  skills: 'Habilidades',
  experience: 'Experiência',
  seniority: 'Senioridade',
  education: 'Formação',
  location: 'Localização',
  language: 'Idioma',
};

/** Same colour ramp as the score badge, applied to a dimension bar. */
function cnBar(score: number): string {
  const tone =
    score >= 80 ? 'bg-success' : score >= 60 ? 'bg-accent-500' : score >= 40 ? 'bg-warning' : 'bg-danger';
  return `h-full rounded ${tone}`;
}

export function JobDetail() {
  const params = useParams<{ id: string }>();
  const jobId = Number(params.id);
  const toast = useToast();

  const { data: job, isLoading, isError } = useJob(jobId);
  const { data: session } = useSessionStatus();
  const [dialogOpen, setDialogOpen] = useState(false);

  const analyze = useAnalyzeJob({
    onSuccess: (updated) =>
      toast.success('Análise concluída', `A IA deu a esta vaga a nota ${updated.score ?? 0}/100.`),
    onError: (error) => toast.error('A análise falhou', errorMessage(error)),
  });

  const skip = useSkipJob({
    onSuccess: () => toast.toast({ title: 'Vaga pulada', variant: 'info' }),
    onError: (error) => toast.error('Não foi possível pular a vaga', errorMessage(error)),
  });

  const preview = usePreviewJobs();
  const prepare = usePrepareApplications({
    onSuccess: (run) => {
      setDialogOpen(false);
      toast.success(
        'Preenchendo a candidatura',
        `Execução #${run.id} iniciada. Ela vai parar na etapa de revisão.`,
      );
    },
    onError: (error) => toast.error('Não foi possível iniciar o preenchimento', errorMessage(error)),
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
          title="Vaga não encontrada"
          description="Ela pode ter sido removida, ou o link está desatualizado."
          action={
            <Link to="/jobs" className="btn">
              Voltar às vagas
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
        Todas as vagas
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
                  Abrir no LinkedIn
                </a>
              ) : null}
            </p>

            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <StatusBadge kind="job" status={job.status} />
              {job.easy_apply ? (
                <span className={badgeClass('accent')}>Candidatura Simplificada</span>
              ) : (
                <span className={badgeClass('neutral')}>Formulário externo</span>
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
                ? 'Pontuar esta vaga em relação ao seu perfil'
                : 'Nenhuma chave de API de IA configurada'
            }
            onClick={() => analyze.mutate(job.id)}
            icon={<Sparkles aria-hidden className="h-4 w-4" />}
          >
            {job.score === null ? 'Analisar com IA' : 'Analisar de novo'}
          </Button>

          <Button
            loading={skip.isPending}
            disabled={job.status === 'applied' || job.status === 'skipped'}
            onClick={() => skip.mutate(job.id)}
            icon={<SkipForward aria-hidden className="h-4 w-4" />}
          >
            Pular
          </Button>

          {job.application_id !== null ? (
            <Link to={`/applications/${job.application_id}`} className="btn btn-primary">
              <Send aria-hidden className="h-4 w-4" />
              Abrir candidatura
            </Link>
          ) : (
            <Button
              variant="primary"
              disabled={!canPrepare}
              title={
                canPrepare
                  ? 'Preencher o formulário de Candidatura Simplificada e parar para revisão'
                  : 'Só vagas de Candidatura Simplificada sem candidatura podem ser preparadas'
              }
              onClick={() => {
                setDialogOpen(true);
                preview.mutate({ job_ids: [job.id] });
              }}
              icon={<Wand2 aria-hidden className="h-4 w-4" />}
            >
              Preparar candidatura…
            </Button>
          )}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Descrição da vaga" description="Exatamente como foi extraída do anúncio." />
          <div className="card-body">
            {job.description ? (
              <div className="whitespace-pre-wrap text-sm leading-relaxed text-content-muted">
                {job.description}
              </div>
            ) : (
              <EmptyState
                compact
                title="Nenhuma descrição armazenada"
                description="O anúncio não tinha uma descrição legível, ou ela não foi obtida."
              />
            )}
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Veredito da IA"
              description={
                job.score === null ? 'Ainda não analisada.' : `Nota ${job.score} de 100.`
              }
            />
            <div className="card-body space-y-4">
              {job.score === null ? (
                <Note tone="neutral">
                  Rode a análise para ver como o seu perfil combina com este anúncio.
                </Note>
              ) : (
                <>
                  {job.score_gates.some((gate) => gate.status !== 'pass') ? (
                    <div className="space-y-1.5">
                      {job.score_gates
                        .filter((gate) => gate.status !== 'pass')
                        .map((gate) => (
                          <Note
                            key={gate.gate}
                            tone={gate.status === 'fail' ? 'danger' : 'warning'}
                            icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}
                          >
                            <span className="font-medium">
                              {gate.status === 'fail' ? 'Excluída' : 'Atenção'} —{' '}
                              {GATE_LABELS[gate.gate] ?? gate.gate}:
                            </span>{' '}
                            {gate.evidence}
                          </Note>
                        ))}
                    </div>
                  ) : null}

                  {job.score_breakdown.length > 0 ? (
                    <div>
                      <SectionLabel>Como a nota foi composta</SectionLabel>
                      <ul className="mt-2 space-y-2">
                        {job.score_breakdown.map((dimension) => (
                          <li key={dimension.dimension}>
                            <div className="flex items-center gap-2">
                              <span className="w-24 shrink-0 text-xs font-medium text-content-muted">
                                {DIMENSION_LABELS[dimension.dimension] ?? dimension.dimension}
                              </span>
                              <div className="h-2 flex-1 overflow-hidden rounded bg-surface-sunken">
                                <div
                                  className={cnBar(dimension.score)}
                                  style={{ width: `${dimension.score}%` }}
                                />
                              </div>
                              <span className="tabular w-8 shrink-0 text-right text-xs font-semibold text-content">
                                {dimension.score}
                              </span>
                              {dimension.weight === 'nice_to_have' ? (
                                <span className={badgeClass('neutral')}>desejável</span>
                              ) : null}
                            </div>
                            <p className="mt-0.5 pl-[6.5rem] text-2xs leading-relaxed text-content-subtle">
                              {dimension.evidence}
                            </p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {job.score_reasons.length > 0 ? (
                    <div>
                      <SectionLabel>Por que combina</SectionLabel>
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
                      <SectionLabel>Requisitos que você pode não atender</SectionLabel>
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
                <Note tone="neutral">Pulada: {job.skip_reason}</Note>
              ) : null}
            </div>
          </Card>

          <Card>
            <CardHeader title="Detalhes" />
            <div className="card-body">
              <dl className="divide-y divide-line">
                <MetaRow label="Publicada">{formatDate(job.posted_at)}</MetaRow>
                <MetaRow label="Vista pela primeira vez">{formatDate(job.created_at)}</MetaRow>
                <MetaRow label="Idioma">
                  {job.detected_language ? job.detected_language.toUpperCase() : '—'}
                </MetaRow>
                <MetaRow label="ID do LinkedIn">
                  <span className="font-mono text-xs">{job.external_id}</span>
                </MetaRow>
              </dl>
            </div>
          </Card>
        </div>
      </div>

      <CVTailorPanel jobId={job.id} aiConfigured={Boolean(session?.ai_configured)} />

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
