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
  to?: string;
  end?: boolean;
  /** Why this destination is not a page yet. Rendered as the item's tooltip. */
  pending?: string;
}

/**
 * The panel's navigation, including the destinations that do not exist yet.
 *
 * The four without a `to` are shown as disabled with a reason, rather than
 * linking to a page built only to have something behind the link: every number
 * they would carry is already on the dashboard, in the section named in the
 * tooltip. When one of them earns a screen of its own, it gains a `to` here and
 * nothing else changes.
 */
const NAV: AdminNavEntry[] = [
  { to: '/admin', label: 'Painel', icon: LayoutDashboard, end: true },
  { to: '/admin/users', label: 'Usuários', icon: Users },
  { to: '/admin/jobs', label: 'Vagas', icon: Briefcase },
  { to: '/admin/logs', label: 'Logs', icon: ScrollText },
  {
    label: 'Candidaturas',
    icon: Send,
    pending: 'Sem página própria: os números estão no funil e nos indicadores do painel.',
  },
  {
    label: 'Automação',
    icon: Bot,
    pending: 'Sem página própria: o estado está em "Saúde da automação", no painel.',
  },
  {
    label: 'IA',
    icon: Brain,
    pending: 'Sem página própria: o estado está em "Saúde da IA", no painel.',
  },
  {
    label: 'Configurações',
    icon: Settings,
    pending: 'A área administrativa é somente leitura por enquanto.',
  },
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
          {NAV.map(({ to, label, icon: Icon, end, pending }) => (
            <li key={label}>
              {to ? (
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
              ) : (
                <span
                  aria-disabled="true"
                  title={pending}
                  className={cn(
                    'nav-item cursor-not-allowed text-content-subtle opacity-60 hover:bg-transparent hover:text-content-subtle',
                    alwaysShowLabels ? '' : 'justify-center lg:justify-start',
                  )}
                >
                  <Icon aria-hidden className="h-[18px] w-[18px] shrink-0" strokeWidth={1.75} />
                  <span className={cn('truncate', labelClass)}>{label}</span>
                  <span className={cn('ml-auto text-2xs', labelClass)}>no painel</span>
                </span>
              )}
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
