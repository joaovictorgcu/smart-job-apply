import type { ReactNode } from 'react';

import { Skeleton } from '@/components/primitives';
import { cn } from '@/lib/utils';

export interface DataColumn<T> {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** The card's heading on a phone. Exactly one column should set it. */
  primary?: boolean;
  align?: 'left' | 'right';
  /** Hidden on narrow screens — for columns that are context, not content. */
  hideOnMobile?: boolean;
}

export interface DataListProps<T> {
  columns: DataColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  caption: string;
  empty: ReactNode;
  isLoading?: boolean;
  className?: string;
}

/**
 * One dataset, two layouts.
 *
 * A table below `md` is either unreadable or horizontally scrolled, so the same
 * rows render as cards there — a heading plus labelled values — rather than as a
 * shrunken grid. Both views come from one `columns` array, so they cannot drift
 * apart, and only the table markup carries the semantics screen readers want.
 */
export function DataList<T>({
  columns,
  rows,
  rowKey,
  caption,
  empty,
  isLoading = false,
  className,
}: DataListProps<T>) {
  if (isLoading) {
    return (
      <div className={cn('space-y-2 px-4 py-3.5', className)} aria-busy="true">
        {Array.from({ length: 5 }, (_, index) => (
          <Skeleton key={index} className="h-11" />
        ))}
      </div>
    );
  }

  if (rows.length === 0) return <>{empty}</>;

  const heading = columns.find((column) => column.primary) ?? columns[0];
  const details = columns.filter((column) => column !== heading);

  return (
    <div className={className}>
      {/* Table from md up. */}
      <div className="hidden overflow-x-auto md:block">
        <table className="table-base">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={cn(column.align === 'right' && 'text-right')}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={rowKey(row)}>
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn(column.align === 'right' && 'tabular text-right')}
                  >
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Cards below md. */}
      <ul className="divide-y divide-line md:hidden">
        {rows.map((row) => (
          <li key={rowKey(row)} className="space-y-2 px-4 py-3">
            <div className="min-w-0 text-sm font-medium text-content">{heading.cell(row)}</div>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5">
              {details
                .filter((column) => !column.hideOnMobile)
                .map((column) => (
                  <div key={column.key} className="min-w-0">
                    <dt className="text-2xs uppercase tracking-wider text-content-subtle">
                      {column.header}
                    </dt>
                    <dd className="tabular truncate text-xs text-content-muted">
                      {column.cell(row)}
                    </dd>
                  </div>
                ))}
            </dl>
          </li>
        ))}
      </ul>
    </div>
  );
}
