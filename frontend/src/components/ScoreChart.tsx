import { BarChart3, LineChart as LineChartIcon } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { DailyCount, ScoreBucket } from '@/types/api';

import { EmptyState } from './EmptyState';
import { Card, CardHeader, Skeleton } from './primitives';

/* Colors are CSS custom properties, so both themes resolve from one declaration.
   A single hue per panel: each chart has one series, named by its own title. */
const SERIES = 'rgb(var(--accent-500))';
const GRID = 'rgb(var(--line))';
const AXIS_TEXT = 'rgb(var(--text-subtle))';

const AXIS_TICK = { fill: AXIS_TEXT, fontSize: 11 } as const;

interface TooltipEntry {
  value?: number | string;
}

interface ChartTooltipProps {
  active?: boolean;
  label?: string | number;
  payload?: TooltipEntry[];
  unit: string;
  labelPrefix?: string;
}

function ChartTooltip({ active, label, payload, unit, labelPrefix }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const value = payload[0]?.value;

  return (
    <div className="rounded-lg border border-line bg-surface-overlay px-2.5 py-1.5 shadow-lifted">
      <p className="text-2xs uppercase tracking-wider text-content-subtle">
        {labelPrefix ? `${labelPrefix} ` : ''}
        {label}
      </p>
      <p className="tabular text-sm font-semibold text-content">
        {typeof value === 'number' ? value : (value ?? 0)} {unit}
      </p>
    </div>
  );
}

/** Screen-reader equivalent of a plot: the same numbers, as a table. */
function DataTable({
  caption,
  rows,
  keyHeader,
  valueHeader,
}: {
  caption: string;
  rows: Array<{ key: string; value: number }>;
  keyHeader: string;
  valueHeader: string;
}) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">{keyHeader}</th>
          <th scope="col">{valueHeader}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key}>
            <th scope="row">{row.key}</th>
            <td>{row.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function weekdayLabel(isoDate: string): string {
  // Parse as local time: a bare YYYY-MM-DD is treated as UTC and can shift a day.
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString('en-US', { weekday: 'short' });
}

export interface ScoreChartProps {
  distribution: ScoreBucket[];
  daily: DailyCount[];
  isLoading?: boolean;
  className?: string;
}

export function ScoreChart({ distribution, daily, isLoading = false, className }: ScoreChartProps) {
  const hasDistribution = distribution.some((bucket) => bucket.count > 0);
  const hasDaily = daily.length > 0;

  const dailyData = daily.map((entry) => ({
    ...entry,
    day: weekdayLabel(entry.date),
  }));

  return (
    <div className={className}>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Match score distribution"
            description="How many analyzed jobs fall in each score band."
          />
          <div className="px-2 py-4">
            {isLoading ? (
              <Skeleton className="mx-3 h-[220px]" />
            ) : hasDistribution ? (
              <>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={distribution} barCategoryGap="22%" margin={{ top: 4, right: 12, bottom: 0, left: -18 }}>
                    <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                    <XAxis
                      dataKey="label"
                      tick={AXIS_TICK}
                      tickLine={false}
                      axisLine={{ stroke: GRID }}
                    />
                    <YAxis
                      tick={AXIS_TICK}
                      tickLine={false}
                      axisLine={false}
                      allowDecimals={false}
                      width={44}
                    />
                    <Tooltip
                      cursor={{ fill: 'rgb(var(--accent-500) / 0.08)' }}
                      content={<ChartTooltip unit="jobs" labelPrefix="Score" />}
                    />
                    <Bar dataKey="count" fill={SERIES} radius={[4, 4, 0, 0]} maxBarSize={56} />
                  </BarChart>
                </ResponsiveContainer>
                <DataTable
                  caption="Match score distribution"
                  keyHeader="Score band"
                  valueHeader="Jobs"
                  rows={distribution.map((bucket) => ({ key: bucket.label, value: bucket.count }))}
                />
              </>
            ) : (
              <EmptyState
                compact
                icon={BarChart3}
                title="No scored jobs yet"
                description="Run a search with AI analysis on and the score bands will fill in here."
              />
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Applications submitted, last 7 days"
            description="Counts only applications you approved and submitted."
          />
          <div className="px-2 py-4">
            {isLoading ? (
              <Skeleton className="mx-3 h-[220px]" />
            ) : hasDaily ? (
              <>
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={dailyData} margin={{ top: 6, right: 14, bottom: 0, left: -18 }}>
                    <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="day" tick={AXIS_TICK} tickLine={false} axisLine={{ stroke: GRID }} />
                    <YAxis
                      tick={AXIS_TICK}
                      tickLine={false}
                      axisLine={false}
                      allowDecimals={false}
                      width={44}
                    />
                    <Tooltip
                      cursor={{ stroke: GRID, strokeWidth: 1 }}
                      content={<ChartTooltip unit="submitted" />}
                    />
                    <Line
                      type="monotone"
                      dataKey="count"
                      stroke={SERIES}
                      strokeWidth={2}
                      dot={{ r: 3, fill: SERIES, strokeWidth: 0 }}
                      activeDot={{ r: 5, fill: SERIES, stroke: 'rgb(var(--surface-raised))', strokeWidth: 2 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
                <DataTable
                  caption="Applications submitted per day, last 7 days"
                  keyHeader="Date"
                  valueHeader="Submitted"
                  rows={daily.map((entry) => ({ key: entry.date, value: entry.count }))}
                />
              </>
            ) : (
              <EmptyState
                compact
                icon={LineChartIcon}
                title="Nothing submitted yet"
                description="Approved submissions will show up here day by day."
              />
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
