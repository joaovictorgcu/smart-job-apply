/* eslint-disable react-refresh/only-export-components -- the provider, its hook and the control that drives it belong together */
/**
 * The period the whole panel is scoped to.
 *
 * Held in one context rather than per page so switching from Painel to Usuários
 * keeps the window the administrator chose. The provider guarantees the query it
 * hands out is always *valid*: a half-filled custom range would 422 every
 * request, so it keeps serving the last complete selection until both dates are
 * in, and says so through `customIncomplete`.
 */

import { CalendarRange } from 'lucide-react';
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

import { Input } from '@/components/primitives';
import { cn } from '@/lib/utils';
import { ADMIN_PERIODS, type AdminPeriod, type AdminPeriodQuery } from '@/types/api';

import { PERIOD_LABELS } from './labels';

const DEFAULT_PERIOD: AdminPeriod = '7d';

interface AdminPeriodValue {
  /** The selection shown in the control. */
  period: AdminPeriod;
  start: string;
  end: string;
  /** Always a complete, valid query — safe to pass straight to a hook. */
  query: AdminPeriodQuery;
  /** True while "Personalizado" is chosen and a bound is still missing. */
  customIncomplete: boolean;
  setPeriod: (period: AdminPeriod) => void;
  setRange: (start: string, end: string) => void;
}

const AdminPeriodContext = createContext<AdminPeriodValue | null>(null);

export function AdminPeriodProvider({ children }: { children: ReactNode }) {
  const [period, setPeriodState] = useState<AdminPeriod>(DEFAULT_PERIOD);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');

  const setPeriod = useCallback((next: AdminPeriod) => setPeriodState(next), []);
  const setRange = useCallback((nextStart: string, nextEnd: string) => {
    setStart(nextStart);
    setEnd(nextEnd);
  }, []);

  const value = useMemo<AdminPeriodValue>(() => {
    const complete = period !== 'custom' || Boolean(start && end);
    return {
      period,
      start,
      end,
      query:
        period === 'custom' && start && end
          ? { period: 'custom', start, end }
          : { period: period === 'custom' ? DEFAULT_PERIOD : period },
      customIncomplete: !complete,
      setPeriod,
      setRange,
    };
  }, [period, start, end, setPeriod, setRange]);

  return <AdminPeriodContext.Provider value={value}>{children}</AdminPeriodContext.Provider>;
}

export function useAdminPeriod(): AdminPeriodValue {
  const context = useContext(AdminPeriodContext);
  if (!context) {
    throw new Error('useAdminPeriod must be used inside an AdminPeriodProvider.');
  }
  return context;
}

/** Today, as YYYY-MM-DD in the browser's own timezone. */
function today(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

export interface PeriodFilterProps {
  className?: string;
}

export function PeriodFilter({ className }: PeriodFilterProps) {
  const { period, start, end, customIncomplete, setPeriod, setRange } = useAdminPeriod();
  const max = today();

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <div
        role="radiogroup"
        aria-label="Período"
        className="flex flex-wrap items-center gap-0.5 rounded-lg border border-line bg-surface-sunken p-0.5"
      >
        {ADMIN_PERIODS.map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={period === option}
            onClick={() => setPeriod(option)}
            className={cn(
              'rounded-md px-2.5 py-1 text-xs font-medium transition duration-150 ease-snap',
              period === option
                ? 'bg-accent-500/14 text-accent-400'
                : 'text-content-muted hover:bg-surface-overlay hover:text-content',
            )}
          >
            {option === 'custom' ? (
              <span className="flex items-center gap-1">
                <CalendarRange aria-hidden className="h-3.5 w-3.5" />
                {PERIOD_LABELS[option]}
              </span>
            ) : (
              PERIOD_LABELS[option]
            )}
          </button>
        ))}
      </div>

      {period === 'custom' ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <Input
            type="date"
            aria-label="Data inicial"
            value={start}
            max={end || max}
            onChange={(event) => setRange(event.target.value, end)}
            className="w-auto py-1 text-xs"
          />
          <span aria-hidden className="text-xs text-content-subtle">
            até
          </span>
          <Input
            type="date"
            aria-label="Data final"
            value={end}
            min={start || undefined}
            max={max}
            onChange={(event) => setRange(start, event.target.value)}
            className="w-auto py-1 text-xs"
          />
          {customIncomplete ? (
            <span role="status" className="text-2xs text-warning">
              Escolha as duas datas — mostrando {PERIOD_LABELS[DEFAULT_PERIOD].toLowerCase()}.
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
