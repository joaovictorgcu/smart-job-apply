import { ArrowDown, ArrowUp, Lock, RotateCcw, Save } from 'lucide-react';
import { useState } from 'react';

import { Drawer } from '@/components/Drawer';
import { Button, Field, Note, SectionLabel, Textarea } from '@/components/primitives';
import { TagEditor } from '@/components/TagEditor';
import { cn } from '@/lib/utils';
import type { ResumeDocument, ResumeExperience, ResumeHighlight } from '@/types/api';

interface ResumeVersionEditorProps {
  open: boolean;
  onClose: () => void;
  /** The version being edited. */
  document: ResumeDocument;
  /** The master snapshot: the source of every fact this editor may present. */
  base: ResumeDocument;
  focus: string[];
  saving: boolean;
  error: string | null;
  onSave: (document: ResumeDocument) => void;
}

function move<T>(items: T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length) return items;
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

/**
 * Edit the resume one application presents.
 *
 * What is editable is the whole point: emphasis and wording — the summary, which
 * achievements appear and in what order, which technologies lead. Company, role
 * and period are shown locked, because this document is a *presentation* of a
 * history that lives on the profile, and the server refuses an edit that
 * disagrees with it. Fixing a fact belongs in Perfil, and the note says so.
 *
 * Achievements are chosen from the master's own list rather than typed freely,
 * so re-emphasizing cannot slide into inventing. The text of one can still be
 * rewritten — that is rephrasing, and the invention guard checks the result.
 */
