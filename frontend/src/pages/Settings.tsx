import { Bot, Info, Lock, Save, ShieldAlert, ShieldCheck, TriangleAlert } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { DryRunToggle } from '@/components/DryRunToggle';
import {
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  Note,
  PageHeader,
  Select,
  Skeleton,
  Toggle,
} from '@/components/primitives';
import { useToast } from '@/components/ToastProvider';
import { useSettings, useUpdateSettings } from '@/hooks/useApi';
import { errorMessage } from '@/services/client';
import type { UserSettings, UserSettingsUpdate } from '@/types/api';

const TONES = ['professional', 'friendly', 'direct', 'enthusiastic'] as const;

const LANGUAGES: Array<{ value: string; label: string }> = [
  { value: 'auto', label: 'Match the job posting' },
  { value: 'en', label: 'English' },
  { value: 'pt-BR', label: 'Portuguese (Brazil)' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'de', label: 'German' },
];

interface Errors {
  actionDelay?: string;
  applyDelay?: string;
  workingHours?: string;
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
  id,
  tone,
}: {
  label: string;
  description: ReactNode;
  checked: boolean;
  onChange: (next: boolean) => void;
  id: string;
  tone?: 'accent' | 'warning' | 'success';
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div className="min-w-0">
        <label htmlFor={id} className="text-sm font-medium text-content">
          {label}
        </label>
        <p className="mt-0.5 text-xs leading-relaxed text-content-subtle">{description}</p>
      </div>
      <Toggle id={id} label={label} checked={checked} onChange={onChange} tone={tone} />
    </div>
  );
}

