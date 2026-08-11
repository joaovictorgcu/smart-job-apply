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
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/jobs', label: 'Jobs', icon: Briefcase },
  { to: '/applications', label: 'Applications', icon: Send },
  { to: '/pipeline', label: 'Pipeline', icon: Columns3 },
  { to: '/searches', label: 'Searches', icon: Search },
  { to: '/activity', label: 'Activity', icon: Activity },
  { to: '/profile', label: 'Profile', icon: User },
  { to: '/settings', label: 'Settings', icon: Settings },
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
            assisted mode
          </span>
        </span>
      </div>

      <nav aria-label="Main navigation" className="scroll-area min-h-0 flex-1 px-2">
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
            Assisted mode
          </p>
          <p className="mt-1.5 text-xs leading-relaxed text-content-muted">
            Searching, scoring and form filling are separate from submitting. No application is
            ever sent without your explicit approval.
          </p>
        </div>
      </div>
    </div>
  );
}
