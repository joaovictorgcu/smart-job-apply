import { Check, CircleHelp, TriangleAlert } from 'lucide-react';

import { joinTerms, scoreTone, verdictLabel } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Recommendation } from '@/types/api';

export interface MatchSummaryProps {
  recommendation: Recommendation | null | undefined;
  /** Compact drops the prose and shows only the two chip rows. */
  compact?: boolean;
  className?: string;
}

const TONE_TEXT: Record<string, string> = {
  success: 'text-success',
  accent: 'text-accent-400',
  warning: 'text-warning',
  danger: 'text-danger',
  info: 'text-info',
  neutral: 'text-content-subtle',
};

function Chip({ label, tone }: { label: string; tone: 'covered' | 'missing' }) {
  return (
    <li
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-2xs font-medium',
        tone === 'covered'
          ? 'border-success/35 bg-success/10 text-success'
          : 'border-warning/35 bg-warning/10 text-warning',
      )}
    >
      {tone === 'covered' ? (
        <Check aria-hidden className="h-3 w-3" />
      ) : (
        <TriangleAlert aria-hidden className="h-3 w-3" />
      )}
      {label}
    </li>
  );
}

/**
 * Why this vacancy, in two lists the reader can check against their own resume.
 *
 * The number is the least useful thing on the card: "82" is something you take
 * on faith. What you already have and what you do not is something you can
 * argue with, and it is the same intersection the adapted resume is built
 * from — so a term shown here as covered is a term emphasised there.
 *
 * Every sentence is composed here rather than sent by the backend, which keeps
 * the whole UI vocabulary in one language and one place.
 */
export function MatchSummary({ recommendation, compact = false, className }: MatchSummaryProps) {
  if (!recommendation) return null;

  const { covered, missing, verdict, score, covered_total, asked_total } = recommendation;

  if (!recommendation.has_evidence) {
    if (compact) return null;
    return (
      <p className={cn('flex items-start gap-1.5 text-xs text-content-subtle', className)}>
        <CircleHelp aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        Este anúncio não cita tecnologias específicas, então não dá para comparar com o seu
        currículo. Leia a descrição antes de decidir.
      </p>
    );
  }

  return (
    <div className={className}>
      {!compact ? (
        <p className={cn('text-sm font-semibold', TONE_TEXT[scoreTone(score)])}>
          {verdictLabel(verdict)}
        </p>
      ) : null}

      {covered.length > 0 || missing.length > 0 ? (
        <ul className={cn('flex flex-wrap gap-1.5', compact ? '' : 'mt-2')}>
          {covered.map((term) => (
            <Chip key={`covered-${term}`} label={term} tone="covered" />
          ))}
          {missing.map((term) => (
            <Chip key={`missing-${term}`} label={term} tone="missing" />
          ))}
        </ul>
      ) : null}

      {!compact ? (
        <div className="mt-3 space-y-1.5 text-xs leading-relaxed text-content-muted">
          <p>
            <span className="font-medium text-content">Por que esta vaga?</span>{' '}
            {covered.length > 0 ? (
              <>
                Você atende {covered_total} de {asked_total}{' '}
                {asked_total === 1 ? 'requisito citado' : 'requisitos citados'} e já tem experiência
                com {joinTerms(covered)}.
              </>
            ) : (
              <>
                Nenhum dos {asked_total}{' '}
                {asked_total === 1 ? 'requisito citado' : 'requisitos citados'} aparece no seu
                currículo.
              </>
            )}
          </p>
          {missing.length > 0 ? (
            <p>
              <span className="font-medium text-warning">Ponto de atenção:</span> a vaga pede{' '}
              {joinTerms(missing)}
              {missing.length === 1 ? ', que não está' : ', que não estão'} no seu perfil. Nada
              disso é acrescentado ao seu currículo.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
