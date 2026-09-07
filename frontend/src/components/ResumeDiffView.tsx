import { ArrowUp, Check, Minus, MoveRight, Plus, TriangleAlert } from 'lucide-react';

import { Note, SectionLabel } from '@/components/primitives';
import { badgeClass } from '@/lib/format';
import { diffResume } from '@/lib/resumeDiff';
import type { ExperienceDiff } from '@/lib/resumeDiff';
import type { CVChange, ResumeDocument } from '@/types/api';

interface ResumeDiffViewProps {
  base: ResumeDocument;
  document: ResumeDocument;
  /** The derivation's own account of what it did and why. */
  changes: CVChange[];
}

function Sentence({ label, text }: { label: string; text: string | null }) {
  return (
    <p className="text-xs leading-relaxed">
      <span className="text-2xs uppercase tracking-wider text-content-subtle">{label} </span>
      <span className="text-content-muted">{text || '—'}</span>
    </p>
  );
}

function ExperienceRow({ diff }: { diff: ExperienceDiff }) {
  return (
    <li className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs font-semibold text-content">
          {diff.role} — {diff.company}
        </p>
        {diff.movedUpBy > 0 ? (
          <span className={badgeClass('accent')}>
            <ArrowUp aria-hidden className="h-3 w-3" />
            {diff.basePosition}ª → {diff.position}ª
          </span>
        ) : diff.movedUpBy < 0 ? (
          <span className={badgeClass('neutral')}>
            {diff.basePosition}ª → {diff.position}ª
          </span>
        ) : null}
      </div>

      {diff.focus.length > 0 ? (
        <p className="mt-1.5 text-2xs text-accent-400">
          Priorizado para esta vaga: {diff.focus.join(' · ')}
        </p>
      ) : null}

      {diff.summaryChanged ? (
        <div className="mt-2 space-y-1">
          <Sentence label="Principal" text={diff.baseSummary} />
          <Sentence label="Nesta candidatura" text={diff.summary} />
        </div>
      ) : null}

      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-2xs text-content-subtle">
        {diff.highlightsReordered ? (
          <li className="inline-flex items-center gap-1">
            <MoveRight aria-hidden className="h-3 w-3" />
            realizações reordenadas
          </li>
        ) : null}
        {diff.highlightsHidden > 0 ? (
          <li className="inline-flex items-center gap-1">
            <Minus aria-hidden className="h-3 w-3" />
            {diff.highlightsHidden}{' '}
            {diff.highlightsHidden === 1 ? 'realização recolhida' : 'realizações recolhidas'}
          </li>
        ) : null}
        {diff.technologiesPromoted.length > 0 ? (
          <li className="inline-flex items-center gap-1">
            <ArrowUp aria-hidden className="h-3 w-3" />
            {diff.technologiesPromoted.join(', ')} à frente
          </li>
        ) : null}
        {diff.projectsReordered ? (
          <li className="inline-flex items-center gap-1">
            <MoveRight aria-hidden className="h-3 w-3" />
            projetos reordenados
          </li>
        ) : null}
        {diff.technologiesAdded.length > 0 ? (
          <li className="inline-flex items-center gap-1 text-warning">
            <Plus aria-hidden className="h-3 w-3" />
            {diff.technologiesAdded.join(', ')} — não está no currículo principal
          </li>
        ) : null}
        {diff.technologiesRemoved.length > 0 ? (
          <li className="inline-flex items-center gap-1">
            <Minus aria-hidden className="h-3 w-3" />
            {diff.technologiesRemoved.join(', ')} omitidas
          </li>
        ) : null}
        {diff.highlightsAdded.length > 0 ? (
          <li className="inline-flex items-center gap-1 text-warning">
            <Plus aria-hidden className="h-3 w-3" />
            {diff.highlightsAdded.length}{' '}
            {diff.highlightsAdded.length === 1 ? 'realização escrita' : 'realizações escritas'} por
            você
          </li>
        ) : null}
      </ul>
    </li>
  );
}

/**
 * The difference between this application's resume and the master it came from.
 *
 * Compared against the snapshot the version was built on, not the live profile:
 * the question this answers is "how does this application present me
 * differently", and diffing against a profile edited afterwards would credit
 * the version with changes it never made. Whether the master has moved since is
 * a separate flag, shown as a stale note by the panel.
 */
export function ResumeDiffView({ base, document, changes }: ResumeDiffViewProps) {
  const diff = diffResume(base, document);
  const changed = diff.experiences.filter((item) => item.changed);

  if (!diff.hasChanges) {
    return (
      <Note tone="neutral" icon={<Check aria-hidden className="h-3.5 w-3.5" />}>
        Esta versão está idêntica ao currículo principal: a vaga não tem interseção com as suas
        tecnologias e competências, então nada foi priorizado. Nada foi escondido.
      </Note>
    );
  }

  return (
    <div className="space-y-4">
      <Note tone="accent">
        {diff.changedCount}{' '}
        {diff.changedCount === 1 ? 'diferença' : 'diferenças'} em relação ao currículo principal.
        Só a ordem e a redação mudam — cargo, empresa e período são sempre os mesmos.
      </Note>

      {diff.summaryChanged ? (
        <div>
          <SectionLabel>Resumo profissional</SectionLabel>
          <div className="mt-1.5 space-y-1 rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
            <Sentence label="Principal" text={diff.baseSummary} />
            <Sentence label="Nesta candidatura" text={diff.summary} />
          </div>
        </div>
      ) : null}

      {diff.skillsPromoted.length > 0 || diff.technologiesPromoted.length > 0 ? (
        <div>
          <SectionLabel>Priorizado no topo</SectionLabel>
          <ul className="mt-1.5 space-y-1 text-xs text-content-muted">
            {diff.skillsPromoted.length > 0 ? (
              <li>Competências: {diff.skillsPromoted.join(', ')}</li>
            ) : null}
            {diff.technologiesPromoted.length > 0 ? (
              <li>Tecnologias: {diff.technologiesPromoted.join(', ')}</li>
            ) : null}
          </ul>
        </div>
      ) : null}

      {changed.length > 0 ? (
        <div>
          <SectionLabel>Experiências</SectionLabel>
          <ul className="mt-2 space-y-2">
            {changed.map((item) => (
              <ExperienceRow key={item.key} diff={item} />
            ))}
          </ul>
        </div>
      ) : null}

      {diff.droppedExperiences.length > 0 ? (
        <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
          Fora desta versão: {diff.droppedExperiences.join('; ')}. Um histórico com lacunas chama
          atenção — considere manter a experiência e apenas recolher os detalhes.
        </Note>
      ) : null}

      {changes.length > 0 ? (
        <div>
          <SectionLabel>Por que ficou assim</SectionLabel>
          <ul className="mt-2 space-y-2">
            {changes.map((change, index) => (
              <li key={`${change.section}-${index}`} className="text-xs leading-relaxed">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className={badgeClass('neutral')}>{change.action}</span>
                  <span className="font-medium text-content">{change.section}</span>
                </div>
                <p className="mt-0.5 text-content-muted">{change.detail}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
