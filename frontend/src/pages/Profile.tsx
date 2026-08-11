import { Info, Plus, Save, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { KeyboardEvent } from 'react';

import {
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  Note,
  PageHeader,
  Skeleton,
  Textarea,
} from '@/components/primitives';
import { ResumeUploader } from '@/components/ResumeUploader';
import { useToast } from '@/components/ToastProvider';
import { useProfile, useUpdateProfile } from '@/hooks/useApi';
import { errorMessage } from '@/services/client';
import type { Profile as ProfileType } from '@/types/api';

interface AnswerRow {
  id: number;
  key: string;
  value: string;
}

interface Draft {
  headline: string;
  location: string;
  phone: string;
  yearsOfExperience: string;
  summary: string;
  resumeText: string;
  skills: string[];
  languages: string[];
  answers: AnswerRow[];
}

let answerRowId = 0;

function draftFrom(profile: ProfileType): Draft {
  return {
    headline: profile.headline ?? '',
    location: profile.location ?? '',
    phone: profile.phone ?? '',
    yearsOfExperience:
      profile.years_of_experience === null ? '' : String(profile.years_of_experience),
    summary: profile.summary ?? '',
    resumeText: profile.resume_text ?? '',
    skills: profile.skills,
    languages: profile.preferred_languages,
    answers: Object.entries(profile.answer_bank).map(([key, value]) => {
      answerRowId += 1;
      return { id: answerRowId, key, value: value === null ? '' : String(value) };
    }),
  };
}

function TagEditor({
  id,
  tags,
  onChange,
  placeholder,
}: {
  id: string;
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder: string;
}) {
  const [value, setValue] = useState('');

  const add = () => {
    const parts = value
      .split(',')
      .map((part) => part.trim())
      .filter((part) => part.length > 0 && !tags.includes(part));
    if (parts.length > 0) onChange([...tags, ...parts]);
    setValue('');
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault();
      add();
    } else if (event.key === 'Backspace' && value === '' && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  };

  return (
    <div>
      {tags.length > 0 ? (
        <ul className="mb-2 flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <li key={tag}>
              <span className="inline-flex items-center gap-1 rounded-full border border-accent-500/35 bg-accent-500/12 py-0.5 pl-2.5 pr-1 text-xs font-medium text-accent-400">
                {tag}
                <button
                  type="button"
                  onClick={() => onChange(tags.filter((entry) => entry !== tag))}
                  aria-label={`Remove ${tag}`}
                  className="rounded-full p-0.5 hover:bg-accent-500/20"
                >
                  <X aria-hidden className="h-3 w-3" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <Input
        id={id}
        value={value}
        placeholder={placeholder}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        onBlur={add}
      />
    </div>
  );
}

export function Profile() {
  const toast = useToast();
  const { data: profile, isLoading } = useProfile();
  const [draft, setDraft] = useState<Draft | null>(null);
  // Kept separately so the dirty check never has to rebuild (and re-key) the rows.
  const [baseline, setBaseline] = useState<Draft | null>(null);

  useEffect(() => {
    if (!profile) return;
    const next = draftFrom(profile);
    setDraft(next);
    setBaseline(next);
  }, [profile]);

  const update = useUpdateProfile({
    onSuccess: () => toast.success('Profile saved'),
    onError: (error) => toast.error('Could not save your profile', errorMessage(error)),
  });

  const isDirty = useMemo(() => {
    if (!baseline || !draft) return false;
    return JSON.stringify(draft) !== JSON.stringify(baseline);
  }, [baseline, draft]);

  if (isLoading || !draft) {
    return (
      <div className="space-y-5" aria-busy="true">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
      </div>
    );
  }

  const patch = (partial: Partial<Draft>) =>
    setDraft((current) => (current ? { ...current, ...partial } : current));

  const save = () => {
    const answerBank: Record<string, string> = {};
    for (const row of draft.answers) {
      const key = row.key.trim();
      if (key) answerBank[key] = row.value;
    }

    const years = draft.yearsOfExperience.trim();
    update.mutate({
      headline: draft.headline.trim() || null,
      location: draft.location.trim() || null,
      phone: draft.phone.trim() || null,
      years_of_experience: years === '' ? null : Math.max(0, Math.min(70, Number(years) || 0)),
      summary: draft.summary.trim() || null,
      resume_text: draft.resumeText.trim() || null,
      skills: draft.skills,
      preferred_languages: draft.languages,
      answer_bank: answerBank,
    });
  };

  return (
    <div className="space-y-5 pb-24">
      <PageHeader
        title="Profile"
        description="What the AI knows about you. Everything here feeds job scoring, cover letters and screening answers."
      />

      <Card>
        <CardHeader title="Basics" />
        <div className="card-body grid gap-4 sm:grid-cols-2">
          <Field
            label="Headline"
            htmlFor="profile-headline"
            hint="One line, like your LinkedIn headline."
            className="sm:col-span-2"
          >
            <Input
              id="profile-headline"
              value={draft.headline}
              onChange={(event) => patch({ headline: event.target.value })}
              placeholder="Senior backend engineer — Python, distributed systems"
            />
          </Field>

          <Field label="Location" htmlFor="profile-location">
            <Input
              id="profile-location"
              value={draft.location}
              onChange={(event) => patch({ location: event.target.value })}
              placeholder="Lisbon, Portugal"
            />
          </Field>

          <Field label="Phone" htmlFor="profile-phone" hint="Used to fill contact fields in forms.">
            <Input
              id="profile-phone"
              type="tel"
              value={draft.phone}
              onChange={(event) => patch({ phone: event.target.value })}
              placeholder="+351 900 000 000"
            />
          </Field>

          <Field label="Years of experience" htmlFor="profile-years">
            <Input
              id="profile-years"
              type="number"
              min={0}
              max={70}
              value={draft.yearsOfExperience}
              onChange={(event) => patch({ yearsOfExperience: event.target.value })}
            />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Summary"
          description="A short professional summary. The AI leans on this for cover letters."
        />
        <div className="card-body">
          <label htmlFor="profile-summary" className="sr-only">
            Summary
          </label>
          <Textarea
            id="profile-summary"
            rows={5}
            value={draft.summary}
            onChange={(event) => patch({ summary: event.target.value })}
            placeholder="Eight years building payment systems, mostly Python and Postgres…"
          />
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Skills" description="Press Enter or comma to add. Backspace removes the last one." />
          <div className="card-body">
            <label htmlFor="profile-skills" className="sr-only">
              Add a skill
            </label>
            <TagEditor
              id="profile-skills"
              tags={draft.skills}
              onChange={(skills) => patch({ skills })}
              placeholder="Python, PostgreSQL, Kubernetes…"
            />
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Preferred languages"
            description="Which languages you are comfortable applying in."
          />
          <div className="card-body">
            <label htmlFor="profile-languages" className="sr-only">
              Add a language
            </label>
            <TagEditor
              id="profile-languages"
              tags={draft.languages}
              onChange={(languages) => patch({ languages })}
              placeholder="English, Portuguese…"
            />
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Résumé"
          description="The PDF is uploaded to LinkedIn; the text version is what the AI reads."
        />
        <div className="card-body grid gap-4 lg:grid-cols-2">
          <ResumeUploader filename={profile?.resume_filename ?? null} />

          <div>
            <label htmlFor="profile-resume-text" className="label">
              Résumé text
            </label>
            <Textarea
              id="profile-resume-text"
              rows={10}
              value={draft.resumeText}
              onChange={(event) => patch({ resumeText: event.target.value })}
              placeholder="Paste the plain text of your résumé here."
            />
            <p className="hint">
              Keep this in sync with the PDF. Mismatched claims are what screening questions catch.
            </p>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Answer bank"
          description="Fixed answers to the questions LinkedIn asks over and over."
          actions={
            <Button
              size="sm"
              onClick={() => {
                answerRowId += 1;
                patch({ answers: [...draft.answers, { id: answerRowId, key: '', value: '' }] });
              }}
              icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
            >
              Add answer
            </Button>
          }
        />
        <div className="card-body space-y-3">
          <Note tone="neutral" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
            The AI checks this bank first and only invents an answer when nothing matches — and any
            answer it invents with low confidence is flagged for your review before submission. Use
            keys like <span className="font-mono">work_authorization</span> or{' '}
            <span className="font-mono">notice_period</span>.
          </Note>

          {draft.answers.length === 0 ? (
            <p className="text-xs text-content-subtle">
              No stored answers yet. Add the ones you type most often.
            </p>
          ) : (
            <ul className="space-y-2">
              {draft.answers.map((row, index) => (
                <li key={row.id} className="flex flex-col gap-2 sm:flex-row sm:items-start">
                  <div className="sm:w-64">
                    <label htmlFor={`answer-key-${row.id}`} className="sr-only">
                      Question key {index + 1}
                    </label>
                    <Input
                      id={`answer-key-${row.id}`}
                      value={row.key}
                      placeholder="question key"
                      className="font-mono"
                      onChange={(event) =>
                        patch({
                          answers: draft.answers.map((entry) =>
                            entry.id === row.id ? { ...entry, key: event.target.value } : entry,
                          ),
                        })
                      }
                    />
                  </div>
                  <div className="flex-1">
                    <label htmlFor={`answer-value-${row.id}`} className="sr-only">
                      Answer {index + 1}
                    </label>
                    <Input
                      id={`answer-value-${row.id}`}
                      value={row.value}
                      placeholder="answer"
                      onChange={(event) =>
                        patch({
                          answers: draft.answers.map((entry) =>
                            entry.id === row.id ? { ...entry, value: event.target.value } : entry,
                          ),
                        })
                      }
                    />
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove answer ${row.key || index + 1}`}
                    className="text-danger hover:bg-danger/10 hover:text-danger"
                    onClick={() =>
                      patch({ answers: draft.answers.filter((entry) => entry.id !== row.id) })
                    }
                  >
                    <X aria-hidden className="h-4 w-4" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      {isDirty ? (
        <div className="sticky bottom-4 z-20 mx-auto w-full max-w-2xl">
          <Card className="flex items-center gap-3 border-accent-500/40 px-4 py-3 shadow-lifted">
            <p className="text-sm text-content-muted">You have unsaved changes.</p>
            <Button
              className="ml-auto"
              onClick={() => baseline && setDraft(baseline)}
              disabled={update.isPending}
            >
              Reset
            </Button>
            <Button
              variant="primary"
              loading={update.isPending}
              onClick={save}
              icon={<Save aria-hidden className="h-4 w-4" />}
            >
              Save profile
            </Button>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
