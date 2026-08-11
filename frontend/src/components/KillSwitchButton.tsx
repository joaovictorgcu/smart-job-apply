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
      toast.warning('Stop requested', message.detail || 'The run will halt at the next safe point.'),
    onError: (error) => toast.error('Could not stop the run', errorMessage(error)),
  });

  const isActive = Boolean(session?.active_run_id);

  return (
    <Button
      variant={isActive ? 'danger' : 'default'}
      onClick={() => stop.mutate()}
      disabled={!isActive}
      loading={stop.isPending}
      aria-label="Stop automation now"
      title={isActive ? 'Stop the running automation now' : 'No automation run is active'}
      className={cn(isActive && 'animate-fade-in', className)}
      icon={<OctagonX aria-hidden className="h-4 w-4" />}
    >
      <span className={cn(iconOnly && 'sr-only')}>Stop</span>
    </Button>
  );
}
