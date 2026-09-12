import { LineChart as LineChartIcon } from 'lucide-react';
import { useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader, Skeleton } from '@/components/primitives';
import { cn } from '@/lib/utils';
import type { GrowthPoint } from '@/types/api';

import { GROWTH_SERIES } from './labels';

/* Same convention as ScoreChart: colours are CSS variables, so one declaration
   serves both themes — and inside `.admin-scope` the accent ramp is violet, which
   is why this chart matches the panel without naming a colour. */
const SERIES = 'rgb(var(--accent-500))';
const GRID = 'rgb(var(--line))';
const AXIS_TICK = { fill: 'rgb(var(--text-subtle))', fontSize: 11 } as const;

type SeriesKey = (typeof GROWTH_SERIES)[number]['key'];

function dayLabel(isoDate: string): string {
  // Parsed as local time: a bare YYYY-MM-DD is read as UTC and can shift a day.
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

interface TooltipProps {
  active?: boolean;
  label?: string | number;
  payload?: Array<{ value?: number | string }>;
  unit: string;
}

function ChartTooltip({ active, label, payload, unit }: TooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface-overlay px-2.5 py-1.5 shadow-lifted">
      <p className="text-2xs uppercase tracking-wider text-content-subtle">{label}</p>
      <p className="tabular text-sm font-semibold text-content">
        {payload[0]?.value ?? 0} {unit}
      </p>
    </div>
  );
}

export interface GrowthChartProps {
  growth?: GrowthPoint[];
  isLoading?: boolean;
  className?: string;
}

/**
 * Growth over the selected period, one series at a time.
 *
 * Three series at once would need three axes to be readable — users grow by
 * ones while jobs grow by hundreds — so the metric is a switch rather than a
 * legend. The screen-reader table always carries all three columns, which is
 * also the "Data | Usuários | Vagas | Candidaturas" table the brief asked for.
 */
export function GrowthChart({ growth, isLoading = false, className }: GrowthChartProps) {
  const [series, setSeries] = useState<SeriesKey>('applications');
  const points = growth ?? [];
  const active = GROWTH_SERIES.find((entry) => entry.key === series) ?? GROWTH_SERIES[2];
  const hasData = points.some((point) => point[series] > 0);
  const data = points.map((point) => ({ ...point, day: dayLabel(point.date) }));

  return (
    <Card className={className}>
      <CardHeader
        title="Crescimento no período"
        description="Um ponto por dia. Um dia sem atividade aparece como zero, não como lacuna."
        actions={
          <div
            role="radiogroup"
            aria-label="Série do gráfico"
            className="flex items-center gap-0.5 rounded-lg border border-line bg-surface-sunken p-0.5"
          >
            {GROWTH_SERIES.map((entry) => (
              <button
                key={entry.key}
                type="button"
                role="radio"
                aria-checked={series === entry.key}
                onClick={() => setSeries(entry.key)}
                className={cn(
                  'rounded-md px-2.5 py-1 text-xs font-medium transition duration-150 ease-snap',
                  series === entry.key
                    ? 'bg-accent-500/14 text-accent-400'
                    : 'text-content-muted hover:bg-surface-overlay hover:text-content',
                )}
              >
                {entry.label}
              </button>
            ))}
          </div>
        }
      />

      <div className="px-2 py-4">
        {isLoading ? (
          <Skeleton className="mx-3 h-[240px]" />
        ) : hasData ? (
          <>
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={data} margin={{ top: 6, right: 14, bottom: 0, left: -18 }}>
                <defs>
                  <linearGradient id="admin-growth-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={SERIES} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={SERIES} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="day"
                  tick={AXIS_TICK}
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                  minTickGap={16}
                />
                <YAxis
                  tick={AXIS_TICK}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                  width={44}
                />
                <Tooltip
                  cursor={{ stroke: GRID, strokeWidth: 1 }}
                  content={<ChartTooltip unit={active.label.toLowerCase()} />}
                />
                <Area
                  type="monotone"
                  dataKey={series}
                  stroke={SERIES}
                  strokeWidth={2}
                  fill="url(#admin-growth-fill)"
                  dot={false}
                  activeDot={{ r: 4, fill: SERIES, stroke: 'rgb(var(--surface-raised))', strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>

            {/* The plot's equivalent as data, for screen readers. */}
            <table className="sr-only">
              <caption>Crescimento por dia no período selecionado</caption>
              <thead>
                <tr>
                  <th scope="col">Data</th>
                  <th scope="col">Usuários</th>
                  <th scope="col">Vagas</th>
                  <th scope="col">Candidaturas</th>
                </tr>
              </thead>
              <tbody>
                {points.map((point) => (
                  <tr key={point.date}>
                    <th scope="row">{point.date}</th>
                    <td>{point.users}</td>
                    <td>{point.jobs}</td>
                    <td>{point.applications}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <EmptyState
            compact
            icon={LineChartIcon}
            title={`Nenhum registro de ${active.label.toLowerCase()} neste período`}
            description="Escolha um período maior ou outra série para ver a evolução."
          />
        )}
      </div>
    </Card>
  );
}
