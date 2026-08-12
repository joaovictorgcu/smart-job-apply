import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';

import { CheckpointBanner } from './CheckpointBanner';
import { Drawer } from './Drawer';
import { Sidebar } from './Sidebar';
import { ToastProvider } from './ToastProvider';
import { Topbar } from './Topbar';

/**
 * Layout route for every authenticated page.
 *
 * The header block sits outside the scroll container, so the checkpoint banner
 * and the kill switch stay on screen no matter how far the page is scrolled.
 */
export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  return (
    <ToastProvider>
      <div className="flex h-screen overflow-hidden bg-surface">
        <aside className="hidden shrink-0 border-r border-line bg-surface-raised md:flex md:w-[4.5rem] lg:w-64">
          <Sidebar className="w-full" />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <div className="shrink-0">
            <CheckpointBanner />
            <Topbar onOpenNav={() => setNavOpen(true)} />
          </div>

          <main className="scroll-area flex-1">
            <div className="mx-auto max-w-[1600px] px-4 py-6 lg:px-8 lg:py-8">
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
        title="Navegação"
      >
        <Sidebar alwaysShowLabels onNavigate={() => setNavOpen(false)} className="py-0" />
      </Drawer>
    </ToastProvider>
  );
}
