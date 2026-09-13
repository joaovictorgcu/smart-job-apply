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

/**
 * Coverage as a bar, because coverage is a proportion.
 *
 * "7 de 9" is the honest shape of this number and a bar is how a proportion is
 * read at a glance. The filled part is the evidence; the rest is what the
 * posting asked for and did not find. No colour: on a list where every card
 * carries one of these, hue would rank the vacancies before the reader does.
 */
function Coverage({ covered, asked }: { covered: number; asked: number }) {
  const ratio = asked > 0 ? Math.min(1, covered / asked) : 0;
  return (
    <p className="flex items-center gap-2 text-xs text-content-muted">
      <span
        aria-hidden
        className="h-1 w-20 shrink-0 overflow-hidden rounded-full bg-line-strong/50"
      >
        <span
          className="block h-full rounded-full bg-content-muted"
          style={{ width: `${ratio * 100}%` }}
        />
      </span>
      {covered} de {asked} {asked === 1 ? 'requisito citado' : 'requisitos citados'}
    </p>
  );
}

/**
 * One line per list, terms separated by commas.
 *
 * They were pills — same radius, same weight and nearly the same green as the
 * "Candidatada" status beside them, so status, channel, work model and evidence
 * all read as one undifferentiated stripe. As running text they are faster to
 * read, wrap properly, and stop competing with the state of the application.
 */
function TermLine({ lead, terms, tone }: { lead: string; terms: string[]; tone: 'has' | 'lacks' }) {
  if (terms.length === 0) return null;
  return (
    <p className="text-xs leading-relaxed">
      <span className="inline-flex items-center gap-1 font-medium text-content-muted">
        {tone === 'has' ? (
          <Check aria-hidden className="h-3 w-3 text-success" />
        ) : (
          <TriangleAlert aria-hidden className="h-3 w-3 text-warning" />
        )}
        {lead}
      </span>{' '}
      <span className={tone === 'has' ? 'text-content' : 'text-content-muted'}>
        {terms.join(', ')}
      </span>
    </p>
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
        <div className={cn('space-y-1', compact ? '' : 'mt-2')}>
          {asked_total > 0 ? <Coverage covered={covered_total} asked={asked_total} /> : null}
          <TermLine lead="tem" terms={covered} tone="has" />
          <TermLine lead="falta" terms={missing} tone="lacks" />
        </div>
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
