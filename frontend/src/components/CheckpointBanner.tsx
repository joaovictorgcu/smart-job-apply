import { ExternalLink, ShieldAlert } from 'lucide-react';

import { useSessionStatus } from '@/hooks/useApi';
import { useEvents } from '@/hooks/useEvents';
import { cn } from '@/lib/utils';

import { Button } from './primitives';
import { useToast } from './ToastProvider';

/**
 * The security-checkpoint bar. It appears whenever the backend reports a blocked
 * session or an `automation.blocked` event arrives, and it never offers a way to
 * work around the verification: solving it is a human action, in the real
 * browser window, by design.
 */
export function CheckpointBanner({ className }: { className?: string }) {
  const toast = useToast();
  const { data: session, refetch, isFetching } = useSessionStatus();
  const { blockedEvent, clearBlocked } = useEvents();

  const blocked = Boolean(session?.blocked) || Boolean(blockedEvent);
  if (!blocked) return null;

  const reason = session?.blocked_reason ?? blockedEvent?.message ?? null;

  const recheck = async () => {
    const result = await refetch();
    if (result.data && !result.data.blocked) {
      clearBlocked();
      toast.success('Checkpoint cleared', 'The session is no longer blocked.');
    } else {
      toast.warning(
        'Still blocked',
        'LinkedIn is still showing the verification. Finish it in the browser window, then re-check.',
      );
    }
  };

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={cn('border-b border-danger/40 bg-danger/12', className)}
    >
      <div className="mx-auto flex max-w-[1600px] flex-col gap-3 px-4 py-3 sm:flex-row sm:items-start sm:gap-4 lg:px-8">
        <ShieldAlert
          aria-hidden
          className="h-5 w-5 shrink-0 text-danger sm:mt-0.5"
          strokeWidth={2}
        />

        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm font-semibold text-danger-strong">
            LinkedIn is asking for a security verification — automation is paused
          </p>
          <p className="text-xs leading-relaxed text-content-muted">
            Switch to the browser window the tool opened and complete the check yourself (CAPTCHA,
            code, or &ldquo;unusual activity&rdquo; prompt). This tool will never try to bypass a
            security challenge, so the run stays stopped until you confirm it is cleared.
          </p>
          {reason ? (
            <p className="truncate text-xs font-medium text-danger" title={reason}>
              {reason}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <a
            href="https://www.linkedin.com/feed/"
            target="_blank"
            rel="noreferrer noopener"
            className="btn btn-sm"
          >
            <ExternalLink aria-hidden className="h-3.5 w-3.5" />
            Open LinkedIn
          </a>
          <Button size="sm" variant="danger" loading={isFetching} onClick={recheck}>
            I solved it — re-check
          </Button>
        </div>
      </div>
    </div>
  );
}
