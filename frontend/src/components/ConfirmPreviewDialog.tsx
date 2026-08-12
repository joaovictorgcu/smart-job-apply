import { CircleSlash, FlaskConical, ShieldCheck, TriangleAlert } from 'lucide-react';
import { useEffect, useState } from 'react';

import { formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { PreviewResponse } from '@/types/api';

import { Modal } from './Modal';
import { Button, Checkbox, Note, Skeleton } from './primitives';

function Metric({
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'neutral' | 'accent' | 'warning';
}) {
  return (
    <div
      className={cn(
        'rounded-lg border px-3 py-2.5',
        tone === 'accent'
          ? 'border-accent-500/40 bg-accent-500/[0.07]'
          : tone === 'warning'
            ? 'border-warning/40 bg-warning/[0.07]'
            : 'border-line bg-surface-sunken',
      )}
    >
      <p className="text-2xs uppercase tracking-wider text-content-subtle">{label}</p>
      <p
        className={cn(
          'tabular mt-1 text-xl font-semibold leading-none',
          tone === 'accent' ? 'text-accent-400' : tone === 'warning' ? 'text-warning' : 'text-content',
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-2xs leading-snug text-content-subtle">{hint}</p> : null}
    </div>
  );
}

export interface ConfirmPreviewDialogProps {
  open: boolean;
  onClose: () => void;
  preview: PreviewResponse | null;
  isLoading?: boolean;
  isSubmitting?: boolean;
  error?: string | null;
  onConfirm: () => void;
}

/**
 * The safety gate in front of form filling.
 *
 * Nothing here can submit an application — preparing always stops at the review
 * step. The dialog exists so the operator sees the exact volume, the quota and
 * every warning *before* a browser starts clicking, and has to tick an
 * acknowledgement rather than muscle-memory a primary button.
 */
export function ConfirmPreviewDialog({
  open,
  onClose,
  preview,
  isLoading = false,
  isSubmitting = false,
  error,
  onConfirm,
}: ConfirmPreviewDialogProps) {
  const [acknowledged, setAcknowledged] = useState(false);

  // Consent is per-dialog: never carry a tick over to the next batch.
  useEffect(() => {
    if (!open) setAcknowledged(false);
  }, [open]);

  const count = preview?.jobs_to_process ?? 0;
  const overQuota = preview !== null && count > preview.remaining_today;
  const canConfirm = Boolean(preview) && count > 0 && acknowledged && !isSubmitting;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title="Revise antes de preencher qualquer coisa"
      description="Este passo abre cada anúncio e preenche o formulário de Candidatura Simplificada. Enviar é uma ação separada que você faz por candidatura."
      footer={
        <>
          <Button onClick={onClose} disabled={isSubmitting}>
            Cancelar
          </Button>
          <Button variant="primary" disabled={!canConfirm} loading={isSubmitting} onClick={onConfirm}>
            {count > 0
              ? `Preencher ${count} ${count === 1 ? 'candidatura' : 'candidaturas'} para revisão — nada será enviado`
              : 'Nada para preencher'}
          </Button>
        </>
      }
    >
      {isLoading || !preview ? (
        <div className="space-y-3">
          <Skeleton className="h-16 w-full" />
          <div className="grid gap-3 sm:grid-cols-3">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
          <Skeleton className="h-12 w-full" />
        </div>
      ) : (
        <div className="space-y-4">
          {error ? (
            <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2.5 text-xs leading-relaxed text-danger-strong">
              {error}
            </div>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              label="Serão preenchidas"
              value={formatNumber(count)}
              hint="Formulários preenchidos e pausados para revisão"
              tone="accent"
            />
            <Metric
              label="Já candidatadas"
              value={formatNumber(preview.already_applied)}
              hint="Puladas — sem duplicatas"
            />
            <Metric
              label="Abaixo do limite"
              value={formatNumber(preview.below_threshold)}
              hint="Abaixo da sua nota mínima"
            />
            <Metric
              label="Cota restante hoje"
              value={`${formatNumber(preview.remaining_today)} / ${formatNumber(preview.daily_cap)}`}
              hint={overQuota ? 'Menos que o solicitado poderá ser enviado' : 'Envios restantes'}
              tone={overQuota ? 'warning' : 'neutral'}
            />
          </div>

          <div
            className={cn(
              'flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5',
              preview.dry_run
                ? 'border-success/40 bg-success/[0.07]'
                : 'border-warning/40 bg-warning/[0.07]',
            )}
          >
            {preview.dry_run ? (
              <FlaskConical aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-success" />
            ) : (
              <TriangleAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            )}
            <div className="min-w-0 text-xs leading-relaxed">
              <p
                className={cn(
                  'font-semibold',
                  preview.dry_run ? 'text-success' : 'text-warning-strong',
                )}
              >
                {preview.dry_run ? 'Modo de teste LIGADO' : 'Modo de teste DESLIGADO'}
              </p>
              <p className="text-content-muted">
                {preview.dry_run
                  ? 'Mesmo depois de você aprovar uma candidatura, o botão de enviar não será clicado. Desligue o modo de teste em Configurações quando estiver pronto para enviar de verdade.'
                  : 'As candidaturas que você aprovar explicitamente serão de fato enviadas ao LinkedIn. Este lote ainda apenas preenche formulários.'}
              </p>
            </div>
          </div>

          {overQuota ? (
            <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
              Você escolheu {formatNumber(count)} vagas, mas só restam{' '}
              {formatNumber(preview.remaining_today)} envios dentro do limite de hoje, que é de{' '}
              {formatNumber(preview.daily_cap)}. Os rascunhos extras vão esperar até amanhã.
            </Note>
          ) : null}

          {preview.warnings.length > 0 ? (
            <ul className="space-y-2">
              {preview.warnings.map((warning) => (
                <li key={warning}>
                  <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
                    {warning}
                  </Note>
                </li>
              ))}
            </ul>
          ) : null}

          {count === 0 ? (
            <Note tone="neutral" icon={<CircleSlash aria-hidden className="h-3.5 w-3.5" />}>
              Nada nesta seleção é elegível. Tudo que você escolheu já foi candidatado, está abaixo da
              sua nota mínima ou não é um anúncio de Candidatura Simplificada.
            </Note>
          ) : (
            <>
              <div className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
                <p className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-content-subtle">
                  <ShieldCheck aria-hidden className="h-3.5 w-3.5" />
                  O que acontece a seguir
                </p>
                <ol className="mt-2 list-decimal space-y-1 pl-4 text-xs leading-relaxed text-content-muted">
                  <li>Cada anúncio é aberto na janela do navegador em que você fez login.</li>
                  <li>O formulário de Candidatura Simplificada é preenchido com o seu perfil e o banco de respostas.</li>
                  <li>
                    A execução para na etapa de revisão e a candidatura aparece em{' '}
                    <span className="font-medium text-content">Aguardando revisão</span>.
                  </li>
                  <li>Você abre cada uma, edita e aprova individualmente — ou descarta.</li>
                </ol>
              </div>

              <Checkbox
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
                label={`Entendo que isto vai abrir e preencher ${count} ${
                  count === 1 ? 'candidatura' : 'candidaturas'
                } do LinkedIn e parar para a minha revisão.`}
                description="Automatizar o LinkedIn viola os Termos de Uso dele e é feito por sua conta e risco."
              />
            </>
          )}
        </div>
      )}
    </Modal>
  );
}
