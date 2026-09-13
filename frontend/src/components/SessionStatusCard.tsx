import { Activity, Bot, CheckCircle2, Info, Linkedin, MonitorPlay, Power } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useSessionStatus, useStartSession, useStopSession } from '@/hooks/useApi';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';

import { Button, Card, CardHeader, Note, Skeleton } from './primitives';
import { useToast } from './ToastProvider';

/**
 * Where a step sits in the sequence, which is what decides its weight.
 *
 * `next` is the only one the user can act on: the browser has to be open before
 * anyone can log in. Giving all three the same weight asked the reader to work
 * out the order for themselves every time they looked.
 */
type StepState = 'done' | 'next' | 'later';

interface CheckRowProps {
  icon: LucideIcon;
  label: string;
  state: StepState;
  okText: string;
  pendingText: string;
}

function CheckRow({ icon: Icon, label, state, okText, pendingText }: CheckRowProps) {
  const done = state === 'done';
  return (
    <li
      className={cn(
        'flex items-start gap-3 py-2.5',
        // A step that cannot be reached yet steps back rather than disappearing:
        // seeing what comes after is the point of showing the sequence at all.
        state === 'later' && 'opacity-55',
      )}
    >
      {/* One status mark, not two. The row used to colour this icon *and* trail
          a filled-or-empty circle saying the same thing — and an empty circle at
          the end of a row reads as a radio button nobody can click. */}
      {done ? (
        <CheckCircle2 aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-success" />
      ) : (
        <Icon
          aria-hidden
          className={cn(
            'mt-0.5 h-4 w-4 shrink-0',
            state === 'next' ? 'text-accent-400' : 'text-content-subtle',
          )}
          strokeWidth={1.75}
        />
      )}
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            'text-sm',
            state === 'next' ? 'font-semibold text-content' : 'font-medium text-content-muted',
          )}
        >
          {label}
        </p>
        <p className="text-xs leading-relaxed text-content-subtle">{done ? okText : pendingText}</p>
      </div>
      <span className="sr-only">{done ? 'pronto' : 'não pronto'}</span>
    </li>
  );
}

export function SessionStatusCard({ className }: { className?: string }) {
  const toast = useToast();
  const { data: session, isLoading } = useSessionStatus();

  const start = useStartSession({
    onSuccess: () =>
      toast.toast({
        title: 'Iniciando a sessão do navegador',
        description: 'Faça login no LinkedIn na janela que acabou de abrir.',
        variant: 'info',
        duration: 9000,
      }),
    onError: (error) => toast.error('Não foi possível iniciar o navegador', errorMessage(error)),
  });

  const stop = useStopSession({
    onSuccess: () => toast.success('Sessão do navegador encerrada'),
    onError: (error) => toast.error('Não foi possível encerrar o navegador', errorMessage(error)),
  });

  if (isLoading || !session) {
    return (
      <Card className={className}>
        <CardHeader title="Sessão" />
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

  // The steps run in order — a browser window has to exist before anyone can
  // log into it — so only the first unsatisfied one is actionable. The AI key
  // is deliberately last and independent: it blocks scoring, never the session.
  const stepStates: StepState[] = (() => {
    const done = [session.browser_open, session.logged_in, session.ai_configured];
    const firstPending = done.indexOf(false);
    return done.map((ok, index) =>
      ok ? 'done' : index === firstPending ? 'next' : 'later',
    );
  })();

  return (
    <Card className={className}>
      <CardHeader
        title="Sessão"
        description={ready ? 'Pronta para buscar e preparar candidaturas.' : 'Ainda não está pronta.'}
        actions={
          // The event log describes this session, so it is reachable from it
          // rather than from a sidebar entry of its own.
          <Link to="/activity" className="btn btn-sm">
            <Activity aria-hidden className="h-3.5 w-3.5" />
            Histórico
          </Link>
        }
      />

      <div className="card-body">
        <ul className="divide-y divide-line">
          <CheckRow
            icon={MonitorPlay}
            label="Janela do navegador"
            state={stepStates[0]}
            okText="Uma janela controlada do Chrome está aberta."
            pendingText="Fechada — inicie uma sessão para abrir uma."
          />
          <CheckRow
            icon={Linkedin}
            label="Login no LinkedIn"
            state={stepStates[1]}
            okText="Autenticado; apenas os cookies da sessão são armazenados, criptografados."
            pendingText="Faça login você mesmo na janela do navegador. A sua senha nunca é armazenada."
          />
          <CheckRow
            icon={Bot}
            label="Análise por IA"
            state={stepStates[2]}
            okText="Uma chave de API está configurada; as vagas podem ser pontuadas automaticamente."
            pendingText="Nenhuma chave de API configurada — pontuação e cartas de apresentação ficam indisponíveis."
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
              Encerrar a sessão do navegador
            </Button>
          ) : (
            <Button
              variant="primary"
              loading={start.isPending}
              onClick={() => start.mutate()}
              icon={<MonitorPlay aria-hidden className="h-4 w-4" />}
            >
              Iniciar a sessão do navegador
            </Button>
          )}
        </div>

        <Note tone="neutral" className="mt-3" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
          Iniciar uma sessão abre uma janela de navegador real e visível. Você faz login no LinkedIn
          ali mesmo — este app nunca pede, envia ou armazena a sua senha do LinkedIn. Mantenha essa
          janela aberta enquanto uma execução estiver em andamento e, se o LinkedIn mostrar uma
          verificação, resolva-a nessa janela.
        </Note>
      </div>
    </Card>
  );
}
