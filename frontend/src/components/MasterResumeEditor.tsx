import { ChevronDown, ChevronUp, Info, Plus, X } from 'lucide-react';

import {
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  Note,
  Textarea,
} from '@/components/primitives';
import { TagEditor } from '@/components/TagEditor';
import {
  emptyEducation,
  emptyExperience,
  emptyProject,
  entryKey,
  moveEntry,
} from '@/lib/masterResume';
import type {
  ResumeEducationEntry,
  ResumeExperience,
  ResumeHighlight,
  ResumeProject,
} from '@/types/masterResume';

interface RowControlsProps {
  index: number;
  total: number;
  label: string;
  onMove: (to: number) => void;
  onRemove: () => void;
}

/**
 * Reorder and remove. Order is meaningful — it is the chronology the candidate
 * chose, and a derived version falls back to it whenever two entries are equally
 * relevant to a posting — so it is editable rather than sorted for them.
 */
function RowControls({ index, total, label, onMove, onRemove }: RowControlsProps) {
  return (
    <div className="flex shrink-0 items-center gap-1">
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Mover ${label} para cima`}
        disabled={index === 0}
        onClick={() => onMove(index - 1)}
      >
        <ChevronUp aria-hidden className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Mover ${label} para baixo`}
        disabled={index === total - 1}
        onClick={() => onMove(index + 1)}
      >
        <ChevronDown aria-hidden className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Remover ${label}`}
        className="text-danger hover:bg-danger/10 hover:text-danger"
        onClick={onRemove}
      >
        <X aria-hidden className="h-4 w-4" />
      </Button>
    </div>
  );
}

function HighlightRows({
  experienceKey,
  highlights,
  onChange,
}: {
  experienceKey: string;
  highlights: ResumeHighlight[];
  onChange: (highlights: ResumeHighlight[]) => void;
}) {
  const patch = (index: number, partial: Partial<ResumeHighlight>) =>
    onChange(highlights.map((entry, position) =>
      position === index ? { ...entry, ...partial } : entry,
    ));

  return (
    <div className="space-y-2">
      <Note tone="neutral" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
        Cada ponto é uma frase sua, com as tecnologias que ela envolveu. É isso que permite
        que <span className="font-medium">a mesma experiência</span> apareça de formas
        diferentes em candidaturas diferentes: uma vaga .NET começa pelos pontos de .NET, uma
        vaga React pelos de React. Nada é reescrito — só escolhido.
      </Note>

      {highlights.length === 0 ? (
        <p className="text-xs text-content-subtle">
          Sem pontos ainda. Sem eles, esta experiência entra em todas as candidaturas com o
          mesmo resumo.
        </p>
      ) : (
        <ul className="space-y-3">
          {highlights.map((highlight, index) => (
            <li key={`${experienceKey}-highlight-${index}`} className="flex items-start gap-2">
              <div className="min-w-0 flex-1 space-y-2">
                <label htmlFor={`${experienceKey}-highlight-${index}`} className="sr-only">
                  Ponto {index + 1}
                </label>
                <Textarea
                  id={`${experienceKey}-highlight-${index}`}
                  rows={2}
                  value={highlight.text}
                  placeholder="Desenvolvimento e manutenção de APIs REST em C# e .NET…"
                  onChange={(event) => patch(index, { text: event.target.value })}
                />
                <TagEditor
                  id={`${experienceKey}-highlight-${index}-tech`}
                  tags={highlight.technologies}
                  onChange={(technologies) => patch(index, { technologies })}
                  placeholder="Tecnologias deste ponto: C#, .NET, PostgreSQL…"
                />
              </div>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Remover ponto ${index + 1}`}
                className="mt-1 text-danger hover:bg-danger/10 hover:text-danger"
                onClick={() => onChange(highlights.filter((_, position) => position !== index))}
              >
                <X aria-hidden className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <Button
        size="sm"
        onClick={() => onChange([...highlights, { text: '', technologies: [] }])}
        icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
      >
        Adicionar ponto
      </Button>
    </div>
  );
}

export interface MasterResumeEditorProps {
  experiences: ResumeExperience[];
  projects: ResumeProject[];
  education: ResumeEducationEntry[];
  certifications: string[];
  onExperiencesChange: (experiences: ResumeExperience[]) => void;
  onProjectsChange: (projects: ResumeProject[]) => void;
  onEducationChange: (education: ResumeEducationEntry[]) => void;
  onCertificationsChange: (certifications: string[]) => void;
}

/**
 * The structured half of the master resume.
 *
 * Everything edited here is the *master* — the one document the user maintains.
 * Each application derives its own version from it, and a version already
 * derived is frozen against these edits, so changing a bullet here affects the
 * next application rather than the ones already reviewed.
 */
