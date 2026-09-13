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
 * The band, carried by a rule under the numeral rather than by a filled chip.
 *
 * This used to be the most saturated element on the page, on the reasoning that
 * the eye should land on it first. That fought the card it sits in:
 * `MatchSummary` exists because "86" is a number you take on faith, while the
 * requirements you meet and the ones you do not are something you can check.
 * Shouting the number put the least checkable thing first.
 *
 * So it stays legible and stays banded — a reader still sees at a glance which
 * range a vacancy falls in — without outranking the evidence beside it.
 */
const TONE: Record<ToneName, string> = {
  success: 'border-b-success',
  accent: 'border-b-accent-500',
  warning: 'border-b-warning',
  danger: 'border-b-danger',
  info: 'border-b-info',
  neutral: 'border-b-line-strong',
};

export function ScoreBadge({ score, size = 'md', className }: ScoreBadgeProps) {
  const unscored = score === null || score === undefined;
  const value = unscored ? 0 : Math.round(score);

  return (
    <span
      aria-label={unscored ? 'Ainda não comparada com o seu perfil' : `Aderência ao seu perfil: ${value} de 100`}
      title={
        unscored
          ? 'Ainda não comparada com o seu perfil'
          : `Aderência ao seu perfil: ${value}/100`
      }
      className={cn(
        'tabular inline-flex select-none items-center justify-center border-b-2 font-semibold text-content',
        SIZE[size],
        unscored ? 'border-b-dashed border-b-line-strong text-content-subtle' : TONE[scoreTone(value)],
        className,
      )}
    >
      {unscored ? '–' : value}
    </span>
  );
}