export function ResumeVersionEditor({
  open,
  onClose,
  document,
  base,
  focus,
  saving,
  error,
  onSave,
}: ResumeVersionEditorProps) {
  // Seeded once, on mount. The panel mounts this only while the drawer is open,
  // so closing it discards the draft: reopening has to show the saved version,
  // not the edits someone abandoned by pressing Cancel.
  const [draft, setDraft] = useState<ResumeDocument>(document);

  const patchExperience = (key: string, partial: Partial<ResumeExperience>) =>
    setDraft((current) => ({
      ...current,
      experiences: current.experiences.map((experience) =>
        experience.key === key ? { ...experience, ...partial } : experience,
      ),
    }));

  const baseExperience = (key: string) => base.experiences.find((item) => item.key === key);

  const toggleHighlight = (
    experience: ResumeExperience,
    highlight: ResumeHighlight,
    include: boolean,
  ) => {
    const kept = experience.highlights.filter((item) => item.text !== highlight.text);
    patchExperience(experience.key, {
      highlights: include ? [...kept, highlight] : kept,
    });
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="max-w-2xl"
      title="Editar o currículo desta candidatura"
      description="As mudanças ficam só aqui. O seu currículo principal não muda."
      footer={
        <>
          <Button onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button
            variant="primary"
            loading={saving}
            onClick={() => onSave(draft)}
            icon={<Save aria-hidden className="h-4 w-4" />}
          >
            Salvar esta versão
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {error ? <Note tone="danger">{error}</Note> : null}

        <Note tone="neutral" icon={<Lock aria-hidden className="h-3.5 w-3.5" />}>
          Cargo, empresa e período vêm do currículo principal e não são editáveis aqui — esta
          versão reorganiza e reescreve o que você já viveu, nunca os fatos. Se um fato mudou,
          corrija em <span className="font-medium">Perfil</span> e gere a versão de novo.
        </Note>

        <Field
          label="Resumo profissional nesta candidatura"
          htmlFor="version-summary"
          hint="É a primeira coisa que um recrutador lê."
        >
          <Textarea
            id="version-summary"
            rows={3}
            value={draft.summary ?? ''}
            disabled={saving}
            onChange={(event) =>
              setDraft((current) => ({ ...current, summary: event.target.value }))
            }
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Competências"
            htmlFor="version-skills"
            hint="A ordem importa: as primeiras são as que aparecem."
          >
            <TagEditor
              id="version-skills"
              tags={draft.skills}
              disabled={saving}
              highlight={focus}
              placeholder="Arquitetura de software…"
              onChange={(skills) => setDraft((current) => ({ ...current, skills }))}
            />
          </Field>
          <Field label="Tecnologias" htmlFor="version-technologies">
            <TagEditor
              id="version-technologies"
              tags={draft.technologies}
              disabled={saving}
              highlight={focus}
              placeholder=".NET 8, React…"
              onChange={(technologies) =>
                setDraft((current) => ({ ...current, technologies }))
              }
            />
          </Field>
        </div>

        <div className="space-y-4">
          <SectionLabel>Experiências</SectionLabel>
          {draft.experiences.map((experience, index) => {
            const source = baseExperience(experience.key);
            const included = new Set(experience.highlights.map((item) => item.text));
            const available = source?.highlights ?? experience.highlights;

            return (
              <section
                key={experience.key}
                className="rounded-xl border border-line bg-surface-sunken px-3.5 py-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-content">
                      {experience.role} — {experience.company}
                    </p>
                    <p className="tabular font-mono text-2xs text-content-subtle">
                      {experience.end
                        ? `${experience.start} — ${experience.end}`
                        : experience.start}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={saving || index === 0}
                      aria-label={`Subir ${experience.company}`}
                      onClick={() =>
                        setDraft((current) => ({
                          ...current,
                          experiences: move(current.experiences, index, index - 1),
                        }))
                      }
                    >
                      <ArrowUp aria-hidden className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={saving || index === draft.experiences.length - 1}
                      aria-label={`Descer ${experience.company}`}
                      onClick={() =>
                        setDraft((current) => ({
                          ...current,
                          experiences: move(current.experiences, index, index + 1),
                        }))
                      }
                    >
                      <ArrowDown aria-hidden className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <div className="mt-2.5">
                  <label htmlFor={`summary-${experience.key}`} className="label">
                    Descrição nesta candidatura
                  </label>
                  <Textarea
                    id={`summary-${experience.key}`}
                    rows={2}
                    value={experience.summary ?? ''}
                    disabled={saving}
                    onChange={(event) =>
                      patchExperience(experience.key, { summary: event.target.value })
                    }
                  />
                  {source?.summary && source.summary !== experience.summary ? (
                    <p className="hint">
                      No principal: <span className="italic">{source.summary}</span>
                    </p>
                  ) : null}
                </div>

                <div className="mt-3">
                  <p className="label">Realizações — marque as que entram nesta versão</p>
                  <ul className="space-y-1.5">
                    {available.map((highlight) => {
                      const isIncluded = included.has(highlight.text);
                      const position = experience.highlights.findIndex(
                        (item) => item.text === highlight.text,
                      );
                      const current = position >= 0 ? experience.highlights[position] : highlight;

                      return (
                        <li key={highlight.text} className="flex items-start gap-2">
                          <input
                            type="checkbox"
                            checked={isIncluded}
                            disabled={saving}
                            aria-label={`Incluir: ${highlight.text}`}
                            onChange={(event) =>
                              toggleHighlight(experience, highlight, event.target.checked)
                            }
                            className="mt-2 h-4 w-4 shrink-0 cursor-pointer rounded border-line-strong bg-surface-raised accent-accent-500"
                          />
                          <div className="min-w-0 flex-1">
                            <Textarea
                              rows={2}
                              aria-label={`Texto da realização: ${highlight.text}`}
                              value={current.text}
                              disabled={saving || !isIncluded}
                              className={cn('text-xs', !isIncluded && 'opacity-60')}
                              onChange={(event) =>
                                patchExperience(experience.key, {
                                  highlights: experience.highlights.map((item) =>
                                    item.text === current.text
                                      ? { ...item, text: event.target.value }
                                      : item,
                                  ),
                                })
                              }
                            />
                            {highlight.impact ? (
                              <p className="hint">Resultado: {highlight.impact}</p>
                            ) : null}
                          </div>
                          {isIncluded && position > 0 ? (
                            <Button
                              variant="ghost"
                              size="icon"
                              disabled={saving}
                              aria-label={`Subir realização: ${current.text}`}
                              onClick={() =>
                                patchExperience(experience.key, {
                                  highlights: move(experience.highlights, position, position - 1),
                                })
                              }
                            >
                              <ArrowUp aria-hidden className="h-4 w-4" />
                            </Button>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                </div>

                <div className="mt-3">
                  <label htmlFor={`tech-${experience.key}`} className="label">
                    Tecnologias desta experiência
                  </label>
                  <TagEditor
                    id={`tech-${experience.key}`}
                    tags={experience.technologies}
                    disabled={saving}
                    highlight={focus}
                    placeholder="Adicionar tecnologia…"
                    onChange={(technologies) =>
                      patchExperience(experience.key, { technologies })
                    }
                  />
                  <p className="hint">
                    Tecnologia que não está no seu currículo principal é sinalizada ao salvar.
                  </p>
                </div>
              </section>
            );
          })}
        </div>

        <Button
          disabled={saving}
          onClick={() => setDraft(document)}
          icon={<RotateCcw aria-hidden className="h-4 w-4" />}
        >
          Desfazer as minhas alterações
        </Button>
      </div>
    </Drawer>
  );
}
