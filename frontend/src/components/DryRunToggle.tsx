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
        title: next.dry_run ? 'Dry run enabled' : 'Dry run disabled',
        description: next.dry_run
          ? 'Forms will be filled for review, but nothing will be submitted.'
          : 'Approved applications can now be submitted to LinkedIn.',
        variant: next.dry_run ? 'success' : 'warning',
      });
    },
    onError: (error) => toast.error('Could not change dry run', errorMessage(error)),
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
          {enabled ? 'Dry run' : 'Live mode'}
        </span>
        <Toggle
          label={enabled ? 'Dry run enabled — turn off to allow real submissions' : 'Dry run disabled — turn on to block submissions'}
          checked={enabled}
          tone="success"
          disabled={updateSettings.isPending}
          onChange={handleChange}
        />
      </div>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Turn off dry run?"
        description="This is the switch that allows real applications to leave your account."
        size="md"
        footer={
          <>
            <Button onClick={() => setConfirmOpen(false)}>Keep dry run on</Button>
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
              Turn off dry run
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-sm leading-relaxed text-content-muted">
          <p>
            With dry run on, the tool opens the Easy Apply form, fills it in and stops at the review
            step — the submit button is never clicked.
          </p>
          <p>
            With dry run off, an application can actually be sent to LinkedIn. Every submission
            still requires you to open the application and approve it individually; nothing is sent
            in bulk or in the background.
          </p>
          <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
            Automating LinkedIn violates LinkedIn&apos;s Terms of Service and can get your account
            restricted. Only leave dry run off while you are watching the run.
          </Note>
        </div>
      </Modal>
    </>
  );
}
