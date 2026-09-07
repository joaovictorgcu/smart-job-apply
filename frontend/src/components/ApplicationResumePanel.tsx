import {
  ClipboardCopy,
  FileText,
  GitCompareArrows,
  Pencil,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  User,
} from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { EmptyState } from '@/components/EmptyState';
import { Button, Card, CardHeader, Note, Skeleton } from '@/components/primitives';
import { ResumeDiffView } from '@/components/ResumeDiffView';
import { ResumeDocumentView } from '@/components/ResumeDocumentView';
import { ResumeVersionEditor } from '@/components/ResumeVersionEditor';
import { useToast } from '@/components/ToastProvider';
import {
  useApplicationResume,
  useDeriveApplicationResume,
  useUpdateApplicationResume,
} from '@/hooks/useApi';
import { badgeClass, formatDateTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';
import type { ApplicationDetail, ResumeDocument } from '@/types/api';

type Tab = 'version' | 'master' | 'diff';

const TABS: { id: Tab; label: string; icon: typeof FileText }[] = [
  { id: 'version', label: 'Desta candidatura', icon: FileText },
  { id: 'master', label: 'Currículo principal', icon: User },
  { id: 'diff', label: 'Diferenças', icon: GitCompareArrows },
];

interface ApplicationResumePanelProps {
  application: ApplicationDetail;
  className?: string;
}

/**
 * The resume this application presents, next to the master it came from.
 *
 * Three tabs rather than three screens: the two documents and their difference
 * are the same subject, and the question the user actually has — "which resume
 * is this application sending, and how is it different from mine?" — is only
 * answerable by putting them a click apart. The master tab is read-only and
 * says so, with the one link out to where it *is* edited: that is the
 * "voltar ao currículo principal" path, and it stays a link rather than a
 * second editor so the two documents can never be confused for one another.
 *
 * Every real state is handled: no version yet (new, or prepared before the
 * feature existed), loading, present, editing, saving, failed, and stale after
 * the master changed.
 */
export function ApplicationResumePanel({
  application,
  className,
}: ApplicationResumePanelProps) {
  const toast = useToast();
  const [tab, setTab] = useState<Tab>('version');
  const [editing, setEditing] = useState(false);
  const { data, isLoading, isError, error, refetch } = useApplicationResume(application.id);

  const derive = useDeriveApplicationResume(application.id, {
    onSuccess: () => {
      setTab('version');
      toast.success(
        'Currículo desta candidatura gerado',
        'Priorizado a partir do seu currículo principal.',
      );
    },
    onError: (mutationError) =>
      toast.error('Não foi possível gerar a versão', errorMessage(mutationError)),
  });

  const save = useUpdateApplicationResume(application.id, {
    onSuccess: () => {
      setEditing(false);
      toast.success('Versão salva', 'Só esta candidatura mudou.');
    },
    onError: (mutationError) =>
      toast.error('Não foi possível salvar a versão', errorMessage(mutationError)),
  });

  const jobLabel = application.job
    ? `${application.job.title} — ${application.job.company}`
    : `vaga #${application.job_id}`;

  const header = (
    <CardHeader
      title="Currículo desta candidatura"
      description={`Versão própria para ${jobLabel}. O seu currículo principal não muda.`}
      actions={
        data ? (
          <>
            <Button
              size="sm"
              disabled={save.isPending}
              onClick={() => setEditing(true)}
              icon={<Pencil aria-hidden className="h-3.5 w-3.5" />}
            >
              Editar
            </Button>
            <Button
              size="sm"
              loading={derive.isPending}
              title="Descarta as edições desta versão e recomeça do currículo principal"
              onClick={() => derive.mutate()}
              icon={<RotateCcw aria-hidden className="h-3.5 w-3.5" />}
            >
              Regerar do principal
            </Button>
          </>
        ) : null
      }
    />
  );

  if (isLoading) {
    return (
      <Card className={className} aria-busy="true">
        {header}
        <div className="card-body space-y-3">
          <Skeleton className="h-8 w-64 rounded-lg" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-32 w-full rounded-lg" />
        </div>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className={className}>
        {header}
        <div className="card-body space-y-3">
          <Note tone="danger" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
            Não foi possível carregar o currículo desta candidatura. {errorMessage(error)}
          </Note>
          <Button onClick={() => void refetch()}>Tentar de novo</Button>
        </div>
      </Card>
    );
  }

  if (!data) {
    // Two causes, one way out: a brand-new application whose master resume is
    // still empty, and one prepared before per-application resumes existed.
    return (
      <Card className={className}>
        {header}
        <div className="card-body">
          <EmptyState
            icon={FileText}
            title="Esta candidatura ainda não tem currículo próprio"
            description="Gere uma versão a partir do seu currículo principal: as experiências, tecnologias e projetos mais próximos desta vaga vão para o topo, e nada é inventado."
            action={
              <div className="flex flex-wrap items-center justify-center gap-2">
                <Button
                  variant="primary"
                  loading={derive.isPending}
                  onClick={() => derive.mutate()}
                  icon={<Sparkles aria-hidden className="h-4 w-4" />}
                >
                  Gerar do currículo principal
                </Button>
                <Link to="/profile" className="btn">
                  <User aria-hidden className="h-4 w-4" />
                  Ver currículo principal
                </Link>
              </div>
            }
          />
        </div>
      </Card>
    );
  }

  const onSave = (document: ResumeDocument) => save.mutate(document);

  return (
    <Card className={className}>
      {header}

      <div className="card-body space-y-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={badgeClass(data.source === 'user' ? 'info' : 'accent')}>
            {data.source === 'user' ? 'editado por você' : 'priorizado automaticamente'}
          </span>
          {data.focus.length > 0 ? (
            <span className="text-2xs text-content-subtle">
              foco: <span className="text-accent-400">{data.focus.slice(0, 4).join(' · ')}</span>
            </span>
          ) : (
            <span className="text-2xs text-content-subtle">
              nenhuma interseção entre esta vaga e o seu currículo
            </span>
          )}
        </div>

        {data.is_stale ? (
          <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
            O seu currículo principal mudou depois que esta versão foi gerada. Esta candidatura
            continua exatamente como está — regere se quiser trazer o que mudou.
          </Note>
        ) : null}

        {data.invention_flags.length > 0 ? (
          <Note tone="danger" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
            <span className="font-medium">Confira você mesmo.</span> Aparecem nesta versão mas não
            no seu currículo principal:{' '}
            <span className="font-medium">{data.invention_flags.join(', ')}</span>. A ferramenta
            sinaliza; ela não remove.
          </Note>
        ) : data.source === 'user' ? (
          <Note tone="accent" icon={<ShieldCheck aria-hidden className="h-3.5 w-3.5" />}>
            Nada nesta versão está fora do seu currículo principal.
          </Note>
        ) : null}

        <div
          role="tablist"
          aria-label="Qual currículo mostrar"
          className="flex flex-wrap gap-1 rounded-lg border border-line bg-surface-sunken p-1"
        >
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              id={`resume-tab-${id}`}
              aria-selected={tab === id}
              aria-controls={`resume-panel-${id}`}
              onClick={() => setTab(id)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition duration-150 ease-snap',
                tab === id
                  ? 'bg-accent-500/12 text-accent-400'
                  : 'text-content-muted hover:bg-surface-overlay hover:text-content',
              )}
            >
              <Icon aria-hidden className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>

        <div
          role="tabpanel"
          id={`resume-panel-${tab}`}
          aria-labelledby={`resume-tab-${tab}`}
          tabIndex={-1}
        >
          {tab === 'version' ? (
            <ResumeDocumentView document={data.document} highlight={data.focus} />
          ) : tab === 'master' ? (
            <div className="space-y-3">
              <Note tone="neutral" icon={<User aria-hidden className="h-3.5 w-3.5" />}>
                Este é o seu currículo <span className="font-medium">principal</span>, como estava
                quando esta versão foi gerada. Ele é só leitura aqui — editar o principal é em{' '}
                <Link to="/profile" className="font-medium text-accent-400 hover:underline">
                  Perfil
                </Link>
                , e não muda nenhuma candidatura que já exista.
              </Note>
              <ResumeDocumentView document={data.base_document} />
            </div>
          ) : (
            <ResumeDiffView
              base={data.base_document}
              document={data.document}
              changes={data.changes}
            />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
          <Button
            size="sm"
            onClick={() => {
              void navigator.clipboard
                ?.writeText(data.markdown)
                .then(() => toast.toast({ title: 'Currículo copiado', variant: 'success' }))
                .catch(() =>
                  toast.warning(
                    'Não foi possível copiar',
                    'Selecione o texto na aba desta candidatura.',
                  ),
                );
            }}
            icon={<ClipboardCopy aria-hidden className="h-3.5 w-3.5" />}
          >
            Copiar como texto
          </Button>
          <Link to="/profile" className="btn btn-sm">
            <User aria-hidden className="h-3.5 w-3.5" />
            Ir ao currículo principal
          </Link>
          {data.updated_at ? (
            <span className="ml-auto text-2xs text-content-subtle">
              atualizada em {formatDateTime(data.updated_at)}
            </span>
          ) : null}
        </div>
      </div>

      {/* Mounted only while open, so the editor's draft never outlives a
          cancelled edit — reopening shows the saved version. */}
      {editing ? (
        <ResumeVersionEditor
          open
          onClose={() => setEditing(false)}
          document={data.document}
          base={data.base_document}
          focus={data.focus}
          saving={save.isPending}
          error={save.isError ? errorMessage(save.error) : null}
          onSave={onSave}
        />
      ) : null}
    </Card>
  );
}
