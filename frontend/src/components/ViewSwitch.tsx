import { NavLink } from 'react-router-dom';

import { cn } from '@/lib/utils';

export interface ViewSwitchOption {
  to: string;
  label: string;
  /** Only the list view should match on the exact path. */
  end?: boolean;
}

export interface ViewSwitchProps {
  /** Names the group for a screen reader — "Candidaturas", not "Alternar visão". */
  label: string;
  options: ViewSwitchOption[];
  className?: string;
}

/**
 * Two ways of reading one list, side by side.
 *
 * Applications and the funnel were separate sidebar destinations, which asked
 * the user to know in advance that they are the same rows grouped differently.
 * As a switch on the screen, the question answers itself: you are looking at
 * your applications, and this is how to look at them another way.
 *
 * Links rather than state, so each view keeps its own URL — a funnel someone
 * bookmarked still opens on the funnel.
 */
export function ViewSwitch({ label, options, className }: ViewSwitchProps) {
  return (
    <nav
      aria-label={label}
      className={cn(
        'inline-flex rounded-lg border border-line bg-surface-sunken p-0.5',
        className,
      )}
    >
      {options.map((option) => (
        <NavLink
          key={option.to}
          to={option.to}
          end={option.end}
          className={({ isActive }) =>
            cn(
              'rounded-[6px] px-3 py-1.5 text-xs font-medium transition duration-150 ease-snap',
              isActive
                ? 'bg-surface-raised text-content shadow-sm'
                : 'text-content-muted hover:text-content',
            )
          }
        >
          {option.label}
        </NavLink>
      ))}
    </nav>
  );
}
