import { ArrowRight, Check, Info, ShieldAlert } from 'lucide-react';

import { Note, SectionLabel } from '@/components/primitives';
import { cn } from '@/lib/utils';
import type { ResumeComparison } from '@/types/api';

export interface ResumeComparisonPanelProps {
  comparison: ResumeComparison | null | undefined;
  className?: string;
}

function Counter({
  value,
  label,
  tone = 'neutral',
}: {
  value: number;
  label: string;
  tone?: 'neutral' | 'good' | 'bad';
}) {
  return (
    <div className="min-w-[7rem] flex-1">
      <p
        className={cn(
          'tabular text-lg font-semibold leading-none',
          tone === 'good' && 'text-success',
          tone === 'bad' && 'text-danger',
          tone === 'neutral' && 'text-content',
        )}
      >
        {value}
      </p>
      <p className="mt-1 text-2xs leading-snug text-content-subtle">{label}</p>
    </div>
  );
}

/**
 * The master resume against the one this vacancy gets.
 *
 * The claim worth checking before approving is not "it was adapted" — it is
 * **how little** was adapted, because a copy that reads as a different document
 * is a copy the candidate cannot defend in an interview. So the four counters
 * lead, and the itemised moves follow for anyone who wants to see them.
 *
 * The fourth counter is the one with teeth: it is the invention guard's output,
 * measured over this document against the candidate's own words. Zero is a
 * result. Anything else is a stop sign, not a footnote.
 */
export function ResumeComparisonPanel({ comparison, className }: ResumeComparisonPanelProps) {
  if (!comparison) return null;

  if (!comparison.is_comparable) {
    return (
      <Note tone="neutral" icon={<Info aria-hidden className="h-3.5 w-3.5" />} className={className}>
        Você editou o seu currículo principal depois que esta versão foi criada, então comparar os
        dois mostraria as suas próprias edições como se fossem adaptações. Adapte de novo para ver a
        comparação.
      </Note>
    );
  }

  const { moves, highlighted_technologies: highlighted, invented } = comparison;
  const relevantMoves = moves.filter((move) => move.from_position !== move.to_position);

  return (
    <div className={className}>
      <SectionLabel>Currículo original vs. currículo para esta vaga</SectionLabel>

      <div className="mt-2 flex flex-wrap gap-4 rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
        <Counter value={comparison.changes_total} label="alterações no total" />
        <Counter value={highlighted.length} label="tecnologias destacadas" />
        <Counter value={comparison.sections_adjusted} label="trechos reordenados" />
        <Counter
          value={invented.length}
          label="informações inventadas"
          tone={invented.length === 0 ? 'good' : 'bad'}
        />
      </div>

      {invented.length > 0 ? (
        <Note
          tone="danger"
          className="mt-3"
          icon={<ShieldAlert aria-hidden className="h-3.5 w-3.5" />}
        >
          <strong>{invented.join(', ')}</strong>{' '}
          {invented.length === 1 ? 'aparece' : 'aparecem'} nesta versão mas não no seu currículo
          principal. Confira antes de aprovar — nada deveria estar aqui que você não tenha escrito.
        </Note>
      ) : (
        <p className="mt-2 flex items-center gap-1.5 text-2xs text-content-subtle">
          <Check aria-hidden className="h-3 w-3 text-success" />
          Tudo nesta versão veio do seu currículo principal. Só a ordem e o destaque mudaram.
        </p>
      )}

      {relevantMoves.length > 0 ? (
        <div className="mt-3">
          <p className="text-2xs font-medium uppercase tracking-wider text-content-subtle">
            O que mudou de lugar
          </p>
          <ul className="mt-1.5 space-y-1.5">
            {relevantMoves.map((move) => (
              <li
                key={`${move.experience_id}-${move.to_position}`}
                className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-content-muted"
              >
                <span className="tabular inline-flex items-center gap-1 text-content-subtle">
                  {move.from_position}ª
                  <ArrowRight aria-hidden className="h-3 w-3" />
                  {move.to_position}ª
                </span>
                <span className="font-medium text-content">
                  {move.role} — {move.company}
                </span>
                {move.matched_terms.length > 0 ? (
                  <span className="text-content-subtle">
                    por causa de {move.matched_terms.slice(0, 3).join(', ')}
                  </span>
                ) : null}
                {move.promoted_bullets > 0 ? (
                  <span className="text-content-subtle">
                    · {move.promoted_bullets}{' '}
                    {move.promoted_bullets === 1 ? 'item subiu' : 'itens subiram'}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {highlighted.length > 0 ? (
        <div className="mt-3">
          <p className="text-2xs font-medium uppercase tracking-wider text-content-subtle">
            Ganharam destaque
          </p>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {highlighted.map((term) => (
              <li
                key={term}
                className="inline-flex items-center rounded-full border border-accent-500/35 bg-accent-500/12 px-2 py-0.5 text-2xs font-medium text-accent-400"
              >
                {term}
              </li>
            ))}
          </ul>
          <p className="hint mt-1.5">
            Já estavam no seu currículo — só vieram para a frente da lista.
          </p>
        </div>
      ) : null}

      {comparison.changes_total === 0 ? (
        <p className="mt-3 text-xs leading-relaxed text-content-muted">
          Esta vaga não pediu nada que justificasse mexer na ordem, então esta versão é o seu
          currículo principal como ele está.
        </p>
      ) : null}
    </div>
  );
}
