import { scoreTone, type ToneName } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface ScoreBadgeProps {
  score: number | null | undefined;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const SIZE: Record<NonNullable<ScoreBadgeProps['size']>, string> = {
  sm: 'h-7 min-w-[1.75rem] px-1.5 text-xs',
  md: 'h-10 min-w-[2.5rem] px-2 text-md',
  lg: 'h-14 min-w-[3.5rem] px-3 text-2xl',
};

/**
 * The AI verdict is deliberately the most saturated element on a page, so the
 * eye lands on it before anything else.
 */
const TONE: Record<ToneName, string> = {
  success: 'border-success/40 bg-success/12 text-success',
  accent: 'border-accent-500/40 bg-accent-500/12 text-accent-400',
  warning: 'border-warning/40 bg-warning/12 text-warning',
  danger: 'border-danger/40 bg-danger/12 text-danger',
  info: 'border-info/40 bg-info/12 text-info',
  neutral: 'border-line bg-surface-sunken text-content-subtle',
};

export function ScoreBadge({ score, size = 'md', className }: ScoreBadgeProps) {
  const unscored = score === null || score === undefined;
  const value = unscored ? 0 : Math.round(score);

  return (
    <span
      aria-label={unscored ? 'Ainda não analisada' : `Nota de aderência da IA ${value} de 100`}
      title={unscored ? 'Ainda não analisada pela IA' : `Nota de aderência da IA: ${value}/100`}
      className={cn(
        'tabular inline-flex select-none items-center justify-center rounded-xl border font-semibold',
        SIZE[size],
        unscored ? 'border-dashed border-line-strong bg-transparent text-content-subtle' : TONE[scoreTone(value)],
        className,
      )}
    >
      {unscored ? '–' : value}
    </span>
  );
}
