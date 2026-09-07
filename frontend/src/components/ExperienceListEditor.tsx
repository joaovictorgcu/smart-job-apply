import { Briefcase, Pencil, Plus, Save, Trash2, X } from 'lucide-react';
import { useState } from 'react';

import { EmptyState } from '@/components/EmptyState';
import {
  Button,
  Card,
  CardHeader,
  Checkbox,
  Field,
  Input,
  Note,
  SectionLabel,
  Skeleton,
  Textarea,
} from '@/components/primitives';
import { useToast } from '@/components/ToastProvider';
import {
  useCreateExperience,
  useDeleteExperience,
  useExperiences,
  useUpdateExperience,
} from '@/hooks/useApi';
import { badgeClass, experiencePeriod } from '@/lib/format';
import { errorMessage } from '@/services/client';
import type { Experience, ExperienceCreate, ResumeProject } from '@/types/api';

interface FormState {
  company: string;
  role: string;
  employmentType: string;
  location: string;
  startedOn: string;
  endedOn: string;
  isCurrent: boolean;
  summary: string;
  responsibilities: string;
  technologies: string;
  results: string;
  projects: ResumeProject[];
}

const EMPTY: FormState = {
  company: '',
  role: '',
  employmentType: '',
  location: '',
  startedOn: '',
  endedOn: '',
  isCurrent: false,
  summary: '',
  responsibilities: '',
  technologies: '',
  results: '',
  projects: [],
};

const lines = (value: string): string[] =>
  value
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

const commas = (value: string): string[] =>
  value
    .split(',')
    .map((part) => part.trim())
    .filter((part) => part.length > 0);

function formFrom(experience: Experience): FormState {
  return {
    company: experience.company,
    role: experience.role,
    employmentType: experience.employment_type ?? '',
    location: experience.location ?? '',
    startedOn: experience.started_on ?? '',
    endedOn: experience.ended_on ?? '',
    isCurrent: experience.is_current,
    summary: experience.summary ?? '',
    responsibilities: experience.responsibilities.join('\n'),
    technologies: experience.technologies.join(', '),
    results: experience.results.join('\n'),
    projects: experience.projects,
  };
}

function toPayload(form: FormState): ExperienceCreate {
  return {
    company: form.company.trim(),
    role: form.role.trim(),
    employment_type: form.employmentType.trim() || null,
    location: form.location.trim() || null,
    started_on: form.startedOn || null,
    // A current position may not carry an end date — the API rejects the pair,
    // so the form clears it rather than sending something it knows is invalid.
    ended_on: form.isCurrent ? null : form.endedOn || null,
    is_current: form.isCurrent,
    summary: form.summary.trim() || null,
    responsibilities: lines(form.responsibilities),
    technologies: commas(form.technologies),
    results: lines(form.results),
    projects: form.projects
      .filter((project) => project.name.trim().length > 0)
      .map((project) => ({
        name: project.name.trim(),
        description: project.description.trim(),
        technologies: project.technologies,
      })),
  };
}

