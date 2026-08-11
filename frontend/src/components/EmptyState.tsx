import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center animate-fade-in',
        compact ? 'gap-2 px-6 py-10' : 'gap-3 px-6 py-16',
        className,
      )}
    >
      {Icon ? (
        <span
          aria-hidden
          className="mb-1 grid h-12 w-12 place-items-center rounded-2xl border border-line bg-surface-sunken text-content-subtle"
        >
          <Icon className="h-5 w-5" strokeWidth={1.75} />
        </span>
      ) : null}
      <p className="text-md font-semibold text-content">{title}</p>
      {description ? (
        <p className="max-w-sm text-sm leading-relaxed text-content-subtle">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
