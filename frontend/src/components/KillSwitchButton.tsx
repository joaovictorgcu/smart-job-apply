import { OctagonX } from 'lucide-react';

import { useSessionStatus, useStopAutomation } from '@/hooks/useApi';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';

import { Button } from './primitives';
import { useToast } from './ToastProvider';

export interface KillSwitchButtonProps {
  className?: string;
  /** Renders the icon only; the accessible name is kept. */
  iconOnly?: boolean;
}

/**
 * Kill switch. Stopping is always safe, so it fires immediately without a
 * confirmation dialog — a second click of hesitation is the wrong default when
 * the browser is doing something the operator wants halted.
 */
export function KillSwitchButton({ className, iconOnly = false }: KillSwitchButtonProps) {
  const toast = useToast();
  const { data: session } = useSessionStatus();
  const stop = useStopAutomation({
    onSuccess: (message) =>
      toast.warning('Parada solicitada', message.detail || 'A execução vai parar no próximo ponto seguro.'),
    onError: (error) => toast.error('Não foi possível parar a execução', errorMessage(error)),
  });

  const isActive = Boolean(session?.active_run_id);

  // Nothing running, nothing to stop. It used to render disabled, which put a
  // dead control in the chrome of every screen — and a disabled button is not
  // reachable in an emergency anyway, so it bought no safety for the noise it
  // cost. Appearing the moment a run starts is both quieter and a clearer
  // signal than a button that is always there and almost always grey.
  if (!isActive && !stop.isPending) return null;

  return (
    <Button
      variant="danger"
      onClick={() => stop.mutate()}
      loading={stop.isPending}
      aria-label="Parar a automação agora"
      title="Parar a automação em execução agora"
      className={cn('animate-fade-in', className)}
      icon={<OctagonX aria-hidden className="h-4 w-4" />}
    >
      <span className={cn(iconOnly && 'sr-only')}>Parar</span>
    </Button>
  );
}
