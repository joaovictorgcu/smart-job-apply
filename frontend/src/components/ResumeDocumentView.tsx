import { Building2, GraduationCap, Sparkles, Target } from 'lucide-react';

import { EmptyState } from '@/components/EmptyState';
import { SectionLabel } from '@/components/primitives';
import { cn } from '@/lib/utils';
import type { ResumeDocument, ResumeExperience, ResumeProject } from '@/types/api';

interface ResumeDocumentViewProps {
  document: ResumeDocument;
  /**
   * The posting's terms, marked in accent wherever they appear. Passed for an
   * application's version and left out for the master — the master has no
   * posting to be emphasized for, and pretending otherwise would blur the one
   * distinction this screen exists to make.
   */
  highlight?: string[];
  className?: string;
}

function Terms({ terms, highlight }: { terms: string[]; highlight: Set<string> }) {
  if (terms.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-1.5">
      {terms.map((term) => (
        <li
          key={term}
          className={cn(
            'rounded-full border px-2 py-0.5 text-2xs font-medium',
            highlight.has(term.toLowerCase())
              ? 'border-accent-500/35 bg-accent-500/12 text-accent-400'
              : 'border-line bg-surface-sunken text-content-muted',
          )}
        >
          {term}
        </li>
      ))}
    </ul>
  );
}

function Project({ project, highlight }: { project: ResumeProject; highlight: Set<string> }) {
  return (
    <li className="rounded-lg border border-line bg-surface-sunken px-3 py-2">
      <p className="text-xs font-semibold text-content">{project.name}</p>
      {project.description ? (
        <p className="mt-0.5 text-xs leading-relaxed text-content-muted">{project.description}</p>
      ) : null}
      {project.outcome ? (
        <p className="mt-0.5 text-2xs text-content-subtle">Resultado: {project.outcome}</p>
      ) : null}
      {project.technologies.length > 0 ? (
        <div className="mt-1.5">
          <Terms terms={project.technologies} highlight={highlight} />
        </div>
      ) : null}
    </li>
  );
}

function Experience({
  experience,
  highlight,
}: {
  experience: ResumeExperience;
  highlight: Set<string>;
}) {
  const period = experience.end ? `${experience.start} — ${experience.end}` : experience.start;

  return (
    <li className="relative pl-5">
      <span
        aria-hidden
        className="absolute left-0 top-1.5 h-[9px] w-[9px] rounded-full bg-accent-500 ring-2 ring-surface-raised"
      />
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-sm font-semibold leading-snug text-content">
          {experience.role} — {experience.company}
        </p>
        <p className="tabular shrink-0 font-mono text-2xs text-content-subtle">
          {period}
          {experience.location ? ` · ${experience.location}` : ''}
        </p>
      </div>

      {experience.focus.length > 0 ? (
        <p className="mt-1 inline-flex flex-wrap items-center gap-1.5 text-2xs text-accent-400">
          <Target aria-hidden className="h-3 w-3" />
          <span className="font-medium">Priorizado aqui:</span>
          <span>{experience.focus.join(' · ')}</span>
        </p>
      ) : null}

      {experience.summary ? (
        <p className="mt-1 text-xs leading-relaxed text-content-muted">{experience.summary}</p>
      ) : null}

      {experience.highlights.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {experience.highlights.map((item) => (
            <li key={item.text} className="text-xs leading-relaxed text-content-muted">
              <span className="text-content-subtle">— </span>
              {item.text}
              {item.impact ? (
                <span className="ml-1 font-medium text-success">({item.impact})</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      {experience.technologies.length > 0 ? (
        <div className="mt-2">
          <Terms terms={experience.technologies} highlight={highlight} />
        </div>
      ) : null}

      {experience.projects.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {experience.projects.map((project) => (
            <Project key={project.name} project={project} highlight={highlight} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/**
 * Renders a resume document — the master or one application's version.
 *
 * Deliberately one component for both. The two are the same kind of thing, and
 * the only honest way to let someone compare them is to show them in the same
 * shape; a separate "version" renderer would make every difference look like a
 * rendering difference.
 */
export function ResumeDocumentView({
  document,
  highlight,
  className,
}: ResumeDocumentViewProps) {
  const highlighted = new Set((highlight ?? []).map((term) => term.toLowerCase()));

  const isEmpty =
    document.experiences.length === 0 &&
    document.skills.length === 0 &&
    document.technologies.length === 0 &&
    document.projects.length === 0;

  if (isEmpty) {
    return (
      <EmptyState
        compact
        icon={Building2}
        title="Nenhuma experiência estruturada"
        description="Adicione experiências no seu perfil para que cada candidatura possa priorizá-las."
      />
    );
  }

  return (
    <div className={cn('space-y-4', className)}>
      {document.headline ? (
        <p className="text-sm font-semibold text-content">{document.headline}</p>
      ) : null}
      {document.summary ? (
        <p className="text-xs leading-relaxed text-content-muted">{document.summary}</p>
      ) : null}

      {document.skills.length > 0 ? (
        <div>
          <SectionLabel>Competências</SectionLabel>
          <div className="mt-1.5">
            <Terms terms={document.skills} highlight={highlighted} />
          </div>
        </div>
      ) : null}

      {document.technologies.length > 0 ? (
        <div>
          <SectionLabel>Tecnologias</SectionLabel>
          <div className="mt-1.5">
            <Terms terms={document.technologies} highlight={highlighted} />
          </div>
        </div>
      ) : null}

      {document.experiences.length > 0 ? (
        <div>
          <SectionLabel>Experiência</SectionLabel>
          <ol className="relative mt-2.5 space-y-5">
            <span aria-hidden className="absolute inset-y-1 left-1 w-px bg-line" />
            {document.experiences.map((experience) => (
              <Experience
                key={experience.key}
                experience={experience}
                highlight={highlighted}
              />
            ))}
          </ol>
        </div>
      ) : null}

      {document.projects.length > 0 ? (
        <div>
          <SectionLabel>Projetos</SectionLabel>
          <ul className="mt-2 space-y-2">
            {document.projects.map((project) => (
              <Project key={project.name} project={project} highlight={highlighted} />
            ))}
          </ul>
        </div>
      ) : null}

      {document.education.length > 0 ? (
        <div>
          <SectionLabel>Formação</SectionLabel>
          <ul className="mt-2 space-y-1.5">
            {document.education.map((entry) => (
              <li
                key={`${entry.institution}-${entry.degree}`}
                className="flex items-start gap-2 text-xs leading-relaxed text-content-muted"
              >
                <GraduationCap aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-content-subtle" />
                <span>
                  {entry.degree ? `${entry.degree}, ` : ''}
                  {entry.institution}
                  {entry.end ? ` (${entry.start} — ${entry.end})` : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {document.certifications.length > 0 ? (
        <div>
          <SectionLabel>Certificações</SectionLabel>
          <ul className="mt-2 space-y-1">
            {document.certifications.map((item) => (
              <li
                key={item}
                className="flex items-start gap-2 text-xs leading-relaxed text-content-muted"
              >
                <Sparkles aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-400" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
