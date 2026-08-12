import { ChevronLeft, ChevronRight } from 'lucide-react';

import { formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';

import { Button } from './primitives';

export interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
  className?: string;
  unit?: string;
}

function pageWindow(current: number, pageCount: number): number[] {
  const span = 5;
  if (pageCount <= span) return Array.from({ length: pageCount }, (_, index) => index + 1);
  const start = Math.max(1, Math.min(current - 2, pageCount - span + 1));
  return Array.from({ length: span }, (_, index) => start + index);
}

export function Pagination({
  total,
  limit,
  offset,
  onOffsetChange,
  className,
  unit = 'resultados',
}: PaginationProps) {
  const safeLimit = limit > 0 ? limit : 20;
  const pageCount = Math.max(1, Math.ceil(total / safeLimit));
  const current = Math.floor(offset / safeLimit) + 1;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + safeLimit, total);

  const goTo = (page: number) =>
    onOffsetChange((Math.max(1, Math.min(page, pageCount)) - 1) * safeLimit);

  return (
    <nav
      aria-label="Paginação"
      className={cn('flex flex-wrap items-center justify-between gap-3', className)}
    >
      <p className="tabular text-xs text-content-subtle">
        {total === 0 ? (
          `Sem ${unit}`
        ) : (
          <>
            <span className="font-medium text-content">
              {formatNumber(from)}–{formatNumber(to)}
            </span>{' '}
            de {formatNumber(total)} {unit}
          </>
        )}
      </p>

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          aria-label="Página anterior"
          disabled={current <= 1}
          onClick={() => goTo(current - 1)}
        >
          <ChevronLeft aria-hidden className="h-4 w-4" />
        </Button>

        {pageWindow(current, pageCount).map((page) => (
          <button
            key={page}
            type="button"
            aria-label={`Página ${page}`}
            aria-current={page === current ? 'page' : undefined}
            onClick={() => goTo(page)}
            className={cn(
              'tabular h-8 min-w-8 rounded-lg px-2 text-xs font-medium transition duration-150 ease-snap',
              page === current
                ? 'bg-accent-500/14 text-accent-400'
                : 'text-content-muted hover:bg-surface-overlay hover:text-content',
            )}
          >
            {page}
          </button>
        ))}

        <Button
          variant="ghost"
          size="icon"
          aria-label="Próxima página"
          disabled={current >= pageCount}
          onClick={() => goTo(current + 1)}
        >
          <ChevronRight aria-hidden className="h-4 w-4" />
        </Button>
      </div>
    </nav>
  );
}
