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
      <span className="sr-only">{ok ? 'pronto' : 'não pronto'}</span>
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

  return (
    <Card className={className}>
      <CardHeader
        title="Sessão"
        description={ready ? 'Pronta para buscar e preparar candidaturas.' : 'Ainda não está pronta.'}
      />

      <div className="card-body">
        <ul className="divide-y divide-line">
          <CheckRow
            icon={MonitorPlay}
            label="Janela do navegador"
            ok={session.browser_open}
            okText="Uma janela controlada do Chrome está aberta."
            pendingText="Fechada — inicie uma sessão para abrir uma."
          />
          <CheckRow
            icon={Linkedin}
            label="Login no LinkedIn"
            ok={session.logged_in}
            okText="Autenticado; apenas os cookies da sessão são armazenados, criptografados."
            pendingText="Faça login você mesmo na janela do navegador. A sua senha nunca é armazenada."
          />
          <CheckRow
            icon={Bot}
            label="Análise por IA"
            ok={session.ai_configured}
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
