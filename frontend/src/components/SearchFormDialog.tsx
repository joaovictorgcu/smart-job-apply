import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';

import { useCreateSearch, useUpdateSearch } from '@/hooks/useApi';
import { errorMessage } from '@/services/client';
import type { Search } from '@/types/api';

import { Modal } from './Modal';
import { Button, Checkbox, Field, Input, Note, Select } from './primitives';
import { useToast } from './ToastProvider';

const REMOTE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'Any workplace' },
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'on-site', label: 'On-site' },
];

const DATE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'Any time' },
  { value: 'past-24h', label: 'Past 24 hours' },
  { value: 'past-week', label: 'Past week' },
  { value: 'past-month', label: 'Past month' },
];

const EXPERIENCE_LEVELS: Array<{ value: string; label: string }> = [
  { value: 'internship', label: 'Internship' },
  { value: 'entry', label: 'Entry level' },
  { value: 'associate', label: 'Associate' },
  { value: 'mid-senior', label: 'Mid-senior' },
  { value: 'director', label: 'Director' },
  { value: 'executive', label: 'Executive' },
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
      toast.success('Search saved');
      onClose();
    },
    onError: (error) => toast.error('Could not save the search', errorMessage(error)),
  });

  const update = useUpdateSearch({
    onSuccess: () => {
      toast.success('Search updated');
      onClose();
    },
    onError: (error) => toast.error('Could not update the search', errorMessage(error)),
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
    if (!form.name.trim()) nextErrors.name = 'Give the search a name you will recognise.';
    if (!form.keywords.trim()) nextErrors.keywords = 'Keywords are required.';
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
      title={search ? 'Edit search' : 'New search'}
      description="Saved searches only find and score jobs. They never start an application."
      footer={
        <>
          <Button onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
          <Button type="submit" form="search-form" variant="primary" loading={isPending}>
            {search ? 'Save changes' : 'Create search'}
          </Button>
        </>
      }
    >
      <form id="search-form" onSubmit={onSubmit} noValidate className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" htmlFor="search-name" error={errors.name} required>
            <Input
              id="search-name"
              data-autofocus
              value={form.name}
              aria-invalid={Boolean(errors.name)}
              onChange={(event) => patch({ name: event.target.value })}
              placeholder="Senior backend — remote"
            />
          </Field>

          <Field label="Location" htmlFor="search-location" hint="Leave empty to search everywhere.">
            <Input
              id="search-location"
              value={form.location}
              onChange={(event) => patch({ location: event.target.value })}
              placeholder="Berlin, Germany"
            />
          </Field>
        </div>

        <Field
          label="Keywords"
          htmlFor="search-keywords"
          error={errors.keywords}
          hint="Exactly what you would type into the LinkedIn search box."
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
          <Field label="Workplace" htmlFor="search-remote">
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

          <Field label="Posted" htmlFor="search-date">
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
            label="Max results"
            htmlFor="search-max"
            hint="1–100 per run."
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
          <legend className="label">Experience levels</legend>
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
          label="Easy Apply only"
          description="The tool can only fill LinkedIn's own Easy Apply form. Turning this off surfaces jobs you would have to apply to yourself."
          checked={form.easyApplyOnly}
          onChange={(event) => patch({ easyApplyOnly: event.target.checked })}
        />

        <Note tone="neutral">
          Keep max results modest. Long scraping runs are the pattern LinkedIn notices first, and a
          short run you actually review beats a hundred drafts you never open.
        </Note>
      </form>
    </Modal>
  );
}
