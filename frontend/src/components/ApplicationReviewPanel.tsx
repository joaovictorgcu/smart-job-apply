import { Info, Save, Send, Sparkles, Trash2, TriangleAlert } from 'lucide-react';
import { useMemo, useState } from 'react';

import {
  useDiscardApplication,
  useGenerateCoverLetter,
  useSettings,
  useSubmitApplication,
  useUpdateApplication,
} from '@/hooks/useApi';
import { applicationStatusLabel } from '@/lib/format';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';
import type { ApplicationDetail, ScreeningAnswer } from '@/types/api';

import { Modal } from './Modal';
import { Button, Card, CardHeader, Note, Textarea } from './primitives';
import { ScreeningAnswerEditor } from './ScreeningAnswerEditor';
import { useToast } from './ToastProvider';

const SOFT_COVER_LETTER_LIMIT = 2000;

interface Draft {
  coverLetter: string;
  answers: ScreeningAnswer[];
}

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
 * role. It stays disabled while any answer is still flagged, while edits are
 * unsaved, and while dry run is on — with the reason spelled out, never a
 * mysteriously grey button.
 */
export function ApplicationReviewPanel({ application, className }: ApplicationReviewPanelProps) {
  const toast = useToast();
  const { data: settings } = useSettings();
  const [draft, setDraft] = useState<Draft>(() => draftFrom(application));
  const [confirmOpen, setConfirmOpen] = useState(false);
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

  const dryRun = settings?.dry_run ?? true;
  const isDirty = useMemo(() => {
    if (draft.coverLetter !== (application.cover_letter ?? '')) return true;
    return JSON.stringify(draft.answers) !== JSON.stringify(application.screening_answers);
  }, [draft, application.cover_letter, application.screening_answers]);

  const pendingReview = draft.answers.filter((answer) => answer.needs_review).length;
  const isReviewable = application.status === 'awaiting_review';
  const isBusy = update.isPending || submit.isPending || discard.isPending;

  const blockers: string[] = [];
  if (!isReviewable) {
    blockers.push(
      `Esta candidatura está "${applicationStatusLabel(application.status)}", não aguardando revisão, então não pode ser enviada.`,
    );
  }
  if (pendingReview > 0) {
    blockers.push(
      `${pendingReview} ${pendingReview === 1 ? 'resposta ainda precisa' : 'respostas ainda precisam'} da sua revisão. Confirme cada resposta sinalizada acima.`,
    );
  }
  if (isDirty) {
    blockers.push('Você tem edições não salvas. Salve primeiro para o LinkedIn receber o que você vê aqui.');
  }
  if (dryRun) {
    blockers.push(
      'O modo de teste está ligado, então o envio está bloqueado de propósito. Desligue em Configurações quando estiver pronto para enviar candidaturas de verdade.',
    );
  }

  const canSubmit = blockers.length === 0 && !isBusy;
  const jobTitle = application.job?.title ?? `vaga #${application.job_id}`;
  const company = application.job?.company ?? 'esta empresa';

  return (
    <div className={cn('space-y-4', className)}>
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
              icon={<Sparkles aria-hidden className="h-3.5 w-3.5" />}
            >
              Gerar com IA
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

            <Button
              variant="primary"
              disabled={!canSubmit}
              onClick={() => setConfirmOpen(true)}
              icon={<Send aria-hidden className="h-4 w-4" />}
            >
              Aprovar e enviar
            </Button>

            <Button
              variant="ghost"
              className="ml-auto text-danger hover:bg-danger/10 hover:text-danger"
              disabled={isBusy || application.status === 'discarded'}
              onClick={() => setDiscardOpen(true)}
              icon={<Trash2 aria-hidden className="h-4 w-4" />}
            >
              Descartar
            </Button>
          </div>

          {blockers.length > 0 ? (
            <div className="space-y-2">
              <p className="text-2xs font-semibold uppercase tracking-wider text-content-subtle">
                Por que &ldquo;Aprovar e enviar&rdquo; está desativado
              </p>
              <ul className="space-y-1.5">
                {blockers.map((blocker) => (
                  <li key={blocker}>
                    <Note tone="neutral" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
                      {blocker}
                    </Note>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
              Aprovar vai realmente enviar esta candidatura ao LinkedIn. Não há como desfazer.
            </Note>
          )}
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
