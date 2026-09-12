import { Menu, Moon, RefreshCw, Sun } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';

import { Drawer } from '@/components/Drawer';
import { Button } from '@/components/primitives';
import { ToastProvider, useToast } from '@/components/ToastProvider';
import { useRefreshAdminOverview } from '@/hooks/useApi';
import { errorMessage } from '@/services/client';
import { useTheme } from '@/lib/theme';
import { formatTime } from '@/lib/format';

import { AdminSidebar } from './AdminSidebar';
import { AdminPeriodProvider, PeriodFilter, useAdminPeriod } from './period';

/**
 * "Atualizar dados".
 *
 * Recomputes server-side rather than re-reading the cached snapshot, so it is a
 * mutation with a pending state — the button says what it is doing instead of
 * looking inert for the second the aggregates take.
 */
function RefreshButton() {
  const { query } = useAdminPeriod();
  const toast = useToast();
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);
  const refresh = useRefreshAdminOverview(query, {
    onSuccess: () => setRefreshedAt(new Date()),
    onError: (error) => toast.error(errorMessage(error, 'Não foi possível atualizar os dados.')),
  });

  return (
    <div className="flex items-center gap-2">
      {refreshedAt ? (
        <span className="hidden text-2xs text-content-subtle sm:inline" aria-live="polite">
          Atualizado às {formatTime(refreshedAt)}
        </span>
      ) : null}
      <Button
        size="sm"
        onClick={() => refresh.mutate()}
        loading={refresh.isPending}
        icon={<RefreshCw aria-hidden className="h-3.5 w-3.5" />}
      >
        {refresh.isPending ? 'Atualizando' : 'Atualizar dados'}
      </Button>
    </div>
  );
}

function AdminTopbar({ onOpenNav }: { onOpenNav: () => void }) {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="border-b border-line bg-surface/85 backdrop-blur supports-[backdrop-filter]:bg-surface/70">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-2 px-4 py-2.5 lg:px-8">
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          onClick={onOpenNav}
          aria-label="Abrir navegação administrativa"
        >
          <Menu aria-hidden className="h-[18px] w-[18px]" />
        </Button>

        <span className="badge badge-accent">Área administrativa</span>

        {/* Wraps to its own line on a phone instead of scrolling off. */}
        <PeriodFilter className="order-last w-full lg:order-none lg:ml-4 lg:w-auto" />

        <div className="ml-auto flex items-center gap-2">
          <RefreshButton />
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Mudar para o tema claro' : 'Mudar para o tema escuro'}
          >
            {theme === 'dark' ? (
              <Sun aria-hidden className="h-[18px] w-[18px]" />
            ) : (
              <Moon aria-hidden className="h-[18px] w-[18px]" />
            )}
          </Button>
        </div>
      </div>
    </header>
  );
}

/**
 * Layout route for every /admin page.
 *
 * Deliberately not `AppShell`: this area has its own navigation, its own period
 * filter, and no kill switch or dry-run toggle — those act on *one* account, and
 * an administrator looking at platform metrics is not operating their own
 * automation. `admin-scope` re-points the accent ramp at violet, which is what
 * makes the area recognisable without a second set of components (see
 * index.css).
 */
export function AdminShell() {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  return (
    <AdminPeriodProvider>
      <ToastProvider>
        <div className="admin-scope flex h-screen overflow-hidden bg-surface">
          <aside className="hidden shrink-0 border-r border-line bg-surface-sunken md:flex md:w-[4.5rem] lg:w-60">
            <AdminSidebar className="w-full" />
          </aside>

          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <div className="shrink-0">
              <AdminTopbar onOpenNav={() => setNavOpen(true)} />
            </div>

            <main className="scroll-area flex-1">
              <div className="mx-auto max-w-[1600px] px-4 py-6 lg:px-8">
                <Outlet />
              </div>
            </main>
          </div>
        </div>

        <Drawer
          open={navOpen}
          onClose={() => setNavOpen(false)}
          side="left"
          width="max-w-[17rem]"
          title="Navegação administrativa"
          className="admin-scope"
        >
          <AdminSidebar alwaysShowLabels onNavigate={() => setNavOpen(false)} className="py-0" />
        </Drawer>
      </ToastProvider>
    </AdminPeriodProvider>
  );
}
