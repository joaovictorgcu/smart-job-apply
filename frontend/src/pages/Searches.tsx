import { Clock, MapPin, Pencil, Play, Plus, Search as SearchIcon, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { EmptyState } from '@/components/EmptyState';
import { Modal } from '@/components/Modal';
import { Button, Card, Note, PageHeader, Skeleton } from '@/components/primitives';
import { SearchFormDialog } from '@/components/SearchFormDialog';
import { useToast } from '@/components/ToastProvider';
import { useDeleteSearch, useRunSearch, useSearches, useSessionStatus } from '@/hooks/useApi';
import { badgeClass, enumLabel, formatRelativeTime } from '@/lib/format';
import { errorMessage } from '@/services/client';
import type { Search } from '@/types/api';

export function Searches() {
  const toast = useToast();
  const { data: searches, isLoading } = useSearches();
  const { data: session } = useSessionStatus();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Search | null>(null);
  const [deleting, setDeleting] = useState<Search | null>(null);
  const [runningId, setRunningId] = useState<number | null>(null);

  const run = useRunSearch({
    onSuccess: (automationRun) => {
      setRunningId(null);
      toast.success(
        'Busca iniciada',
        `A execução #${automationRun.id} está encontrando e pontuando vagas. Ela não vai se candidatar a nada.`,
      );
    },
    onError: (error) => {
      setRunningId(null);
      toast.error('Não foi possível iniciar a busca', errorMessage(error));
    },
  });

  const remove = useDeleteSearch({
    onSuccess: () => {
      setDeleting(null);
      toast.toast({ title: 'Busca excluída', variant: 'info' });
    },
    onError: (error) => toast.error('Não foi possível excluir a busca', errorMessage(error)),
  });

  const sessionReady = Boolean(session?.browser_open && session.logged_in);
  const items = searches ?? [];

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (search: Search) => {
    setEditing(search);
    setFormOpen(true);
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Buscas"
        description="Consultas salvas do LinkedIn. Rodar uma encontra e pontua vagas — nunca inicia uma candidatura."
        actions={
          <Button variant="primary" onClick={openCreate} icon={<Plus aria-hidden className="h-4 w-4" />}>
            Nova busca
          </Button>
        }
      />

      {!sessionReady ? (
        <Note tone="warning">
          Ainda não há uma sessão do navegador autenticada. Inicie uma no painel e faça login no
          LinkedIn você mesmo — as buscas precisam dessa janela aberta.
        </Note>
      ) : null}

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
          <Skeleton className="h-52 rounded-xl" />
          <Skeleton className="h-52 rounded-xl" />
          <Skeleton className="h-52 rounded-xl" />
        </div>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={SearchIcon}
            title="Nenhuma busca salva"
            description="Uma busca é um conjunto de palavras-chave e filtros que você pode rodar de novo sempre que quiser anúncios novos."
            action={
              <Button variant="primary" onClick={openCreate} icon={<Plus aria-hidden className="h-4 w-4" />}>
                Criar a sua primeira busca
              </Button>
            }
          />
        </Card>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((search) => (
            <li key={search.id}>
              <Card className="flex h-full flex-col px-5 py-4">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="min-w-0 text-md leading-snug">{search.name}</h2>
                  <span className={badgeClass(search.is_active ? 'success' : 'neutral')}>
                    {search.is_active ? 'Ativa' : 'Pausada'}
                  </span>
                </div>

                <p className="mt-2 truncate font-mono text-xs text-content-muted" title={search.keywords}>
                  {search.keywords}
                </p>

                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  {search.location ? (
                    <span className={badgeClass('neutral')}>
                      <MapPin aria-hidden className="h-3 w-3" />
                      {search.location}
                    </span>
                  ) : null}
                  {search.remote_filter ? (
                    <span className={badgeClass('neutral')}>
                      {enumLabel(search.remote_filter)}
                    </span>
                  ) : null}
                  {search.date_posted ? (
                    <span className={badgeClass('neutral')}>
                      <Clock aria-hidden className="h-3 w-3" />
                      {enumLabel(search.date_posted)}
                    </span>
                  ) : null}
                  {search.easy_apply_only ? (
                    <span className={badgeClass('accent')}>Só Candidatura Simplificada</span>
                  ) : null}
                  <span className={badgeClass('neutral')}>máx {search.max_results}</span>
                  {search.experience_levels.length > 0 ? (
                    <span className={badgeClass('neutral')}>
                      {search.experience_levels.length} níveis
                    </span>
                  ) : null}
                </div>

                <p className="mt-3 text-2xs text-content-subtle">
                  {search.last_run_at
                    ? `Última execução ${formatRelativeTime(search.last_run_at)}`
                    : 'Nunca executada'}
                </p>

                <div className="mt-4 flex items-center gap-2 border-t border-line pt-3.5">
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={!sessionReady || run.isPending}
                    loading={run.isPending && runningId === search.id}
                    title={
                      sessionReady
                        ? 'Encontrar e pontuar vagas para esta busca'
                        : 'Inicie primeiro uma sessão do navegador autenticada'
                    }
                    onClick={() => {
                      setRunningId(search.id);
                      run.mutate({ search_id: search.id, analyze: true });
                    }}
                    icon={<Play aria-hidden className="h-3.5 w-3.5" />}
                  >
                    Rodar busca
                  </Button>

                  <Button
                    size="sm"
                    onClick={() => openEdit(search)}
                    icon={<Pencil aria-hidden className="h-3.5 w-3.5" />}
                  >
                    Editar
                  </Button>

                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-auto text-danger hover:bg-danger/10 hover:text-danger"
                    onClick={() => setDeleting(search)}
                    aria-label={`Excluir ${search.name}`}
                  >
                    <Trash2 aria-hidden className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <SearchFormDialog open={formOpen} onClose={() => setFormOpen(false)} search={editing} />

      <Modal
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        size="sm"
        title="Excluir esta busca?"
        description={
          deleting
            ? `"${deleting.name}" será removida. As vagas que ela já encontrou continuam na sua lista.`
            : undefined
        }
        footer={
          <>
            <Button onClick={() => setDeleting(null)} disabled={remove.isPending}>
              Cancelar
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => {
                if (deleting) remove.mutate(deleting.id);
              }}
            >
              Excluir
            </Button>
          </>
        }
      />
    </div>
  );
}
