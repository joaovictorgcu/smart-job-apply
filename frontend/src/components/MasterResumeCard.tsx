import { Briefcase, Info, Pencil, Plus, Save, Trash2, X } from 'lucide-react';
import { useState } from 'react';

import { Drawer } from '@/components/Drawer';
import { EmptyState } from '@/components/EmptyState';
import { Modal } from '@/components/Modal';
import {
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  Note,
  SectionLabel,
  Textarea,
} from '@/components/primitives';
import { TagEditor } from '@/components/TagEditor';
import { useToast } from '@/components/ToastProvider';
import { useUpdateProfile } from '@/hooks/useApi';
import { errorMessage } from '@/services/client';
import type {
  Profile,
  ResumeExperience,
  ResumeHighlight,
  ResumeProject,
} from '@/types/api';

function emptyExperience(): ResumeExperience {
  return {
    key: '',
    company: '',
    role: '',
    start: '',
    end: null,
    location: null,
    summary: null,
    highlights: [],
    technologies: [],
    projects: [],
    focus: [],
  };
}

function emptyProject(): ResumeProject {
  return { name: '', description: '', technologies: [], outcome: null };
}

interface ExperienceDrawerProps {
  open: boolean;
  experience: ResumeExperience | null;
  saving: boolean;
  onClose: () => void;
  onSave: (experience: ResumeExperience) => void;
}

/**
 * The master resume's own editor for one position.
 *
 * Everything is editable here, unlike an application's version: this is where
 * the facts live. Each achievement is tagged with the technologies it involved,
 * and those tags are what let a later version lead with the right sentence for
 * a .NET posting and a different one for a React posting — so the field carries
 * a hint saying exactly that, rather than looking like optional metadata.
 */
