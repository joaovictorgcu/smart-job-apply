import {
  CheckCircle2,
  ClipboardCheck,
  ExternalLink,
  Info,
  PenLine,
  Quote,
  Save,
  ScanSearch,
  Send,
  Trash2,
  TriangleAlert,
  XCircle,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';

import {
  useDiscardApplication,
  useGenerateCoverLetter,
  useMarkApplied,
  useSettings,
  useSubmitApplication,
  useUpdateApplication,
} from '@/hooks/useApi';
import { applicationStatusLabel, badgeClass } from '@/lib/format';
import { cn, safeExternalUrl } from '@/lib/utils';
import { reviewApplication } from '@/services/applications';
import { errorMessage } from '@/services/client';
import type {
  ApplicationDetail,
  CoverageStatus,
  DraftReview,
  ReviewCategory,
  ScreeningAnswer,
} from '@/types/api';

import { KillSwitchButton } from './KillSwitchButton';
import { Modal } from './Modal';
import { Button, Card, CardHeader, Note, Textarea } from './primitives';
import { ScreeningAnswerEditor } from './ScreeningAnswerEditor';
import { SubmissionSummary } from './SubmissionSummary';
import { useToast } from './ToastProvider';

const SOFT_COVER_LETTER_LIMIT = 2000;

interface Draft {
  coverLetter: string;
  answers: ScreeningAnswer[];
}

/**
 * One line of the readiness checklist. `fail` blocks approval; `warn` is a fact
 * worth knowing that does not — an unscored job or a missing letter is still
 * submittable, an unconfirmed answer is not.
 */
interface ReadinessCheck {
  state: 'ok' | 'warn' | 'fail';
  label: string;
  detail?: string;
}

const CHECK_ICON: Record<ReadinessCheck['state'], typeof CheckCircle2> = {
  ok: CheckCircle2,
  warn: TriangleAlert,
  fail: XCircle,
};

const CHECK_ICON_CLASS: Record<ReadinessCheck['state'], string> = {
  ok: 'text-success',
  warn: 'text-warning',
  fail: 'text-danger',
};

const CHECK_SR_PREFIX: Record<ReadinessCheck['state'], string> = {
  ok: 'ok:',
  warn: 'atenção:',
  fail: 'pendente:',
};

const REVIEW_CATEGORY_LABELS: Record<ReviewCategory, string> = {
  missed_keywords: 'Palavras-chave ausentes',
  company_angle: 'Ângulo da empresa',
  reframing: 'Reenquadramento',
  tone: 'Tom',
};

const COVERAGE_LABELS: Record<CoverageStatus, string> = {
  covered: 'coberto',
  synonym_only: 'só como sinônimo',
  missing_have_it: 'você tem, mas não disse',
  missing_gap: 'lacuna real',
};

const COVERAGE_TONES: Record<CoverageStatus, 'success' | 'info' | 'warning' | 'neutral'> = {
  covered: 'success',
  synonym_only: 'info',
  missing_have_it: 'warning',
  missing_gap: 'neutral',
};

function draftFrom(application: ApplicationDetail): Draft {
  return {
    coverLetter: application.cover_letter ?? '',
    answers: application.screening_answers,
  };
}

export interface ApplicationReviewPanelProps {
  application: ApplicationDetail;
  className?: string;
}

/**
 * The human-approval surface.
 *
 * "Save changes" and "Approve & submit" are deliberately separate actions, and
 * submitting is gated behind a second confirmation that names the company and
 * role. It stays disabled while any answer is still flagged, while the backend
 * says the application needs a human, while edits are unsaved, and while dry run
 * is on — with the reason spelled out, never a mysteriously grey button.
 *
 * An application on the `external` channel has no such button at all: there is
 * no form here to send. Its pair of actions is "apply on the company's site"
 * (which just opens the posting) and "I already applied", which records the act
 * so the application joins the pipeline instead of evaporating. Same
 * confirmation idiom, opposite meaning — one sends, the other only writes down.
 */
export function ApplicationReviewPanel({ application, className }: ApplicationReviewPanelProps) {
  const toast = useToast();
  const { data: settings } = useSettings();
  const [draft, setDraft] = useState<Draft>(() => draftFrom(application));
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [appliedOpen, setAppliedOpen] = useState(false);
  const [appliedNote, setAppliedNote] = useState('');
  const [discardOpen, setDiscardOpen] = useState(false);

  // Server state wins whenever the application itself changes underneath us, but
  // a plain refetch of identical data must not wipe edits in progress — so the
  // draft resets during render only when the identity/version key moves.
  const syncKey = `${application.id}:${application.updated_at ?? ''}`;
  const [syncedKey, setSyncedKey] = useState(syncKey);
  if (syncKey !== syncedKey) {
    setSyncedKey(syncKey);
    setDraft(draftFrom(application));
  }

  const update = useUpdateApplication({
    onSuccess: () => toast.success('Alterações salvas'),
    onError: (error) => toast.error('Não foi possível salvar as suas alterações', errorMessage(error)),
  });

  const submit = useSubmitApplication({
    onSuccess: () => {
      setConfirmOpen(false);
      toast.success('Candidatura enviada', 'O LinkedIn a recebeu.');
    },
    onError: (error) => toast.error('Falha no envio', errorMessage(error)),
  });

  const markApplied = useMarkApplied({
    onSuccess: () => {
      setAppliedOpen(false);
      toast.success(
        'Candidatura registrada',
        'Ela entrou no funil e passa a contar nas estatísticas.',
      );
    },
    onError: (error) => toast.error('Não foi possível registrar', errorMessage(error)),
  });

  const discard = useDiscardApplication({
    onSuccess: () => {
      setDiscardOpen(false);
      toast.toast({ title: 'Candidatura descartada', variant: 'info' });
    },
    onError: (error) => toast.error('Não foi possível descartar', errorMessage(error)),
  });

  const generate = useGenerateCoverLetter({
    onSuccess: (result) => {
      setDraft((current) => ({ ...current, coverLetter: result.content }));
      toast.success('Carta de apresentação gerada', 'Revise e salve as suas alterações.');
    },
    onError: (error) => toast.error('Não foi possível gerar a carta de apresentação', errorMessage(error)),
  });

  const review = useMutation<DraftReview, Error, void>({
    mutationFn: () => reviewApplication(application.id),
    onError: (error) => toast.error('Não foi possível revisar', errorMessage(error)),
  });

  const applyEdit = (oldString: string, newString: string) => {
    setDraft((current) => {
      if (!current.coverLetter.includes(oldString)) {
        toast.warning(
          'Trecho não encontrado',
          'A carta mudou desde a revisão — aplique a sugestão manualmente.',
        );
        return current;
      }
      return { ...current, coverLetter: current.coverLetter.replace(oldString, newString) };
    });
  };

  const dryRun = settings?.dry_run ?? true;
  const isDirty = useMemo(() => {
    if (draft.coverLetter !== (application.cover_letter ?? '')) return true;
    return JSON.stringify(draft.answers) !== JSON.stringify(application.screening_answers);
  }, [draft, application.cover_letter, application.screening_answers]);

  const pendingReview = draft.answers.filter((answer) => answer.needs_review).length;
  // Two independent gates, deliberately not folded into one: `needs_review` is
  // the local draft's view of each answer, while `needs_human_input` is the
  // server's verdict on the application as a whole — the backend recomputes it
  // when the draft is saved, so ticking answers on screen does not clear it.
  const needsHuman = application.needs_human_input;
  const isReviewable = application.status === 'awaiting_review';
  const isBusy =
    update.isPending || submit.isPending || discard.isPending || markApplied.isPending;
  // No form on this side: the posting is answered on the company's own page.
  const isExternal = application.channel === 'external';

  // Content facts (warn) and hard gates (fail), in the order a reviewer scans them.
  const coverLetterReady = draft.coverLetter.trim().length > 0;
  const checks: ReadinessCheck[] = [
    application.job?.score != null
      ? { state: 'ok', label: `Vaga analisada — nota ${application.job.score}/100` }
      : {
          state: 'warn',
          label: 'Vaga ainda não comparada com o seu perfil',
          detail: 'Opcional — você ainda pode enviar.',
        },
    application.resume_filename
      ? { state: 'ok', label: `Currículo anexado (${application.resume_filename})` }
      : {
          state: 'warn',
          label: 'Nenhum currículo anexado ao formulário',
          detail: 'Confira na janela do navegador se a vaga exige um.',
        },
    coverLetterReady
      ? { state: 'ok', label: 'Carta de apresentação pronta' }
      : settings === undefined
        // Settings still loading: state the fact without guessing the preference.
        ? { state: 'warn', label: 'Sem carta de apresentação' }
        : settings.generate_cover_letter === false
          ? { state: 'ok', label: 'Carta de apresentação desativada em Configurações' }
          : {
              state: 'warn',
              label: 'Sem carta de apresentação',
              detail: 'Muitos formulários de Candidatura Simplificada não pedem uma.',
            },
    pendingReview === 0
      ? { state: 'ok', label: 'Todas as respostas confirmadas' }
      : {
          state: 'fail',
          label: `${pendingReview} ${pendingReview === 1 ? 'resposta precisa' : 'respostas precisam'} de revisão`,
          detail: 'Confirme cada resposta sinalizada acima.',
        },
    ...(needsHuman
      ? [
          {
            state: 'fail' as const,
            label: 'Revisão humana pendente',
            detail: 'A automação sinalizou esta candidatura ao preencher o formulário.',
          },
        ]
      : []),
    isDirty
      ? {
          state: 'fail',
          label: 'Edições não salvas',
          detail: 'Salve para o LinkedIn receber o que você vê aqui.',
        }
      : { state: 'ok', label: 'Edições salvas' },
  ];
  if (!isReviewable) {
    checks.unshift({
      state: 'fail',
      label: `Status "${applicationStatusLabel(application.status)}"`,
      detail: 'Só uma candidatura aguardando revisão pode ser enviada.',
    });
  }

  const ready = checks.every((check) => check.state !== 'fail');
  // A submitted or discarded application has no readiness to report — and an
  // external one has no submission for the checklist to be about.
  const isClosed = ['submitted', 'submitting', 'discarded'].includes(application.status);
  const showReadiness = !isClosed && !isExternal;

  // Same gate as before the checklist existed: dry run still blocks the click.
  const canSubmit =
    !isBusy && isReviewable && pendingReview === 0 && !needsHuman && !isDirty && !dryRun;
  // Recording is not sending, so none of the submission gates apply: dry run,
  // the daily cap and the answer flags all guard what the app sends to LinkedIn.
  // All that matters is that there is still an unrecorded application to record.
  const canMarkApplied = !isBusy && isReviewable;
  const jobTitle = application.job?.title ?? `vaga #${application.job_id}`;
  const company = application.job?.company ?? 'esta empresa';
  // The posting's own URL, and it is third-party input — see `safeExternalUrl`.
  const jobUrl = safeExternalUrl(application.job?.url);

  return (
    <div className={cn('space-y-4', className)}>
      {/* First, and above every editor: approving is a decision about the whole
          document, and scrolling through the parts is not the same as seeing
          it. Hidden once the decision has been made. */}
      {!isClosed ? <SubmissionSummary application={application} /> : null}

      <Card>
        <CardHeader
          title="Carta de apresentação"
          description="Edite à vontade — este texto exato é o que será colado no formulário."
          actions={
            <Button
              size="sm"
              loading={generate.isPending}
              disabled={isBusy}
              onClick={() => generate.mutate(application.job_id)}
              icon={<PenLine aria-hidden className="h-3.5 w-3.5" />}
            >
              Escrever carta
            </Button>
          }
        />
        <div className="card-body space-y-2">
          <label htmlFor="cover-letter" className="sr-only">
            Carta de apresentação
          </label>
          <Textarea
            id="cover-letter"
            rows={10}
            value={draft.coverLetter}
            disabled={isBusy}
            placeholder="Nenhuma carta de apresentação foi gerada para esta candidatura."
            onChange={(event) =>
              setDraft((current) => ({ ...current, coverLetter: event.target.value }))
            }
          />
          <p
            className={cn(
              'tabular text-2xs',
              draft.coverLetter.length > SOFT_COVER_LETTER_LIMIT
                ? 'text-warning'
                : 'text-content-subtle',
            )}
            aria-live="polite"
          >
            {draft.coverLetter.length.toLocaleString('pt-BR')} caracteres
            {draft.coverLetter.length > SOFT_COVER_LETTER_LIMIT
              ? ' — respostas longas costumam ser cortadas pelo LinkedIn'
              : ''}
          </p>
        </div>
      </Card>

      {/* Nothing read a form here, so there are no triage answers to show. */}
      {isExternal ? null : (
        <Card>
          <CardHeader
            title="Respostas de triagem"
            description={
              pendingReview > 0
                ? `${pendingReview} de ${draft.answers.length} ${pendingReview === 1 ? 'precisa' : 'precisam'} da sua atenção.`
                : 'Todas as respostas estão confirmadas.'
            }
          />
          <div className="card-body">
            <ScreeningAnswerEditor
              answers={draft.answers}
              disabled={isBusy}
              onChange={(answers) => setDraft((current) => ({ ...current, answers }))}
            />
          </div>
        </Card>
      )}

      <Card>
        <CardHeader
          title="Revisão da IA"
          description="Uma segunda passada, de contexto limpo, sobre a carta e as respostas — nada é aplicado sem você mandar."
          actions={
            <Button
              size="sm"
              loading={review.isPending}
              disabled={isBusy}
              onClick={() => review.mutate()}
              icon={<ScanSearch aria-hidden className="h-3.5 w-3.5" />}
            >
              {review.data ? 'Revisar de novo' : 'Pedir uma segunda leitura'}
            </Button>
          }
        />
        {review.data ? (
          <div className="card-body space-y-4">
            {review.data.summary ? (
              <Note tone="accent" icon={<Quote aria-hidden className="h-3.5 w-3.5" />}>
                {review.data.summary}
              </Note>
            ) : null}

            <div>
              <p className="text-2xs font-semibold uppercase tracking-wider text-content-subtle">
                Crítica
              </p>
              <ul className="mt-2 space-y-1.5">
                {review.data.critique.map((note) => (
                  <li key={note.category} className="text-xs leading-relaxed">
                    <span className="font-medium text-content">
                      {REVIEW_CATEGORY_LABELS[note.category] ?? note.category}:
                    </span>{' '}
                    <span className="text-content-muted">{note.note}</span>
                  </li>
                ))}
              </ul>
            </div>

            {review.data.coverage.length > 0 ? (
              <div>
                <p className="text-2xs font-semibold uppercase tracking-wider text-content-subtle">
                  Cobertura dos requisitos
                </p>
                <ul className="mt-2 space-y-1.5">
                  {review.data.coverage.map((row) => (
                    <li key={row.requirement} className="flex items-start gap-2 text-xs">
                      <span className={badgeClass(COVERAGE_TONES[row.status] ?? 'neutral')}>
                        {COVERAGE_LABELS[row.status] ?? row.status}
                      </span>
                      <span className="min-w-0 leading-relaxed">
                        <span className="font-medium text-content">{row.requirement}</span>
                        {row.note ? (
                          <span className="text-content-subtle"> — {row.note}</span>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {review.data.edits.length > 0 ? (
              <div>
                <p className="text-2xs font-semibold uppercase tracking-wider text-content-subtle">
                  Edições sugeridas na carta
                </p>
                <ul className="mt-2 space-y-2.5">
                  {review.data.edits.map((edit) => (
                    <li
                      key={edit.old_string}
                      className="rounded-lg border border-line bg-surface-sunken px-3 py-2.5 text-xs"
                    >
                      <p className="leading-relaxed text-danger-strong line-through decoration-danger/50">
                        {edit.old_string}
                      </p>
                      <p className="mt-1 leading-relaxed text-success">{edit.new_string}</p>
                      <div className="mt-2 flex items-center justify-between gap-3">
                        <p className="text-2xs leading-relaxed text-content-subtle">{edit.reason}</p>
                        <Button
                          size="sm"
                          disabled={isBusy}
                          onClick={() => applyEdit(edit.old_string, edit.new_string)}
                        >
                          Aplicar
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-2xs text-content-subtle">
                  Aplicar altera só o rascunho — salve as alterações para persistir.
                </p>
              </div>
            ) : null}
          </div>
        ) : null}
      </Card>

      <Card>
        <div className="card-body space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="default"
              disabled={!isDirty || isBusy}
              loading={update.isPending}
              onClick={() =>
                update.mutate({
                  id: application.id,
                  payload: {
                    cover_letter: draft.coverLetter,
                    screening_answers: draft.answers,
                  },
                })
              }
              icon={<Save aria-hidden className="h-4 w-4" />}
            >
              Salvar alterações
            </Button>

            {isExternal ? (
              <>
                {jobUrl ? (
                  <a
                    href={jobUrl}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="btn btn-primary"
                  >
                    <ExternalLink aria-hidden className="h-4 w-4" />
                    Candidatar-se no site da empresa
                  </a>
                ) : null}
                <Button
                  disabled={!canMarkApplied}
                  onClick={() => setAppliedOpen(true)}
                  icon={<ClipboardCheck aria-hidden className="h-4 w-4" />}
                >
                  Já me candidatei
                </Button>
              </>
            ) : (
              <Button
                variant="primary"
                disabled={!canSubmit}
                onClick={() => setConfirmOpen(true)}
                icon={<Send aria-hidden className="h-4 w-4" />}
              >
                Aprovar e enviar
              </Button>
            )}

            {/* Reused rather than reimplemented: the same stop the shell and
                the dashboard offer. It belongs here too — this is where an
                operator is when they decide the automation should not carry on
                without them. */}
            <KillSwitchButton className="ml-auto" />

            <Button
              variant="ghost"
              className="text-danger hover:bg-danger/10 hover:text-danger"
              disabled={isBusy || application.status === 'discarded'}
              onClick={() => setDiscardOpen(true)}
              icon={<Trash2 aria-hidden className="h-4 w-4" />}
            >
              Descartar
            </Button>
          </div>

          {showReadiness ? (
            <div className="space-y-2.5 rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-2xs font-semibold uppercase tracking-wider text-content-subtle">
                  Prontidão da candidatura
                </p>
                <span className={badgeClass(!ready ? 'warning' : dryRun ? 'info' : 'success')}>
                  {!ready
                    ? 'Ainda não pronta'
                    : dryRun
                      ? 'Pronta — modo de teste ligado'
                      : 'Pronta para aprovação'}
                </span>
              </div>
              <ul className="space-y-1.5">
                {checks.map((check) => {
                  const Icon = CHECK_ICON[check.state];
                  return (
                    <li key={check.label} className="flex items-start gap-2 text-xs leading-relaxed">
                      <Icon
                        aria-hidden
                        className={cn('mt-0.5 h-3.5 w-3.5 shrink-0', CHECK_ICON_CLASS[check.state])}
                      />
                      <span className="min-w-0">
                        <span className="sr-only">{CHECK_SR_PREFIX[check.state]} </span>
                        <span
                          className={
                            check.state === 'fail' ? 'font-medium text-content' : 'text-content-muted'
                          }
                        >
                          {check.label}
                        </span>
                        {check.detail ? (
                          <span className="text-content-subtle"> — {check.detail}</span>
                        ) : null}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}

          {isClosed ? (
            <Note tone="neutral" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
              {application.status === 'submitted'
                ? isExternal
                  ? 'Você registrou esta candidatura como enviada no site da empresa. Ela já está no funil e nas estatísticas.'
                  : 'Esta candidatura já foi enviada — não há mais nada para aprovar aqui.'
                : application.status === 'submitting'
                  ? 'Enviando ao LinkedIn…'
                  : 'Esta candidatura foi descartada. Nada foi enviado.'}
            </Note>
          ) : null}

          {isExternal && !isClosed ? (
            <Note tone="neutral" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
              Esta vaga é respondida no site da empresa — o app não envia nada por você, e nunca
              vai. Leve a carta acima (e o currículo adaptado) para lá e, quando terminar, use
              &ldquo;Já me candidatei&rdquo;: é o que faz esta candidatura entrar no funil e contar
              nas suas estatísticas.
            </Note>
          ) : null}

          {showReadiness && needsHuman ? (
            <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
              A automação marcou esta candidatura como precisando de um humano, então &ldquo;Aprovar
              e enviar&rdquo; fica bloqueado — não há como ignorar. Confira a carta e as respostas
              acima e salve as alterações: o servidor recalcula essa marcação a cada gravação, a
              partir das respostas que ainda estiverem sinalizadas.
            </Note>
          ) : null}

          {showReadiness && dryRun ? (
            <Note tone="neutral" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
              O modo de teste está ligado, então &ldquo;Aprovar e enviar&rdquo; fica bloqueado de
              propósito. Desligue em Configurações quando estiver pronto para enviar de verdade.
            </Note>
          ) : null}

          {showReadiness && ready && !dryRun ? (
            <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
              Aprovar vai realmente enviar esta candidatura ao LinkedIn. Não há como desfazer.
            </Note>
          ) : null}
        </div>
      </Card>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        size="md"
        title="Enviar esta candidatura?"
        description="Esta é a única ação do app que envia algo ao LinkedIn."
        footer={
          <>
            <Button onClick={() => setConfirmOpen(false)} disabled={submit.isPending}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              loading={submit.isPending}
              onClick={() => submit.mutate(application.id)}
            >
              Enviar para {company}
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-sm leading-relaxed text-content-muted">
          <div className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
            <p className="text-2xs uppercase tracking-wider text-content-subtle">Candidatando-se a</p>
            <p className="mt-1 font-semibold text-content">{jobTitle}</p>
            <p className="text-xs text-content-muted">{company}</p>
          </div>
          <p>
            A carta de apresentação salva e {draft.answers.length === 1 ? 'a' : 'as'}{' '}
            {draft.answers.length} {draft.answers.length === 1 ? 'resposta de triagem' : 'respostas de triagem'}{' '}
            serão enviadas exatamente como aparecem nesta página, e o formulário será enviado. Isto não
            pode ser desfeito.
          </p>
        </div>
      </Modal>

      <Modal
        open={appliedOpen}
        onClose={() => setAppliedOpen(false)}
        size="md"
        title="Registrar que você se candidatou?"
        description="Isto não envia nada — só anota aqui o que você já fez lá."
        footer={
          <>
            <Button onClick={() => setAppliedOpen(false)} disabled={markApplied.isPending}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              loading={markApplied.isPending}
              onClick={() =>
                markApplied.mutate({ id: application.id, note: appliedNote.trim() || null })
              }
            >
              Registrar candidatura
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-sm leading-relaxed text-content-muted">
          <div className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
            <p className="text-2xs uppercase tracking-wider text-content-subtle">Candidatura a</p>
            <p className="mt-1 font-semibold text-content">{jobTitle}</p>
            <p className="text-xs text-content-muted">{company}</p>
          </div>
          <p>
            A candidatura passa a &ldquo;enviada&rdquo;, entra no quadro do funil em
            &ldquo;Candidatado&rdquo; e começa a contar nas estatísticas. Registre só depois de ter
            enviado de verdade no site da empresa.
          </p>
          <div>
            <label htmlFor="applied-note" className="label">
              Observação (opcional)
            </label>
            <Textarea
              id="applied-note"
              rows={2}
              maxLength={500}
              value={appliedNote}
              disabled={markApplied.isPending}
              placeholder="Ex.: enviei pelo formulário da página de carreiras."
              onChange={(event) => setAppliedNote(event.target.value)}
            />
          </div>
        </div>
      </Modal>

      <Modal
        open={discardOpen}
        onClose={() => setDiscardOpen(false)}
        size="sm"
        title="Descartar esta candidatura?"
        description="O rascunho é fechado e a vaga fica sem candidatura. Nada é enviado."
        footer={
          <>
            <Button onClick={() => setDiscardOpen(false)} disabled={discard.isPending}>
              Manter
            </Button>
            <Button
              variant="danger"
              loading={discard.isPending}
              onClick={() => discard.mutate(application.id)}
            >
              Descartar
            </Button>
          </>
        }
      />
    </div>
  );
}