function ExperienceForm({
  initial,
  idPrefix,
  saving,
  onCancel,
  onSubmit,
}: {
  initial: FormState;
  idPrefix: string;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (payload: ExperienceCreate) => void;
}) {
  const [form, setForm] = useState<FormState>(initial);
  const patch = (partial: Partial<FormState>) => setForm((current) => ({ ...current, ...partial }));
  const valid = form.company.trim().length > 0 && form.role.trim().length > 0;

  return (
    <div className="space-y-3 rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Empresa" htmlFor={`${idPrefix}-company`} required>
          <Input
            id={`${idPrefix}-company`}
            value={form.company}
            disabled={saving}
            onChange={(event) => patch({ company: event.target.value })}
            placeholder="Globalthings"
          />
        </Field>
        <Field label="Cargo" htmlFor={`${idPrefix}-role`} required>
          <Input
            id={`${idPrefix}-role`}
            value={form.role}
            disabled={saving}
            onChange={(event) => patch({ role: event.target.value })}
            placeholder="Engenheiro de Software Sênior"
          />
        </Field>
        <Field label="Localização" htmlFor={`${idPrefix}-location`}>
          <Input
            id={`${idPrefix}-location`}
            value={form.location}
            disabled={saving}
            onChange={(event) => patch({ location: event.target.value })}
            placeholder="Recife, PE"
          />
        </Field>
        <Field label="Vínculo" htmlFor={`${idPrefix}-employment`} hint="CLT, PJ, estágio…">
          <Input
            id={`${idPrefix}-employment`}
            value={form.employmentType}
            disabled={saving}
            onChange={(event) => patch({ employmentType: event.target.value })}
          />
        </Field>
        <Field label="Início" htmlFor={`${idPrefix}-start`}>
          <Input
            id={`${idPrefix}-start`}
            type="date"
            value={form.startedOn}
            disabled={saving}
            onChange={(event) => patch({ startedOn: event.target.value })}
          />
        </Field>
        <Field label="Fim" htmlFor={`${idPrefix}-end`}>
          <Input
            id={`${idPrefix}-end`}
            type="date"
            value={form.isCurrent ? '' : form.endedOn}
            disabled={saving || form.isCurrent}
            onChange={(event) => patch({ endedOn: event.target.value })}
          />
        </Field>
      </div>

      <Checkbox
        label="Ainda estou nesta posição"
        checked={form.isCurrent}
        disabled={saving}
        onChange={(event) => patch({ isCurrent: event.target.checked })}
      />

      <Field label="Resumo" htmlFor={`${idPrefix}-summary`} hint="Uma ou duas linhas sobre o papel.">
        <Textarea
          id={`${idPrefix}-summary`}
          rows={2}
          value={form.summary}
          disabled={saving}
          onChange={(event) => patch({ summary: event.target.value })}
        />
      </Field>

      <Field
        label="Responsabilidades"
        htmlFor={`${idPrefix}-responsibilities`}
        hint="Uma por linha. A adaptação por vaga reordena estas linhas — ela nunca escreve novas."
      >
        <Textarea
          id={`${idPrefix}-responsibilities`}
          rows={4}
          value={form.responsibilities}
          disabled={saving}
          onChange={(event) => patch({ responsibilities: event.target.value })}
          placeholder={'Projetei APIs REST em C# e ASP.NET Core.\nModelei o banco em PostgreSQL.'}
        />
      </Field>

      <Field
        label="Tecnologias"
        htmlFor={`${idPrefix}-technologies`}
        hint="Separadas por vírgula. É por aqui que a vaga encontra o que você já fez."
      >
        <Input
          id={`${idPrefix}-technologies`}
          value={form.technologies}
          disabled={saving}
          onChange={(event) => patch({ technologies: event.target.value })}
          placeholder="C#, .NET, PostgreSQL, React"
        />
      </Field>

      <Field
        label="Resultados"
        htmlFor={`${idPrefix}-results`}
        hint="Um por linha, com número quando houver."
      >
        <Textarea
          id={`${idPrefix}-results`}
          rows={2}
          value={form.results}
          disabled={saving}
          onChange={(event) => patch({ results: event.target.value })}
          placeholder="Reduzi o tempo de resposta das APIs de 800 ms para 210 ms."
        />
      </Field>

      <div>
        <div className="flex items-center justify-between">
          <SectionLabel>Projetos</SectionLabel>
          <Button
            size="sm"
            disabled={saving}
            onClick={() =>
              patch({ projects: [...form.projects, { name: '', description: '', technologies: [] }] })
            }
            icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
          >
            Adicionar projeto
          </Button>
        </div>
        {form.projects.length === 0 ? (
          <p className="mt-1.5 text-2xs text-content-subtle">
            Opcional. Só os projetos ligados à vaga aparecem no currículo daquela candidatura.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {form.projects.map((project, index) => (
              <li key={index} className="flex flex-col gap-2 sm:flex-row sm:items-start">
                <div className="sm:w-52">
                  <label htmlFor={`${idPrefix}-project-${index}-name`} className="sr-only">
                    Nome do projeto {index + 1}
                  </label>
                  <Input
                    id={`${idPrefix}-project-${index}-name`}
                    value={project.name}
                    placeholder="nome"
                    disabled={saving}
                    onChange={(event) =>
                      patch({
                        projects: form.projects.map((entry, position) =>
                          position === index ? { ...entry, name: event.target.value } : entry,
                        ),
                      })
                    }
                  />
                </div>
                <div className="flex-1">
                  <label htmlFor={`${idPrefix}-project-${index}-description`} className="sr-only">
                    Descrição do projeto {index + 1}
                  </label>
                  <Input
                    id={`${idPrefix}-project-${index}-description`}
                    value={project.description}
                    placeholder="descrição"
                    disabled={saving}
                    onChange={(event) =>
                      patch({
                        projects: form.projects.map((entry, position) =>
                          position === index ? { ...entry, description: event.target.value } : entry,
                        ),
                      })
                    }
                  />
                </div>
                <div className="sm:w-52">
                  <label htmlFor={`${idPrefix}-project-${index}-technologies`} className="sr-only">
                    Tecnologias do projeto {index + 1}
                  </label>
                  <Input
                    id={`${idPrefix}-project-${index}-technologies`}
                    value={project.technologies.join(', ')}
                    placeholder="tecnologias"
                    disabled={saving}
                    onChange={(event) =>
                      patch({
                        projects: form.projects.map((entry, position) =>
                          position === index
                            ? { ...entry, technologies: commas(event.target.value) }
                            : entry,
                        ),
                      })
                    }
                  />
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={saving}
                  aria-label={`Remover projeto ${project.name || index + 1}`}
                  className="text-danger hover:bg-danger/10 hover:text-danger"
                  onClick={() =>
                    patch({ projects: form.projects.filter((_, position) => position !== index) })
                  }
                >
                  <X aria-hidden className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
        <Button
          variant="primary"
          loading={saving}
          disabled={!valid}
          onClick={() => onSubmit(toPayload(form))}
          icon={<Save aria-hidden className="h-4 w-4" />}
        >
          Salvar experiência
        </Button>
        <Button disabled={saving} onClick={onCancel}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}

/**
 * The structured half of the master resume.
 *
 * Editing here changes the master and nothing else: candidaturas that already
 * hold a derived copy keep theirs and simply report themselves as outdated, so a
 * document a human already reviewed is never rewritten behind their back.
 */
export function ExperienceListEditor() {
  const toast = useToast();
  const { data, isLoading, isError } = useExperiences();
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);

  const create = useCreateExperience({
    onSuccess: () => {
      setAdding(false);
      toast.success('Experiência adicionada', 'As candidaturas existentes não foram alteradas.');
    },
    onError: (error) => toast.error('Não foi possível adicionar', errorMessage(error)),
  });
  const update = useUpdateExperience({
    onSuccess: () => {
      setEditingId(null);
      toast.toast({ title: 'Experiência salva', variant: 'success' });
    },
    onError: (error) => toast.error('Não foi possível salvar', errorMessage(error)),
  });
  const remove = useDeleteExperience({
    onSuccess: () => {
      setConfirmingId(null);
      toast.toast({ title: 'Experiência removida', variant: 'info' });
    },
    onError: (error) => toast.error('Não foi possível remover', errorMessage(error)),
  });

  const experiences = data ?? [];

  return (
    <Card>
      <CardHeader
        title="Experiências"
        description="A base do currículo de cada candidatura. Cada vaga recebe estas mesmas experiências reordenadas e reenfatizadas — nunca reescritas."
        actions={
          <Button
            size="sm"
            disabled={adding}
            onClick={() => {
              setAdding(true);
              setEditingId(null);
            }}
            icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
          >
            Adicionar experiência
          </Button>
        }
      />
      <div className="card-body space-y-3">
        {isError ? (
          <Note tone="danger">Não foi possível carregar as suas experiências.</Note>
        ) : null}

        {adding ? (
          <ExperienceForm
            initial={EMPTY}
            idPrefix="new-experience"
            saving={create.isPending}
            onCancel={() => setAdding(false)}
            onSubmit={(payload) => create.mutate(payload)}
          />
        ) : null}

        {isLoading ? (
          <Skeleton className="h-24 w-full rounded-lg" />
        ) : experiences.length === 0 && !adding ? (
          <EmptyState
            icon={Briefcase}
            compact
            title="Nenhuma experiência cadastrada"
            description="Sem experiências estruturadas, a adaptação por vaga só pode reordenar competências. Adicione as suas posições para que ela também priorize experiências e projetos."
          />
        ) : (
          <ul className="space-y-2">
            {experiences.map((experience) => (
              <li key={experience.id}>
                {editingId === experience.id ? (
                  <ExperienceForm
                    initial={formFrom(experience)}
                    idPrefix={`experience-${experience.id}`}
                    saving={update.isPending}
                    onCancel={() => setEditingId(null)}
                    onSubmit={(payload) =>
                      update.mutate({ id: experience.id, payload })
                    }
                  />
                ) : (
                  <div className="rounded-lg border border-line px-3.5 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-content">
                          {experience.role}{' '}
                          <span className="font-normal text-content-muted">
                            · {experience.company}
                          </span>
                        </p>
                        <p className="mt-0.5 text-2xs text-content-subtle">
                          {experiencePeriod(
                            experience.started_on,
                            experience.ended_on,
                            experience.is_current,
                          )}
                          {experience.location ? ` · ${experience.location}` : ''}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <Button
                          size="sm"
                          onClick={() => {
                            setEditingId(experience.id);
                            setAdding(false);
                          }}
                          icon={<Pencil aria-hidden className="h-3.5 w-3.5" />}
                        >
                          Editar
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Remover ${experience.role} em ${experience.company}`}
                          className="text-danger hover:bg-danger/10 hover:text-danger"
                          onClick={() => setConfirmingId(experience.id)}
                        >
                          <Trash2 aria-hidden className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>

                    {experience.technologies.length > 0 ? (
                      <p className="mt-2 flex flex-wrap gap-1">
                        {experience.technologies.map((term) => (
                          <span key={term} className={badgeClass('neutral')}>
                            {term}
                          </span>
                        ))}
                      </p>
                    ) : null}

                    <p className="mt-2 text-2xs text-content-subtle">
                      {experience.responsibilities.length}{' '}
                      {experience.responsibilities.length === 1
                        ? 'responsabilidade'
                        : 'responsabilidades'}
                      {' · '}
                      {experience.results.length}{' '}
                      {experience.results.length === 1 ? 'resultado' : 'resultados'}
                      {experience.projects.length > 0
                        ? ` · ${experience.projects.length} ${
                            experience.projects.length === 1 ? 'projeto' : 'projetos'
                          }`
                        : ''}
                    </p>

                    {confirmingId === experience.id ? (
                      <Note tone="danger" className="mt-3">
                        <span className="block">
                          Remover esta experiência do currículo principal? As candidaturas que já a
                          citam continuam com o texto delas.
                        </span>
                        <span className="mt-2 flex gap-2">
                          <Button
                            variant="danger"
                            size="sm"
                            loading={remove.isPending}
                            onClick={() => remove.mutate(experience.id)}
                          >
                            Remover
                          </Button>
                          <Button size="sm" onClick={() => setConfirmingId(null)}>
                            Manter
                          </Button>
                        </span>
                      </Note>
                    ) : null}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
