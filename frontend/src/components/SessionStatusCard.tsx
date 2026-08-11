import { Bot, CheckCircle2, Circle, Info, Linkedin, MonitorPlay, Power } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { useSessionStatus, useStartSession, useStopSession } from '@/hooks/useApi';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';

import { Button, Card, CardHeader, Note, Skeleton } from './primitives';
import { useToast } from './ToastProvider';

interface CheckRowProps {
  icon: LucideIcon;
  label: string;
  ok: boolean;
  okText: string;
  pendingText: string;
}

function CheckRow({ icon: Icon, label, ok, okText, pendingText }: CheckRowProps) {
  return (
    <li className="flex items-start gap-3 py-2.5">
      <Icon
        aria-hidden
        className={cn('mt-0.5 h-4 w-4 shrink-0', ok ? 'text-success' : 'text-content-subtle')}
        strokeWidth={1.75}
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-content">{label}</p>
        <p className="text-xs leading-relaxed text-content-subtle">{ok ? okText : pendingText}</p>
      </div>
      {ok ? (
        <CheckCircle2 aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-success" />
      ) : (
        <Circle aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-content-subtle/60" />
      )}
      <span className="sr-only">{ok ? 'ready' : 'not ready'}</span>
    </li>
  );
}

export function SessionStatusCard({ className }: { className?: string }) {
  const toast = useToast();
  const { data: session, isLoading } = useSessionStatus();

  const start = useStartSession({
    onSuccess: () =>
      toast.toast({
        title: 'Browser session starting',
        description: 'Sign in to LinkedIn in the window that just opened.',
        variant: 'info',
        duration: 9000,
      }),
    onError: (error) => toast.error('Could not start the browser', errorMessage(error)),
  });

  const stop = useStopSession({
    onSuccess: () => toast.success('Browser session closed'),
    onError: (error) => toast.error('Could not close the browser', errorMessage(error)),
  });

  if (isLoading || !session) {
    return (
      <Card className={className}>
        <CardHeader title="Session" />
        <div className="card-body space-y-3">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-4 w-3/5" />
          <Skeleton className="h-9 w-40" />
        </div>
      </Card>
    );
  }

  const ready = session.browser_open && session.logged_in;

  return (
    <Card className={className}>
      <CardHeader
        title="Session"
        description={ready ? 'Ready to search and prepare applications.' : 'Not ready yet.'}
      />

      <div className="card-body">
        <ul className="divide-y divide-line">
          <CheckRow
            icon={MonitorPlay}
            label="Browser window"
            ok={session.browser_open}
            okText="A controlled Chrome window is open."
            pendingText="Closed — start a session to open one."
          />
          <CheckRow
            icon={Linkedin}
            label="LinkedIn sign-in"
            ok={session.logged_in}
            okText="Signed in; only the session cookies are stored, encrypted."
            pendingText="Sign in yourself in the browser window. Your password is never stored."
          />
          <CheckRow
            icon={Bot}
            label="AI analysis"
            ok={session.ai_configured}
            okText="An API key is configured; jobs can be scored automatically."
            pendingText="No API key configured — scoring and cover letters are unavailable."
          />
        </ul>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {session.browser_open ? (
            <Button
              variant="default"
              loading={stop.isPending}
              onClick={() => stop.mutate()}
              icon={<Power aria-hidden className="h-4 w-4" />}
            >
              Close browser session
            </Button>
          ) : (
            <Button
              variant="primary"
              loading={start.isPending}
              onClick={() => start.mutate()}
              icon={<MonitorPlay aria-hidden className="h-4 w-4" />}
            >
              Start browser session
            </Button>
          )}
        </div>

        <Note tone="neutral" className="mt-3" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
          Starting a session opens a real, visible browser window. You sign in to LinkedIn there
          yourself — this app never asks for, sends or stores your LinkedIn password. Keep that
          window open while a run is in progress, and if LinkedIn ever shows a verification, solve it
          in that window.
        </Note>
      </div>
    </Card>
  );
}
