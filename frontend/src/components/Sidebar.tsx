import {
  Activity,
  Briefcase,
  Columns3,
  LayoutDashboard,
  Search,
  Send,
  Settings,
  ShieldCheck,
  User,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { NavLink } from 'react-router-dom';

import { cn } from '@/lib/utils';

interface NavEntry {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Only the dashboard should match on the exact path. */
  end?: boolean;
}

const NAV: NavEntry[] = [
  { to: '/', label: 'Painel', icon: LayoutDashboard, end: true },
  { to: '/jobs', label: 'Vagas', icon: Briefcase },
  { to: '/applications', label: 'Candidaturas', icon: Send },
  { to: '/pipeline', label: 'Funil', icon: Columns3 },
  { to: '/searches', label: 'Buscas', icon: Search },
  { to: '/activity', label: 'Atividade', icon: Activity },
  { to: '/profile', label: 'Perfil', icon: User },
  { to: '/settings', label: 'Configurações', icon: Settings },
];

export interface SidebarProps {
  /** Sheet mode keeps labels visible at every width. */
  alwaysShowLabels?: boolean;
  onNavigate?: () => void;
  className?: string;
}

export function Sidebar({ alwaysShowLabels = false, onNavigate, className }: SidebarProps) {
  const labelClass = alwaysShowLabels ? 'inline' : 'hidden lg:inline';

  return (
    <div className={cn('flex h-full min-h-0 flex-col gap-6 py-5', className)}>
      <div
        className={cn(
          'flex items-center gap-2.5 px-3',
          alwaysShowLabels ? '' : 'justify-center lg:justify-start',
        )}
      >
        <span
          aria-hidden
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-600 text-xs font-bold text-white shadow-glow-sm"
        >
          LA
        </span>
        <span className={cn('min-w-0', labelClass)}>
          <span className="block truncate text-sm font-semibold leading-tight text-content">
            Auto Apply
          </span>
          <span className="block truncate text-2xs leading-tight text-content-subtle">
            modo assistido
          </span>
        </span>
      </div>

      <nav aria-label="Navegação principal" className="scroll-area min-h-0 flex-1 px-2">
        <ul className="space-y-0.5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={end}
                onClick={onNavigate}
                title={alwaysShowLabels ? undefined : label}
                className={({ isActive }) =>
                  cn(
                    'nav-item',
                    alwaysShowLabels ? '' : 'justify-center lg:justify-start',
                    isActive && 'nav-item-active',
                  )
                }
              >
                <Icon aria-hidden className="h-[18px] w-[18px] shrink-0" strokeWidth={1.75} />
                <span className={cn('truncate', labelClass)}>{label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className={cn('px-3', alwaysShowLabels ? 'block' : 'hidden lg:block')}>
        <div className="rounded-lg border border-line bg-surface-sunken p-3">
          <p className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-content-subtle">
            <ShieldCheck aria-hidden className="h-3.5 w-3.5" />
            Modo assistido
          </p>
          <p className="mt-1.5 text-xs leading-relaxed text-content-muted">
            Busca, pontuação e preenchimento são separados do envio. Nenhuma candidatura é
            enviada sem a sua aprovação explícita.
          </p>
        </div>
      </div>
    </div>
  );
}