export function Settings() {
  const toast = useToast();
  const { data: settings, isLoading } = useSettings();
  const [draft, setDraft] = useState<UserSettings | null>(null);
  const [errors, setErrors] = useState<Errors>({});

  useEffect(() => {
    if (settings) setDraft(settings);
  }, [settings]);

  const update = useUpdateSettings({
    onSuccess: () => toast.success('Settings saved'),
    onError: (error) => toast.error('Could not save settings', errorMessage(error)),
  });

  const isDirty = useMemo(() => {
    if (!settings || !draft) return false;
    return JSON.stringify(draft) !== JSON.stringify(settings);
  }, [settings, draft]);

  if (isLoading || !draft) {
    return (
      <div className="space-y-5" aria-busy="true">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-72 rounded-xl" />
        <Skeleton className="h-56 rounded-xl" />
      </div>
    );
  }

  const patch = (partial: Partial<UserSettings>) =>
    setDraft((current) => (current ? { ...current, ...partial } : current));

  const numberPatch = (key: keyof UserSettings, raw: string, min: number, max: number) => {
    const parsed = Number(raw);
    if (Number.isNaN(parsed)) return;
    patch({ [key]: Math.max(min, Math.min(max, parsed)) } as Partial<UserSettings>);
  };

  const save = () => {
    const nextErrors: Errors = {};
    if (draft.action_delay_min > draft.action_delay_max) {
      nextErrors.actionDelay = 'The minimum delay cannot be larger than the maximum.';
    }
    if (draft.apply_delay_min > draft.apply_delay_max) {
      nextErrors.applyDelay = 'The minimum delay cannot be larger than the maximum.';
    }
    if (draft.working_hour_start >= draft.working_hour_end) {
      nextErrors.workingHours = 'The start hour must be earlier than the end hour.';
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    // dry_run is owned by the dedicated toggle, which has its own confirmation step.
    const payload: UserSettingsUpdate = { ...draft };
    delete payload.dry_run;
    update.mutate(payload);
  };

  return (
    <div className="space-y-5 pb-24">
      <PageHeader
        title="Settings"
        description="Guard rails, safety switches and AI behaviour. Loosening a guard rail does not make the tool faster — it makes your account easier to flag."
      />

      <Card>
        <CardHeader
          title="Automation guard rails"
          description="Limits that keep the run small, slow and human-shaped."
        />
        <div className="card-body space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Daily submission cap"
              htmlFor="settings-daily-cap"
              hint="Maximum applications you can submit per day (1–50). A human applying to 40 jobs in an evening is already unusual; going higher is the fastest way to look like a bot."
            >
              <Input
                id="settings-daily-cap"
                type="number"
                min={1}
                max={50}
                value={draft.daily_cap}
                onChange={(event) => numberPatch('daily_cap', event.target.value, 1, 50)}
              />
            </Field>

            <Field
              label="Minimum match score"
              htmlFor="settings-min-score"
              hint="Jobs scoring below this are skipped instead of applied to. Lowering it burns your daily cap on roles you do not fit, which is worse for you than for LinkedIn."
            >
              <Input
                id="settings-min-score"
                type="number"
                min={0}
                max={100}
                value={draft.min_score}
                onChange={(event) => numberPatch('min_score', event.target.value, 0, 100)}
              />
            </Field>
          </div>

          <div>
            <p className="label">Delay between actions (seconds)</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Minimum" htmlFor="settings-action-min">
                <Input
                  id="settings-action-min"
                  type="number"
                  step={0.5}
                  min={0.5}
                  max={60}
                  value={draft.action_delay_min}
                  onChange={(event) => numberPatch('action_delay_min', event.target.value, 0.5, 60)}
                />
              </Field>
              <Field label="Maximum" htmlFor="settings-action-max" error={errors.actionDelay}>
                <Input
                  id="settings-action-max"
                  type="number"
                  step={0.5}
                  min={0.5}
                  max={120}
                  value={draft.action_delay_max}
                  onChange={(event) => numberPatch('action_delay_max', event.target.value, 0.5, 120)}
                />
              </Field>
            </div>
            <p className="hint">
              Each click and keystroke waits a random amount inside this range. Randomized delays
              reduce, but do not eliminate, the risk of detection — no delay setting makes automation
              safe or permitted.
            </p>
          </div>

          <div>
            <p className="label">Delay between applications (seconds)</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Minimum" htmlFor="settings-apply-min">
                <Input
                  id="settings-apply-min"
                  type="number"
                  step={1}
                  min={5}
                  max={600}
                  value={draft.apply_delay_min}
                  onChange={(event) => numberPatch('apply_delay_min', event.target.value, 5, 600)}
                />
              </Field>
              <Field label="Maximum" htmlFor="settings-apply-max" error={errors.applyDelay}>
                <Input
                  id="settings-apply-max"
                  type="number"
                  step={1}
                  min={5}
                  max={1800}
                  value={draft.apply_delay_max}
                  onChange={(event) => numberPatch('apply_delay_max', event.target.value, 5, 1800)}
                />
              </Field>
            </div>
            <p className="hint">
              The pause between two applications. Short pauses produce a burst of activity that looks
              nothing like a person reading job descriptions.
            </p>
          </div>

          <div>
            <p className="label">Working hours</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Start hour" htmlFor="settings-hour-start">
                <Input
                  id="settings-hour-start"
                  type="number"
                  min={0}
                  max={23}
                  value={draft.working_hour_start}
                  onChange={(event) => numberPatch('working_hour_start', event.target.value, 0, 23)}
                />
              </Field>
              <Field label="End hour" htmlFor="settings-hour-end" error={errors.workingHours}>
                <Input
                  id="settings-hour-end"
                  type="number"
                  min={1}
                  max={24}
                  value={draft.working_hour_end}
                  onChange={(event) => numberPatch('working_hour_end', event.target.value, 1, 24)}
                />
              </Field>
            </div>
            <p className="hint">
              Runs are confined to this window, in your local time. A window that spans the whole day
              means activity at 4am, which is one of the easiest patterns to spot.
            </p>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader title="Safety" description="The switches that decide whether anything can be sent." />
        <div className="card-body space-y-4">
          <div className="flex items-start justify-between gap-4 rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-sm font-medium text-content">
                Dry run
                <ShieldCheck aria-hidden className="h-3.5 w-3.5 text-success" />
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-content-subtle">
                While dry run is on, forms are filled and reviewed but the submit button is never
                clicked. Turn it off only when you are ready to send real applications — and expect
                to confirm that choice.
              </p>
            </div>
            <DryRunToggle />
          </div>

          {draft.require_manual_approval ? (
            <div className="flex items-start justify-between gap-4 rounded-lg border border-success/40 bg-success/[0.07] px-3.5 py-3">
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 text-sm font-medium text-content">
                  Manual approval required
                  <Lock aria-hidden className="h-3.5 w-3.5 text-success" />
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-content-subtle">
                  Every application waits for you to open it, read it and approve it. This is what
                  assisted mode means, so this dashboard will not turn it off — there is no bulk
                  submit anywhere in the app.
                </p>
              </div>
              <span className="badge badge-success shrink-0">Always on</span>
            </div>
          ) : (
            <div className="rounded-lg border border-danger/40 bg-danger/[0.07] px-3.5 py-3">
              <p className="flex items-center gap-1.5 text-sm font-medium text-danger-strong">
                <ShieldAlert aria-hidden className="h-4 w-4" />
                Manual approval is currently disabled
              </p>
              <p className="mt-1 text-xs leading-relaxed text-content-muted">
                Something set this flag off outside this dashboard. Applications could be submitted
                without you reading them first. Turn it back on.
              </p>
              <Button
                className="mt-2.5"
                size="sm"
                variant="primary"
                onClick={() => patch({ require_manual_approval: true })}
              >
                Require manual approval again
              </Button>
            </div>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="AI"
          description="How jobs are scored and what the generated text sounds like."
        />
        <div className="card-body space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Model"
              htmlFor="settings-model"
              hint="Leave empty to use the model configured on the server."
            >
              <Input
                id="settings-model"
                value={draft.ai_model ?? ''}
                placeholder="Server default"
                onChange={(event) => patch({ ai_model: event.target.value.trim() || null })}
              />
            </Field>

            <Field label="Cover letter tone" htmlFor="settings-tone">
              <Select
                id="settings-tone"
                value={draft.cover_letter_tone}
                onChange={(event) => patch({ cover_letter_tone: event.target.value })}
              >
                {TONES.map((tone) => (
                  <option key={tone} value={tone}>
                    {tone.charAt(0).toUpperCase() + tone.slice(1)}
                  </option>
                ))}
              </Select>
            </Field>

            <Field
              label="Content language"
              htmlFor="settings-language"
              hint="Applies to cover letters and screening answers."
            >
              <Select
                id="settings-language"
                value={draft.content_language}
                onChange={(event) => patch({ content_language: event.target.value })}
              >
                {LANGUAGES.map((language) => (
                  <option key={language.value} value={language.value}>
                    {language.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <div className="divide-y divide-line border-t border-line">
            <ToggleRow
              id="settings-generate-cover-letter"
              label="Generate a cover letter for each application"
              description="Costs an extra AI call per job. Turn it off if the forms you meet rarely ask for one."
              checked={draft.generate_cover_letter}
              onChange={(next) => patch({ generate_cover_letter: next })}
            />
          </div>

          <Note tone="neutral" icon={<Bot aria-hidden className="h-3.5 w-3.5" />}>
            The AI never decides to submit anything. It only scores jobs and drafts text that you
            read and approve.
          </Note>
        </div>
      </Card>

      <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
        No combination of these settings makes automating LinkedIn permitted. It violates
        LinkedIn&apos;s Terms of Service, and account restrictions are a real possible outcome.
      </Note>

      {isDirty ? (
        <div className="sticky bottom-4 z-20 mx-auto w-full max-w-2xl">
          <Card className="flex items-center gap-3 border-accent-500/40 px-4 py-3 shadow-lifted">
            <p className="flex items-center gap-1.5 text-sm text-content-muted">
              <Info aria-hidden className="h-3.5 w-3.5" />
              Unsaved changes
            </p>
            <Button
              className="ml-auto"
              disabled={update.isPending}
              onClick={() => settings && setDraft(settings)}
            >
              Reset
            </Button>
            <Button
              variant="primary"
              loading={update.isPending}
              onClick={save}
              icon={<Save aria-hidden className="h-4 w-4" />}
            >
              Save settings
            </Button>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
