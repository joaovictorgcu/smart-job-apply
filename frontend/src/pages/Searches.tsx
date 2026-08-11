import { Clock, MapPin, Pencil, Play, Plus, Search as SearchIcon, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { EmptyState } from '@/components/EmptyState';
import { Modal } from '@/components/Modal';
import { Button, Card, Note, PageHeader, Skeleton } from '@/components/primitives';
import { SearchFormDialog } from '@/components/SearchFormDialog';
import { useToast } from '@/components/ToastProvider';
import { useDeleteSearch, useRunSearch, useSearches, useSessionStatus } from '@/hooks/useApi';
import { badgeClass, formatRelativeTime, humanizeSnakeCase } from '@/lib/format';
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
        'Search started',
        `Run #${automationRun.id} is finding and scoring jobs. It will not apply to anything.`,
      );
    },
    onError: (error) => {
      setRunningId(null);
      toast.error('Could not start the search', errorMessage(error));
    },
  });

  const remove = useDeleteSearch({
    onSuccess: () => {
      setDeleting(null);
      toast.toast({ title: 'Search deleted', variant: 'info' });
    },
    onError: (error) => toast.error('Could not delete the search', errorMessage(error)),
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
        title="Searches"
        description="Saved LinkedIn queries. Running one finds and scores jobs — it never starts an application."
        actions={
          <Button variant="primary" onClick={openCreate} icon={<Plus aria-hidden className="h-4 w-4" />}>
            New search
          </Button>
        }
      />

      {!sessionReady ? (
        <Note tone="warning">
          No signed-in browser session yet. Start one from the dashboard and sign in to LinkedIn
          yourself — searches need that window to be open.
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
            title="No saved searches"
            description="A search is a set of keywords and filters you can re-run whenever you want fresh postings."
            action={
              <Button variant="primary" onClick={openCreate} icon={<Plus aria-hidden className="h-4 w-4" />}>
                Create your first search
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
                    {search.is_active ? 'Active' : 'Paused'}
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
                      {humanizeSnakeCase(search.remote_filter)}
                    </span>
                  ) : null}
                  {search.date_posted ? (
                    <span className={badgeClass('neutral')}>
                      <Clock aria-hidden className="h-3 w-3" />
                      {humanizeSnakeCase(search.date_posted)}
                    </span>
                  ) : null}
                  {search.easy_apply_only ? (
                    <span className={badgeClass('accent')}>Easy Apply only</span>
                  ) : null}
                  <span className={badgeClass('neutral')}>max {search.max_results}</span>
                  {search.experience_levels.length > 0 ? (
                    <span className={badgeClass('neutral')}>
                      {search.experience_levels.length} levels
                    </span>
                  ) : null}
                </div>

                <p className="mt-3 text-2xs text-content-subtle">
                  {search.last_run_at
                    ? `Last run ${formatRelativeTime(search.last_run_at)}`
                    : 'Never run yet'}
                </p>

                <div className="mt-4 flex items-center gap-2 border-t border-line pt-3.5">
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={!sessionReady || run.isPending}
                    loading={run.isPending && runningId === search.id}
                    title={
                      sessionReady
                        ? 'Find and score jobs for this search'
                        : 'Start a signed-in browser session first'
                    }
                    onClick={() => {
                      setRunningId(search.id);
                      run.mutate({ search_id: search.id, analyze: true });
                    }}
                    icon={<Play aria-hidden className="h-3.5 w-3.5" />}
                  >
                    Run search
                  </Button>

                  <Button
                    size="sm"
                    onClick={() => openEdit(search)}
                    icon={<Pencil aria-hidden className="h-3.5 w-3.5" />}
                  >
                    Edit
                  </Button>

                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-auto text-danger hover:bg-danger/10 hover:text-danger"
                    onClick={() => setDeleting(search)}
                    aria-label={`Delete ${search.name}`}
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
        title="Delete this search?"
        description={
          deleting
            ? `"${deleting.name}" will be removed. Jobs it already found stay in your list.`
            : undefined
        }
        footer={
          <>
            <Button onClick={() => setDeleting(null)} disabled={remove.isPending}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => {
                if (deleting) remove.mutate(deleting.id);
              }}
            >
              Delete
            </Button>
          </>
        }
      />
    </div>
  );
}
