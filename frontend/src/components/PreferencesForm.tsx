import { Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { ChipGroup } from '@/components/ChipGroup';
import { Button, Card, CardHeader, Field, Input, Note, Select } from '@/components/primitives';
import { TagEditor } from '@/components/TagEditor';
import { useToast } from '@/components/ToastProvider';
import { usePreferences, useUpdatePreferences } from '@/hooks/useApi';
import { errorMessage } from '@/services/client';
import type { JobPreferences } from '@/types/api';

/**
 * The labels for the portal's own vocabulary.
 *
 * The values are the portal's and must not be translated on the wire; only
 * what the user reads is in Portuguese.
 */
const SENIORITY_OPTIONS = [
  { value: 'internship', label: 'Estágio' },
  { value: 'entry', label: 'Júnior' },
  { value: 'associate', label: 'Pleno' },
  { value: 'mid-senior', label: 'Sênior' },
  { value: 'director', label: 'Diretor' },
  { value: 'executive', label: 'Executivo' },
];

const WORK_MODEL_OPTIONS = [
  { value: 'remote', label: 'Remoto' },
  { value: 'hybrid', label: 'Híbrido' },
  { value: 'on-site', label: 'Presencial' },
];

const CURRENCIES = ['BRL', 'USD', 'EUR'];

interface Draft {
  targetRole: string;
  alternativeRoles: string[];
  seniority: string[];
  workModels: string[];
  locations: string[];
  salaryMin: string;
  salaryCurrency: string;
  priorityTechnologies: string[];
  excludedTerms: string[];
}

function draftFrom(preferences: JobPreferences): Draft {
  return {
    targetRole: preferences.target_role ?? '',
    alternativeRoles: preferences.alternative_roles,
    seniority: preferences.seniority,
    workModels: preferences.work_models,
    locations: preferences.locations,
    salaryMin: preferences.salary_min === null ? '' : String(preferences.salary_min),
    salaryCurrency: preferences.salary_currency || 'BRL',
    priorityTechnologies: preferences.priority_technologies,
    excludedTerms: preferences.excluded_terms,
  };
}

export interface PreferencesFormProps {
  /** Label for the save button; the wizard and the profile page word it differently. */
  submitLabel?: string;
  /** Rendered beside the save button — the wizard puts "skip for now" there. */
  secondaryAction?: ReactNode;
  onSaved?: (preferences: JobPreferences) => void;
  className?: string;
}

/**
 * What kind of vacancy this account is looking for.
 *
 * Shared by the onboarding wizard and the profile page rather than written
 * twice: the same answers drive the search, the triage and which of the
 * candidate's own technologies get emphasised, so two forms would be two
 * chances to disagree about what a preference means.
 */
export function PreferencesForm({
  submitLabel = 'Salvar preferências',
  secondaryAction,
  onSaved,
  className,
}: PreferencesFormProps) {
  const toast = useToast();
  const { data: preferences, isLoading } = usePreferences();
  const [draft, setDraft] = useState<Draft | null>(null);

  useEffect(() => {
    if (preferences) setDraft(draftFrom(preferences));
  }, [preferences]);

  const save = useUpdatePreferences({
    onSuccess: (saved) => {
      toast.success('Preferências salvas');
      onSaved?.(saved);
    },
    onError: (error) => toast.error('Não foi possível salvar', errorMessage(error)),
  });

  const hasRole = useMemo(() => Boolean(draft?.targetRole.trim()), [draft]);

  if (isLoading || !draft) {
    return <div className="skeleton h-96 rounded-xl" aria-busy="true" />;
  }

  const patch = (partial: Partial<Draft>) =>
    setDraft((current) => (current ? { ...current, ...partial } : current));

  const submit = () => {
    const salary = draft.salaryMin.trim();
    save.mutate({
      target_role: draft.targetRole.trim() || null,
      alternative_roles: draft.alternativeRoles,
      seniority: draft.seniority,
      work_models: draft.workModels,
      locations: draft.locations,
      salary_min: salary === '' ? null : Math.max(0, Number(salary) || 0),
      salary_currency: draft.salaryCurrency,
      priority_technologies: draft.priorityTechnologies,
      excluded_terms: draft.excludedTerms,
    });
  };

  return (
    <div className={className}>
      <div className="space-y-4">
        <Card>
          <CardHeader
            title="Que vaga você procura?"
            description="É isto que decide quais vagas buscamos e quais recomendamos."
          />
          <div className="card-body space-y-4">
            <Field
              label="Cargo principal"
              htmlFor="pref-role"
              hint="Um só. É ele que puxa a busca."
            >
              <Input
                id="pref-role"
                value={draft.targetRole}
                placeholder="Desenvolvedor Full Stack"
                onChange={(event) => patch({ targetRole: event.target.value })}
              />
            </Field>

            <div>
              <p className="label">Também aceito</p>
              <TagEditor
                id="pref-alternative-roles"
                tags={draft.alternativeRoles}
                onChange={(alternativeRoles) => patch({ alternativeRoles })}
                placeholder="Backend Developer, Software Developer…"
              />
            </div>

            <ChipGroup
              legend="Nível"
              options={SENIORITY_OPTIONS}
              selected={draft.seniority}
              onChange={(seniority) => patch({ seniority })}
              hint="Não escolher nenhum significa qualquer nível."
            />

            <ChipGroup
              legend="Como você quer trabalhar"
              options={WORK_MODEL_OPTIONS}
              selected={draft.workModels}
              onChange={(workModels) => patch({ workModels })}
              hint="Vagas em um modelo que você não marcou são descartadas antes de serem analisadas."
            />

            <div>
              <p className="label">Onde</p>
              <TagEditor
                id="pref-locations"
                tags={draft.locations}
                onChange={(locations) => patch({ locations })}
                placeholder="Recife, PE…"
              />
            </div>

            <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
              <Field
                label="Salário mínimo"
                htmlFor="pref-salary"
                hint="Opcional. Abaixo disso você não tem interesse."
              >
                <Input
                  id="pref-salary"
                  type="number"
                  min={0}
                  inputMode="numeric"
                  value={draft.salaryMin}
                  placeholder="5000"
                  onChange={(event) => patch({ salaryMin: event.target.value })}
                />
              </Field>
              <Field label="Moeda" htmlFor="pref-currency">
                <Select
                  id="pref-currency"
                  value={draft.salaryCurrency}
                  onChange={(event) => patch({ salaryCurrency: event.target.value })}
                >
                  {CURRENCIES.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Destaques e filtros"
            description="O que colocar na frente, e o que você não quer nem ver."
          />
          <div className="card-body space-y-4">
            <div>
              <p className="label">Priorizar estas tecnologias</p>
              <TagEditor
                id="pref-priority"
                tags={draft.priorityTechnologies}
                onChange={(priorityTechnologies) => patch({ priorityTechnologies })}
                placeholder=".NET, React, PostgreSQL…"
              />
              <p className="hint">
                Só reordena o que já está no seu currículo. Uma tecnologia aqui que você não tem não
                aparece em lugar nenhum.
              </p>
            </div>

            <div>
              <p className="label">Não me mostre vagas com</p>
              <TagEditor
                id="pref-excluded"
                tags={draft.excludedTerms}
                onChange={(excludedTerms) => patch({ excludedTerms })}
                placeholder="call center, vendas, sênior…"
              />
              <p className="hint">
                Comparado com o título, o local e o modelo de trabalho da vaga — não com o texto
                inteiro do anúncio. Vagas assim são descartadas sem gastar análise.
              </p>
            </div>

            {draft.excludedTerms.length > 0 ? (
              <Note tone="neutral">
                Vamos pular qualquer vaga que mencione{' '}
                <strong>{draft.excludedTerms.join(', ')}</strong>, e dizer o motivo em cada uma.
              </Note>
            ) : null}
          </div>
        </Card>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {secondaryAction}
        <Button
          variant="primary"
          className="ml-auto"
          loading={save.isPending}
          disabled={!hasRole}
          title={hasRole ? undefined : 'Informe o cargo principal'}
          onClick={submit}
          icon={<Save aria-hidden className="h-4 w-4" />}
        >
          {submitLabel}
        </Button>
        {!hasRole ? (
          <p className="w-full text-xs text-content-subtle">
            Informe o cargo principal — é ele que define o que buscar.
          </p>
        ) : null}
      </div>
    </div>
  );
}
