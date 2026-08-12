import { ChevronDown, LogOut, Menu, Moon, Sun, User as UserIcon } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { useAuth } from '@/hooks/useAuth';
import { useEvents } from '@/hooks/useEvents';
import { useTheme } from '@/lib/theme';
import { cn } from '@/lib/utils';

import { DryRunToggle } from './DryRunToggle';
import { KillSwitchButton } from './KillSwitchButton';
import { Button } from './primitives';

function ConnectionDot({ connected }: { connected: boolean }) {
  return (
    <span
      className="flex items-center gap-1.5"
      title={connected ? 'Transmissão de eventos ao vivo conectada' : 'Transmissão de eventos ao vivo desconectada'}
    >
      <span aria-hidden className={cn('live-dot', !connected && 'live-dot-idle')} />
      <span
        className={cn(
          'hidden text-xs font-medium sm:inline',
          connected ? 'text-content-muted' : 'text-content-subtle',
        )}
      >
        {connected ? 'Ao vivo' : 'Offline'}
      </span>
      <span className="sr-only" role="status">
        {connected ? 'Transmissão de eventos ao vivo conectada' : 'Transmissão de eventos ao vivo desconectada'}
      </span>
    </span>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const label = user?.full_name || user?.email || 'Conta';

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="btn btn-ghost gap-2 px-2"
      >
        <span
          aria-hidden
          className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent-500/18 text-2xs font-semibold text-accent-400"
        >
          {label.slice(0, 1).toUpperCase()}
        </span>
        <span className="hidden max-w-[10rem] truncate md:inline">{label}</span>
        <ChevronDown
          aria-hidden
          className={cn('h-3.5 w-3.5 transition-transform duration-150', open && 'rotate-180')}
        />
      </button>

      {open ? (
        <div
          role="menu"
          aria-label="Conta"
          className="absolute right-0 z-40 mt-1.5 w-60 overflow-hidden rounded-xl border border-line bg-surface-overlay shadow-lifted animate-fade-in"
        >
          <div className="border-b border-line px-3 py-2.5">
            <p className="truncate text-sm font-medium text-content">
              {user?.full_name || 'Operador'}
            </p>
            <p className="truncate text-xs text-content-subtle">{user?.email}</p>
          </div>
          <div className="p-1">
            <Link
              to="/profile"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="nav-item w-full text-sm"
            >
              <UserIcon aria-hidden className="h-4 w-4" />
              Perfil
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                logout();
                navigate('/login', { replace: true });
              }}
              className="nav-item w-full text-sm text-danger hover:bg-danger/10 hover:text-danger"
            >
              <LogOut aria-hidden className="h-4 w-4" />
              Sair
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export interface TopbarProps {
  onOpenNav: () => void;
}

export function Topbar({ onOpenNav }: TopbarProps) {
  const { connected } = useEvents();
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="border-b border-line bg-surface/85 backdrop-blur supports-[backdrop-filter]:bg-surface/70">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-2 px-4 lg:px-8">
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          onClick={onOpenNav}
          aria-label="Abrir navegação"
        >
          <Menu aria-hidden className="h-[18px] w-[18px]" />
        </Button>

        <ConnectionDot connected={connected} />

        <div className="ml-auto flex items-center gap-2">
          <DryRunToggle className="hidden sm:flex" />
          <KillSwitchButton />

          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Mudar para o tema claro' : 'Mudar para o tema escuro'}
            title={theme === 'dark' ? 'Mudar para o tema claro' : 'Mudar para o tema escuro'}
          >
            {theme === 'dark' ? (
              <Sun aria-hidden className="h-[18px] w-[18px]" />
            ) : (
              <Moon aria-hidden className="h-[18px] w-[18px]" />
            )}
          </Button>

          <UserMenu />
        </div>
      </div>

      <div className="border-t border-line px-4 py-2 sm:hidden">
        <DryRunToggle className="w-full justify-between" />
      </div>
    </header>
  );
}