export function MasterResumeEditor({
  experiences,
  projects,
  education,
  certifications,
  onExperiencesChange,
  onProjectsChange,
  onEducationChange,
  onCertificationsChange,
}: MasterResumeEditorProps) {
  const patchExperience = (index: number, partial: Partial<ResumeExperience>) =>
    onExperiencesChange(
      experiences.map((entry, position) =>
        position === index ? { ...entry, ...partial } : entry,
      ),
    );

  const patchProject = (index: number, partial: Partial<ResumeProject>) =>
    onProjectsChange(
      projects.map((entry, position) => (position === index ? { ...entry, ...partial } : entry)),
    );

  const patchEducation = (index: number, partial: Partial<ResumeEducationEntry>) =>
    onEducationChange(
      education.map((entry, position) => (position === index ? { ...entry, ...partial } : entry)),
    );

  return (
    <>
      <Card>
        <CardHeader
          title="Experiência profissional"
          description="O histórico que cada candidatura reorganiza. A ordem aqui é a sua cronologia — ela é usada quando duas experiências são igualmente relevantes para uma vaga."
          actions={
            <Button
              size="sm"
              onClick={() => onExperiencesChange([...experiences, emptyExperience()])}
              icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
            >
              Adicionar experiência
            </Button>
          }
        />
        <div className="card-body space-y-4">
          {experiences.length === 0 ? (
            <p className="text-xs text-content-subtle">
              Nenhuma experiência cadastrada. Sem elas, cada candidatura ainda reordena as suas
              competências, mas não consegue adaptar a descrição das suas experiências.
            </p>
          ) : null}

          {experiences.map((experience, index) => {
            const key = entryKey(experience, index);
            const label = experience.role || experience.company || `experiência ${index + 1}`;
            return (
              <div key={key} className="rounded-lg border border-line p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-content-subtle">
                    {index + 1}. {label}
                  </p>
                  <RowControls
                    index={index}
                    total={experiences.length}
                    label={label}
                    onMove={(to) => onExperiencesChange(moveEntry(experiences, index, to))}
                    onRemove={() =>
                      onExperiencesChange(
                        experiences.filter((_, position) => position !== index),
                      )
                    }
                  />
                </div>

                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Field label="Cargo" htmlFor={`${key}-role`} required>
                    <Input
                      id={`${key}-role`}
                      value={experience.role}
                      placeholder="Tech Lead"
                      onChange={(event) => patchExperience(index, { role: event.target.value })}
                    />
                  </Field>
                  <Field label="Empresa" htmlFor={`${key}-company`} required>
                    <Input
                      id={`${key}-company`}
                      value={experience.company}
                      placeholder="Globalthings"
                      onChange={(event) =>
                        patchExperience(index, { company: event.target.value })
                      }
                    />
                  </Field>
                  <Field label="Início" htmlFor={`${key}-start`}>
                    <Input
                      id={`${key}-start`}
                      value={experience.start}
                      placeholder="2023"
                      onChange={(event) => patchExperience(index, { start: event.target.value })}
                    />
                  </Field>
                  <Field label="Fim" htmlFor={`${key}-end`} hint="Deixe “atual” se for o cargo de agora.">
                    <Input
                      id={`${key}-end`}
                      value={experience.end}
                      placeholder="atual"
                      onChange={(event) => patchExperience(index, { end: event.target.value })}
                    />
                  </Field>
                  <Field label="Local" htmlFor={`${key}-location`} className="sm:col-span-2">
                    <Input
                      id={`${key}-location`}
                      value={experience.location}
                      placeholder="Recife, PE"
                      onChange={(event) =>
                        patchExperience(index, { location: event.target.value })
                      }
                    />
                  </Field>
                  <Field
                    label="Resumo neutro"
                    htmlFor={`${key}-summary`}
                    hint="Usado quando a vaga não casa com nenhum ponto abaixo — a experiência nunca fica em branco."
                    className="sm:col-span-2"
                  >
                    <Textarea
                      id={`${key}-summary`}
                      rows={2}
                      value={experience.summary}
                      onChange={(event) =>
                        patchExperience(index, { summary: event.target.value })
                      }
                    />
                  </Field>
                  <Field
                    label="Tecnologias da experiência"
                    htmlFor={`${key}-tech`}
                    className="sm:col-span-2"
                  >
                    <TagEditor
                      id={`${key}-tech`}
                      tags={experience.technologies}
                      onChange={(technologies) => patchExperience(index, { technologies })}
                      placeholder="C#, .NET, PostgreSQL, React…"
                    />
                  </Field>
                </div>

                <div className="mt-4 border-t border-line pt-3">
                  <p className="mb-2 text-xs font-semibold text-content">
                    Pontos desta experiência
                  </p>
                  <HighlightRows
                    experienceKey={key}
                    highlights={experience.highlights}
                    onChange={(highlights) => patchExperience(index, { highlights })}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Projetos"
          description="Cada candidatura traz para a frente os projetos que usam a stack da vaga."
          actions={
            <Button
              size="sm"
              onClick={() => onProjectsChange([...projects, emptyProject()])}
              icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
            >
              Adicionar projeto
            </Button>
          }
        />
        <div className="card-body space-y-3">
          {projects.length === 0 ? (
            <p className="text-xs text-content-subtle">Nenhum projeto cadastrado.</p>
          ) : null}

          {projects.map((project, index) => {
            const key = entryKey(project, index);
            const label = project.name || `projeto ${index + 1}`;
            return (
              <div key={key} className="rounded-lg border border-line p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-content-subtle">
                    {index + 1}. {label}
                  </p>
                  <RowControls
                    index={index}
                    total={projects.length}
                    label={label}
                    onMove={(to) => onProjectsChange(moveEntry(projects, index, to))}
                    onRemove={() =>
                      onProjectsChange(projects.filter((_, position) => position !== index))
                    }
                  />
                </div>
                <div className="mt-3 grid gap-3">
                  <Field label="Nome" htmlFor={`${key}-name`} required>
                    <Input
                      id={`${key}-name`}
                      value={project.name}
                      placeholder="Gateway de APIs de parceiros"
                      onChange={(event) => patchProject(index, { name: event.target.value })}
                    />
                  </Field>
                  <Field label="Descrição" htmlFor={`${key}-description`}>
                    <Textarea
                      id={`${key}-description`}
                      rows={2}
                      value={project.description}
                      onChange={(event) =>
                        patchProject(index, { description: event.target.value })
                      }
                    />
                  </Field>
                  <Field label="Resultado" htmlFor={`${key}-outcome`}>
                    <Input
                      id={`${key}-outcome`}
                      value={project.outcome}
                      placeholder="Integração de um novo parceiro passou de semanas para dias."
                      onChange={(event) => patchProject(index, { outcome: event.target.value })}
                    />
                  </Field>
                  <Field label="Tecnologias" htmlFor={`${key}-tech`}>
                    <TagEditor
                      id={`${key}-tech`}
                      tags={project.technologies}
                      onChange={(technologies) => patchProject(index, { technologies })}
                      placeholder="C#, ASP.NET Core, GraphQL…"
                    />
                  </Field>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Formação"
            actions={
              <Button
                size="sm"
                onClick={() => onEducationChange([...education, emptyEducation()])}
                icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
              >
                Adicionar
              </Button>
            }
          />
          <div className="card-body space-y-3">
            {education.length === 0 ? (
              <p className="text-xs text-content-subtle">Nenhuma formação cadastrada.</p>
            ) : null}

            {education.map((entry, index) => {
              const key = entryKey(entry, index);
              const label = entry.degree || entry.institution || `formação ${index + 1}`;
              return (
                <div key={key} className="rounded-lg border border-line p-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-content-subtle">
                      {index + 1}. {label}
                    </p>
                    <RowControls
                      index={index}
                      total={education.length}
                      label={label}
                      onMove={(to) => onEducationChange(moveEntry(education, index, to))}
                      onRemove={() =>
                        onEducationChange(education.filter((_, position) => position !== index))
                      }
                    />
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <Field label="Curso" htmlFor={`${key}-degree`} className="sm:col-span-2">
                      <Input
                        id={`${key}-degree`}
                        value={entry.degree}
                        placeholder="Bacharelado em Ciência da Computação"
                        onChange={(event) => patchEducation(index, { degree: event.target.value })}
                      />
                    </Field>
                    <Field label="Instituição" htmlFor={`${key}-institution`}>
                      <Input
                        id={`${key}-institution`}
                        value={entry.institution}
                        placeholder="UFPE"
                        onChange={(event) =>
                          patchEducation(index, { institution: event.target.value })
                        }
                      />
                    </Field>
                    <Field label="Conclusão" htmlFor={`${key}-end`}>
                      <Input
                        id={`${key}-end`}
                        value={entry.end}
                        placeholder="2015"
                        onChange={(event) => patchEducation(index, { end: event.target.value })}
                      />
                    </Field>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Certificações"
            description="Pressione Enter ou vírgula para adicionar."
          />
          <div className="card-body">
            <label htmlFor="profile-certifications" className="sr-only">
              Adicionar uma certificação
            </label>
            <TagEditor
              id="profile-certifications"
              tags={certifications}
              onChange={onCertificationsChange}
              placeholder="Microsoft AZ-204, Certified Scrum Foundation…"
            />
          </div>
        </Card>
      </div>
    </>
  );
}
