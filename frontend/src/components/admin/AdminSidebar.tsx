import {
  ArrowLeft,
  Bot,
  Brain,
  Briefcase,
  LayoutDashboard,
  ScrollText,
  Send,
  Settings,
  ShieldCheck,
  Users,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Link, NavLink } from 'react-router-dom';

import { cn } from '@/lib/utils';

interface AdminNavEntry {
  label: string;
  icon: LucideIcon;
  to: string;
  end?: boolean;
}

/**
 * The panel's navigation.
 *
 * Four of these used to render disabled, with a tooltip explaining that their
 * numbers live on the dashboard. That was half the menu leading nowhere — the
 * same dead-control problem as a permanently greyed "Parar" button, and a
 * tooltip is not a fix for a destination that does not exist.
 *
 * They are links now, to the dashboard section that actually answers them. The
 * menu is complete, every item goes somewhere, and no page was invented to sit
 * behind a label.
 */
const NAV: AdminNavEntry[] = [
  { to: '/admin', label: 'Painel', icon: LayoutDashboard, end: true },
  { to: '/admin/users', label: 'Usuários', icon: Users },
  { to: '/admin/jobs', label: 'Vagas', icon: Briefcase },
  { to: '/admin/logs', label: 'Logs', icon: ScrollText },
  { to: '/admin#funil', label: 'Candidaturas', icon: Send },
  { to: '/admin#automacao', label: 'Automação', icon: Bot },
  { to: '/admin#ia', label: 'IA', icon: Brain },
  { to: '/admin#sistema', label: 'Sistema', icon: Settings },
];

export interface AdminSidebarProps {
  alwaysShowLabels?: boolean;
  onNavigate?: () => void;
  className?: string;
}

export function AdminSidebar({
  alwaysShowLabels = false,
  onNavigate,
  className,
}: AdminSidebarProps) {
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
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-600 text-white shadow-glow-sm"
        >
          <ShieldCheck className="h-4 w-4" />
        </span>
        <span className={cn('min-w-0', labelClass)}>
          <span className="block truncate text-sm font-semibold leading-tight text-content">
            Admin
          </span>
          <span className="block truncate text-2xs leading-tight text-content-subtle">
            Smart Job Apply
          </span>
        </span>
      </div>

      <nav aria-label="Navegação administrativa" className="scroll-area min-h-0 flex-1 px-2">
        <ul className="space-y-0.5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <li key={label}>
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

      <div className={cn('px-2', alwaysShowLabels ? 'block' : 'hidden lg:block')}>
        <Link to="/" onClick={onNavigate} className="nav-item text-sm">
          <ArrowLeft aria-hidden className="h-4 w-4 shrink-0" />
          <span className="truncate">Voltar ao app</span>
        </Link>
      </div>
    </div>
  );
}
