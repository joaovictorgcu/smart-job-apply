import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';

import { useCreateSearch, useUpdateSearch } from '@/hooks/useApi';
import { errorMessage } from '@/services/client';
import type { Search } from '@/types/api';

import { Modal } from './Modal';
import { Button, Checkbox, Field, Input, Note, Select } from './primitives';
import { useToast } from './ToastProvider';

const REMOTE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'Qualquer local' },
  { value: 'remote', label: 'Remoto' },
  { value: 'hybrid', label: 'Híbrido' },
  { value: 'on-site', label: 'Presencial' },
];

const DATE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'Qualquer data' },
  { value: 'past-24h', label: 'Últimas 24 horas' },
  { value: 'past-week', label: 'Última semana' },
  { value: 'past-month', label: 'Último mês' },
];

const EXPERIENCE_LEVELS: Array<{ value: string; label: string }> = [
  { value: 'internship', label: 'Estágio' },
  { value: 'entry', label: 'Júnior' },
  { value: 'associate', label: 'Pleno' },
  { value: 'mid-senior', label: 'Sênior' },
  { value: 'director', label: 'Diretor' },
  { value: 'executive', label: 'Executivo' },
];

interface FormState {
  name: string;
  keywords: string;
  location: string;
  remoteFilter: string;
  datePosted: string;
  experienceLevels: string[];
  easyApplyOnly: boolean;
  maxResults: number;
}

const BLANK: FormState = {
  name: '',
  keywords: '',
  location: '',
  remoteFilter: '',
  datePosted: '',
  experienceLevels: [],
  easyApplyOnly: true,
  maxResults: 25,
};

function stateFrom(search: Search | null | undefined): FormState {
  if (!search) return BLANK;
  return {
    name: search.name,
    keywords: search.keywords,
    location: search.location ?? '',
    remoteFilter: search.remote_filter ?? '',
    datePosted: search.date_posted ?? '',
    experienceLevels: search.experience_levels,
    easyApplyOnly: search.easy_apply_only,
    maxResults: search.max_results,
  };
}

export interface SearchFormDialogProps {
  open: boolean;
  onClose: () => void;
  /** Present for edit mode; omitted to create. */
  search?: Search | null;
}

export function SearchFormDialog({ open, onClose, search }: SearchFormDialogProps) {
  const toast = useToast();
  const [form, setForm] = useState<FormState>(() => stateFrom(search));
  const [errors, setErrors] = useState<{ name?: string; keywords?: string }>({});

  useEffect(() => {
    if (open) {
      setForm(stateFrom(search));
      setErrors({});
    }
  }, [open, search]);

  const create = useCreateSearch({
    onSuccess: () => {
      toast.success('Busca salva');
      onClose();
    },
    onError: (error) => toast.error('Não foi possível salvar a busca', errorMessage(error)),
  });

  const update = useUpdateSearch({
    onSuccess: () => {
      toast.success('Busca atualizada');
      onClose();
    },
    onError: (error) => toast.error('Não foi possível atualizar a busca', errorMessage(error)),
  });

  const isPending = create.isPending || update.isPending;

  const patch = (partial: Partial<FormState>) => setForm((current) => ({ ...current, ...partial }));

  const toggleLevel = (value: string) => {
    setForm((current) => ({
      ...current,
      experienceLevels: current.experienceLevels.includes(value)
        ? current.experienceLevels.filter((level) => level !== value)
        : [...current.experienceLevels, value],
    }));
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const nextErrors: { name?: string; keywords?: string } = {};
    if (!form.name.trim()) nextErrors.name = 'Dê à busca um nome que você reconheça.';
    if (!form.keywords.trim()) nextErrors.keywords = 'As palavras-chave são obrigatórias.';
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    const payload = {
      name: form.name.trim(),
      keywords: form.keywords.trim(),
      location: form.location.trim() || null,
      remote_filter: form.remoteFilter || null,
      date_posted: form.datePosted || null,
      experience_levels: form.experienceLevels,
      easy_apply_only: form.easyApplyOnly,
      max_results: form.maxResults,
    };

    if (search) {
      update.mutate({ id: search.id, payload });
    } else {
      create.mutate(payload);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={search ? 'Editar busca' : 'Nova busca'}
      description="Buscas salvas apenas encontram e pontuam vagas. Elas nunca iniciam uma candidatura."
      footer={
        <>
          <Button onClick={onClose} disabled={isPending}>
            Cancelar
          </Button>
          <Button type="submit" form="search-form" variant="primary" loading={isPending}>
            {search ? 'Salvar alterações' : 'Criar busca'}
          </Button>
        </>
      }
    >
      <form id="search-form" onSubmit={onSubmit} noValidate className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nome" htmlFor="search-name" error={errors.name} required>
            <Input
              id="search-name"
              data-autofocus
              value={form.name}
              aria-invalid={Boolean(errors.name)}
              onChange={(event) => patch({ name: event.target.value })}
              placeholder="Backend sênior — remoto"
            />
          </Field>

          <Field label="Localização" htmlFor="search-location" hint="Deixe vazio para buscar em qualquer lugar.">
            <Input
              id="search-location"
              value={form.location}
              onChange={(event) => patch({ location: event.target.value })}
              placeholder="Berlim, Alemanha"
            />
          </Field>
        </div>

        <Field
          label="Palavras-chave"
          htmlFor="search-keywords"
          error={errors.keywords}
          hint="Exatamente o que você digitaria na caixa de busca do LinkedIn."
          required
        >
          <Input
            id="search-keywords"
            value={form.keywords}
            aria-invalid={Boolean(errors.keywords)}
            onChange={(event) => patch({ keywords: event.target.value })}
            placeholder="python backend engineer"
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Local de trabalho" htmlFor="search-remote">
            <Select
              id="search-remote"
              value={form.remoteFilter}
              onChange={(event) => patch({ remoteFilter: event.target.value })}
            >
              {REMOTE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Publicada" htmlFor="search-date">
            <Select
              id="search-date"
              value={form.datePosted}
              onChange={(event) => patch({ datePosted: event.target.value })}
            >
              {DATE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Máx. de resultados"
            htmlFor="search-max"
            hint="1–100 por execução."
          >
            <Input
              id="search-max"
              type="number"
              min={1}
              max={100}
              value={form.maxResults}
              onChange={(event) =>
                patch({ maxResults: Math.max(1, Math.min(100, Number(event.target.value) || 1)) })
              }
            />
          </Field>
        </div>

        <fieldset>
          <legend className="label">Níveis de experiência</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {EXPERIENCE_LEVELS.map((level) => (
              <Checkbox
                key={level.value}
                label={level.label}
                checked={form.experienceLevels.includes(level.value)}
                onChange={() => toggleLevel(level.value)}
              />
            ))}
          </div>
        </fieldset>

        <Checkbox
          label="Apenas Candidatura Simplificada"
          description="A ferramenta só consegue preencher o próprio formulário de Candidatura Simplificada do LinkedIn. Desligar isto mostra vagas às quais você teria que se candidatar por conta própria."
          checked={form.easyApplyOnly}
          onChange={(event) => patch({ easyApplyOnly: event.target.checked })}
        />

        <Note tone="neutral">
          Mantenha o máximo de resultados modesto. Execuções longas de coleta são o padrão que o
          LinkedIn percebe primeiro, e uma execução curta que você realmente revisa vale mais do que
          cem rascunhos que você nunca abre.
        </Note>
      </form>
    </Modal>
  );
}
