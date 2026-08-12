import { FlaskConical, TriangleAlert } from 'lucide-react';
import { useState } from 'react';

import { useSettings, useUpdateSettings } from '@/hooks/useApi';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';

import { Modal } from './Modal';
import { Button, Note, Skeleton, Toggle } from './primitives';
import { useToast } from './ToastProvider';

export interface DryRunToggleProps {
  className?: string;
  /** Hides the text label; the switch keeps its accessible name. */
  compact?: boolean;
}

/**
 * Dry run is the outermost safety net: with it on, forms are filled but the
 * LinkedIn submit button is never clicked. Turning it *on* is instant; turning
 * it *off* always asks first, because it is the only direction that adds risk.
 */
export function DryRunToggle({ className, compact = false }: DryRunToggleProps) {
  const toast = useToast();
  const { data: settings, isLoading } = useSettings();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const updateSettings = useUpdateSettings({
    onSuccess: (next) => {
      toast.toast({
        title: next.dry_run ? 'Modo de teste ativado' : 'Modo de teste desativado',
        description: next.dry_run
          ? 'Os formulários serão preenchidos para revisão, mas nada será enviado.'
          : 'Candidaturas aprovadas agora podem ser enviadas ao LinkedIn.',
        variant: next.dry_run ? 'success' : 'warning',
      });
    },
    onError: (error) => toast.error('Não foi possível alterar o modo de teste', errorMessage(error)),
  });

  if (isLoading || !settings) {
    return <Skeleton className={cn('h-8 w-28', className)} />;
  }

  const enabled = settings.dry_run;

  const handleChange = (next: boolean) => {
    if (!next) {
      setConfirmOpen(true);
      return;
    }
    updateSettings.mutate({ dry_run: true });
  };

  return (
    <>
      <div
        className={cn(
          'flex items-center gap-2 rounded-lg border px-2.5 py-1.5 transition-colors duration-150',
          enabled ? 'border-line bg-surface-sunken' : 'border-warning/40 bg-warning/10',
          className,
        )}
      >
        {enabled ? (
          <FlaskConical aria-hidden className="h-3.5 w-3.5 shrink-0 text-content-subtle" />
        ) : (
          <TriangleAlert aria-hidden className="h-3.5 w-3.5 shrink-0 text-warning" />
        )}
        <span
          className={cn(
            'whitespace-nowrap text-xs font-medium',
            compact && 'sr-only',
            enabled ? 'text-content-muted' : 'text-warning-strong',
          )}
        >
          {enabled ? 'Modo de teste' : 'Modo real'}
        </span>
        <Toggle
          label={enabled ? 'Modo de teste ativado — desligue para permitir envios reais' : 'Modo de teste desativado — ligue para bloquear envios'}
          checked={enabled}
          tone="success"
          disabled={updateSettings.isPending}
          onChange={handleChange}
        />
      </div>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Desligar o modo de teste?"
        description="Este é o interruptor que permite candidaturas reais saírem da sua conta."
        size="md"
        footer={
          <>
            <Button onClick={() => setConfirmOpen(false)}>Manter o modo de teste ligado</Button>
            <Button
              variant="danger"
              loading={updateSettings.isPending}
              onClick={() =>
                updateSettings.mutate(
                  { dry_run: false },
                  { onSuccess: () => setConfirmOpen(false) },
                )
              }
            >
              Desligar o modo de teste
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-sm leading-relaxed text-content-muted">
          <p>
            Com o modo de teste ligado, a ferramenta abre o formulário de Candidatura Simplificada,
            preenche e para na etapa de revisão — o botão de enviar nunca é clicado.
          </p>
          <p>
            Com o modo de teste desligado, uma candidatura pode de fato ser enviada ao LinkedIn. Todo
            envio ainda exige que você abra a candidatura e a aprove individualmente; nada é enviado em
            massa nem em segundo plano.
          </p>
          <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
            Automatizar o LinkedIn viola os Termos de Uso do LinkedIn e pode fazer a sua conta ser
            restringida. Só deixe o modo de teste desligado enquanto estiver acompanhando a execução.
          </Note>
        </div>
      </Modal>
    </>
  );
}