function ExperienceDrawer({
  open,
  experience,
  saving,
  onClose,
  onSave,
}: ExperienceDrawerProps) {
  const [draft, setDraft] = useState<ResumeExperience>(experience ?? emptyExperience());
  const [seeded, setSeeded] = useState(experience?.key ?? '');

  const identity = experience?.key ?? '';
  if (open && identity !== seeded) {
    setSeeded(identity);
    setDraft(experience ?? emptyExperience());
  }

  const patch = (partial: Partial<ResumeExperience>) =>
    setDraft((current) => ({ ...current, ...partial }));

  const patchHighlight = (index: number, partial: Partial<ResumeHighlight>) =>
    patch({
      highlights: draft.highlights.map((item, position) =>
        position === index ? { ...item, ...partial } : item,
      ),
    });

  const valid = draft.company.trim().length > 0 && draft.role.trim().length > 0;

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="max-w-2xl"
      title={experience ? 'Editar experiência' : 'Nova experiência'}
      description="Faz parte do currículo principal. Candidaturas que já existem não mudam."
      footer={
        <>
          <Button onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button
            variant="primary"
            loading={saving}
            disabled={!valid}
            onClick={() => onSave(draft)}
            icon={<Save aria-hidden className="h-4 w-4" />}
          >
            Salvar experiência
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Empresa" htmlFor="exp-company" required>
            <Input
              id="exp-company"
              value={draft.company}
              disabled={saving}
              placeholder="Globalthings"
              onChange={(event) => patch({ company: event.target.value })}
            />
          </Field>
          <Field label="Cargo" htmlFor="exp-role" required>
            <Input
              id="exp-role"
              value={draft.role}
              disabled={saving}
              placeholder="Tech Lead"
              onChange={(event) => patch({ role: event.target.value })}
            />
          </Field>
          <Field label="Início" htmlFor="exp-start" hint="Ano-mês, como 2023-02.">
            <Input
              id="exp-start"
              value={draft.start}
              disabled={saving}
              placeholder="2023-02"
              onChange={(event) => patch({ start: event.target.value })}
            />
          </Field>
          <Field label="Fim" htmlFor="exp-end" hint="Vazio se você continua aí.">
            <Input
              id="exp-end"
              value={draft.end ?? ''}
              disabled={saving}
              placeholder="2025-01"
              onChange={(event) => patch({ end: event.target.value || null })}
            />
          </Field>
          <Field label="Local" htmlFor="exp-location" className="sm:col-span-2">
            <Input
              id="exp-location"
              value={draft.location ?? ''}
              disabled={saving}
              placeholder="Recife, PE · Remoto"
              onChange={(event) => patch({ location: event.target.value || null })}
            />
          </Field>
        </div>

        <Field
          label="Descrição"
          htmlFor="exp-summary"
          hint="Neutra: cada candidatura reescreve isto com a ênfase da vaga."
        >
          <Textarea
            id="exp-summary"
            rows={2}
            value={draft.summary ?? ''}
            disabled={saving}
            onChange={(event) => patch({ summary: event.target.value || null })}
          />
        </Field>

        <Field label="Tecnologias desta experiência" htmlFor="exp-technologies">
          <TagEditor
            id="exp-technologies"
            tags={draft.technologies}
            disabled={saving}
            placeholder=".NET 8, SQL Server…"
            onChange={(technologies) => patch({ technologies })}
          />
        </Field>

        <div>
          <div className="flex items-center justify-between">
            <SectionLabel>Realizações</SectionLabel>
            <Button
              size="sm"
              disabled={saving}
              onClick={() =>
                patch({
                  highlights: [
                    ...draft.highlights,
                    { text: '', technologies: [], impact: null },
                  ],
                })
              }
              icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
            >
              Adicionar
            </Button>
          </div>
          <Note tone="neutral" className="mt-2" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
            Marque cada realização com as tecnologias que ela envolveu de verdade. É isso que
            permite a uma candidatura de .NET abrir esta experiência com uma frase e a uma de React
            abrir com outra — sem inventar nenhuma das duas.
          </Note>

          {draft.highlights.length === 0 ? (
            <p className="mt-2 text-xs text-content-subtle">
              Nenhuma realização ainda. Sem elas, esta experiência entra igual em toda candidatura.
            </p>
          ) : (
            <ul className="mt-2 space-y-3">
              {draft.highlights.map((highlight, index) => (
                <li
                  key={index}
                  className="rounded-lg border border-line bg-surface-sunken px-3 py-2.5"
                >
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1 space-y-2">
                      <Textarea
                        rows={2}
                        aria-label={`Realização ${index + 1}`}
                        value={highlight.text}
                        disabled={saving}
                        placeholder="Reescreveu o serviço de autorização em .NET 8…"
                        onChange={(event) => patchHighlight(index, { text: event.target.value })}
                      />
                      <Input
                        aria-label={`Resultado da realização ${index + 1}`}
                        value={highlight.impact ?? ''}
                        disabled={saving}
                        placeholder="Resultado medido: p95 de 420 ms para 120 ms"
                        onChange={(event) =>
                          patchHighlight(index, { impact: event.target.value || null })
                        }
                      />
                      <TagEditor
                        id={`highlight-tech-${index}`}
                        tags={highlight.technologies}
                        disabled={saving}
                        placeholder="Tecnologias desta realização…"
                        onChange={(technologies) => patchHighlight(index, { technologies })}
                      />
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={saving}
                      aria-label={`Remover realização ${index + 1}`}
                      className="text-danger hover:bg-danger/10 hover:text-danger"
                      onClick={() =>
                        patch({
                          highlights: draft.highlights.filter(
                            (_, position) => position !== index,
                          ),
                        })
                      }
                    >
                      <X aria-hidden className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Drawer>
  );
}

interface MasterResumeCardProps {
  profile: Profile;
}

/**
 * The structured half of the master resume: experiences, projects, technologies.
 *
 * Saved on its own rather than through the page's sticky "save profile" bar:
 * each of these is a discrete act ("save this experience", "remove that one"),
 * and folding them into one big form would make a removal look undoable when it
 * is not yet saved — and make it silently lost if the user leaves.
 */
export function MasterResumeCard({ profile }: MasterResumeCardProps) {
  const toast = useToast();
  const [editing, setEditing] = useState<ResumeExperience | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [removing, setRemoving] = useState<ResumeExperience | null>(null);
  const [projectDraft, setProjectDraft] = useState<ResumeProject | null>(null);

  const update = useUpdateProfile({
    onSuccess: () => {
      setDrawerOpen(false);
      setEditing(null);
      setRemoving(null);
      setProjectDraft(null);
      toast.success(
        'Currículo principal salvo',
        'Novas candidaturas partem daqui. As que já existem não mudaram.',
      );
    },
    onError: (error) =>
      toast.error('Não foi possível salvar o currículo principal', errorMessage(error)),
  });

  const saveExperience = (experience: ResumeExperience) => {
    const exists = profile.experiences.some((item) => item.key === experience.key);
    const experiences = exists
      ? profile.experiences.map((item) => (item.key === experience.key ? experience : item))
      : [...profile.experiences, experience];
    update.mutate({ experiences });
  };

  const removeExperience = (experience: ResumeExperience) =>
    update.mutate({
      experiences: profile.experiences.filter((item) => item.key !== experience.key),
    });

  const saveProject = (project: ResumeProject) => {
    const exists = profile.projects.some((item) => item.name === project.name);
    const projects = exists
      ? profile.projects.map((item) => (item.name === project.name ? project : item))
      : [...profile.projects, project];
    update.mutate({ projects });
  };

  return (
    <>
      <Card>
        <CardHeader
          title="Experiência profissional"
          description="A base de toda candidatura: cada uma monta a própria versão a partir daqui."
          actions={
            <Button
              size="sm"
              onClick={() => {
                setEditing(null);
                setDrawerOpen(true);
              }}
              icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
            >
              Adicionar experiência
            </Button>
          }
        />
        <div className="card-body space-y-3">
          <Note tone="neutral" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
            Editar aqui muda o que as <span className="font-medium">próximas</span> candidaturas
            vão priorizar. Candidaturas que já têm currículo próprio continuam exatamente como
            estão — cada uma guarda a sua versão.
          </Note>

          {profile.experiences.length === 0 ? (
            <EmptyState
              compact
              icon={Briefcase}
              title="Nenhuma experiência cadastrada"
              description="Sem experiências estruturadas, uma candidatura não tem o que priorizar — ela fica só com o texto do currículo."
            />
          ) : (
            <ul className="space-y-2">
              {profile.experiences.map((experience) => (
                <li
                  key={experience.key}
                  className="flex flex-wrap items-start gap-3 rounded-lg border border-line bg-surface-sunken px-3.5 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-content">
                      {experience.role} — {experience.company}
                    </p>
                    <p className="tabular font-mono text-2xs text-content-subtle">
                      {experience.end
                        ? `${experience.start} — ${experience.end}`
                        : `${experience.start} — atual`}
                      {experience.location ? ` · ${experience.location}` : ''}
                    </p>
                    {experience.summary ? (
                      <p className="mt-1 text-xs leading-relaxed text-content-muted">
                        {experience.summary}
                      </p>
                    ) : null}
                    <p className="mt-1.5 text-2xs text-content-subtle">
                      {experience.highlights.length}{' '}
                      {experience.highlights.length === 1 ? 'realização' : 'realizações'} ·{' '}
                      {experience.technologies.length}{' '}
                      {experience.technologies.length === 1 ? 'tecnologia' : 'tecnologias'}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Editar ${experience.role} na ${experience.company}`}
                      onClick={() => {
                        setEditing(experience);
                        setDrawerOpen(true);
                      }}
                    >
                      <Pencil aria-hidden className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remover ${experience.role} na ${experience.company}`}
                      className="text-danger hover:bg-danger/10 hover:text-danger"
                      onClick={() => setRemoving(experience)}
                    >
                      <Trash2 aria-hidden className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Tecnologias e certificações"
          description="O vocabulário que uma vaga é comparada com. Nada fora daqui entra num currículo."
        />
        <div className="card-body grid gap-4 lg:grid-cols-2">
          <Field
            label="Tecnologias"
            htmlFor="master-technologies"
            hint="Ferramentas e linguagens. As competências ficam no campo Habilidades."
          >
            <TagEditor
              id="master-technologies"
              tags={profile.technologies}
              disabled={update.isPending}
              placeholder=".NET 8, React, Python…"
              onChange={(technologies) => update.mutate({ technologies })}
            />
          </Field>
          <Field label="Certificações" htmlFor="master-certifications">
            <TagEditor
              id="master-certifications"
              tags={profile.certifications}
              disabled={update.isPending}
              placeholder="AZ-204 — Azure Developer Associate…"
              onChange={(certifications) => update.mutate({ certifications })}
            />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Projetos"
          description="Projetos próprios ou paralelos, priorizados por vaga como as experiências."
          actions={
            <Button
              size="sm"
              onClick={() => setProjectDraft(emptyProject())}
              icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
            >
              Adicionar projeto
            </Button>
          }
        />
        <div className="card-body">
          {profile.projects.length === 0 ? (
            <p className="text-xs text-content-subtle">Nenhum projeto cadastrado.</p>
          ) : (
            <ul className="space-y-2">
              {profile.projects.map((project) => (
                <li
                  key={project.name}
                  className="flex flex-wrap items-start gap-3 rounded-lg border border-line bg-surface-sunken px-3.5 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-content">{project.name}</p>
                    {project.description ? (
                      <p className="mt-0.5 text-xs leading-relaxed text-content-muted">
                        {project.description}
                      </p>
                    ) : null}
                    {project.technologies.length > 0 ? (
                      <p className="mt-1 text-2xs text-content-subtle">
                        {project.technologies.join(' · ')}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Editar projeto ${project.name}`}
                      onClick={() => setProjectDraft(project)}
                    >
                      <Pencil aria-hidden className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remover projeto ${project.name}`}
                      className="text-danger hover:bg-danger/10 hover:text-danger"
                      onClick={() =>
                        update.mutate({
                          projects: profile.projects.filter((item) => item.name !== project.name),
                        })
                      }
                    >
                      <Trash2 aria-hidden className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      <ExperienceDrawer
        open={drawerOpen}
        experience={editing}
        saving={update.isPending}
        onClose={() => {
          setDrawerOpen(false);
          setEditing(null);
        }}
        onSave={saveExperience}
      />

      <Drawer
        open={projectDraft !== null}
        onClose={() => setProjectDraft(null)}
        title={projectDraft?.name ? 'Editar projeto' : 'Novo projeto'}
        description="Faz parte do currículo principal."
        footer={
          <>
            <Button onClick={() => setProjectDraft(null)} disabled={update.isPending}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              loading={update.isPending}
              disabled={!projectDraft?.name.trim()}
              onClick={() => projectDraft && saveProject(projectDraft)}
              icon={<Save aria-hidden className="h-4 w-4" />}
            >
              Salvar projeto
            </Button>
          </>
        }
      >
        {projectDraft ? (
          <div className="space-y-4">
            <Field label="Nome" htmlFor="project-name" required>
              <Input
                id="project-name"
                value={projectDraft.name}
                disabled={update.isPending}
                onChange={(event) =>
                  setProjectDraft({ ...projectDraft, name: event.target.value })
                }
              />
            </Field>
            <Field label="Descrição" htmlFor="project-description">
              <Textarea
                id="project-description"
                rows={3}
                value={projectDraft.description}
                disabled={update.isPending}
                onChange={(event) =>
                  setProjectDraft({ ...projectDraft, description: event.target.value })
                }
              />
            </Field>
            <Field label="Resultado" htmlFor="project-outcome">
              <Input
                id="project-outcome"
                value={projectDraft.outcome ?? ''}
                disabled={update.isPending}
                placeholder="usado em 4 repositórios internos"
                onChange={(event) =>
                  setProjectDraft({ ...projectDraft, outcome: event.target.value || null })
                }
              />
            </Field>
            <Field label="Tecnologias" htmlFor="project-technologies">
              <TagEditor
                id="project-technologies"
                tags={projectDraft.technologies}
                disabled={update.isPending}
                placeholder="Python, SQL…"
                onChange={(technologies) => setProjectDraft({ ...projectDraft, technologies })}
              />
            </Field>
          </div>
        ) : null}
      </Drawer>

      <Modal
        open={removing !== null}
        onClose={() => setRemoving(null)}
        size="sm"
        title="Remover esta experiência?"
        description="Ela sai do currículo principal e das próximas candidaturas."
        footer={
          <>
            <Button onClick={() => setRemoving(null)} disabled={update.isPending}>
              Manter
            </Button>
            <Button
              variant="danger"
              loading={update.isPending}
              onClick={() => removing && removeExperience(removing)}
            >
              Remover
            </Button>
          </>
        }
      >
        <p className="text-sm leading-relaxed text-content-muted">
          As candidaturas que já têm currículo próprio continuam com esta experiência: cada uma
          guarda a sua versão, e remover aqui não reescreve o que já foi preparado.
        </p>
      </Modal>
    </>
  );
}
