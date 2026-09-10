import {
  ArrowRight,
  CheckCircle2,
  FileText,
  Info,
  Sparkles,
  TriangleAlert,
  Upload,
} from 'lucide-react';
import { useMemo, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';

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
import { useToast } from '@/components/ToastProvider';
import { useApplyResumeIntake, useExperiences, useProfile, useReadResumeIntake } from '@/hooks/useApi';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';
import type { ExperienceCreate, ResumeIntake, ResumeIntakeExperience } from '@/types/api';

const MAX_BYTES = 5 * 1024 * 1024;

/**
 * One position as the confirm screen holds it.
 *
 * The parsed bullets and technologies ride along untouched — the screen shows
 * how many there are and saves them as they came. Only the two fields a layout
 * routinely hides, the role and the employer, are editable here; correcting the
 * rest belongs on the profile page, which already has an editor for it.
 */
interface DraftExperience {
  key: number;
  include: boolean;
  role: string;
  company: string;
  source: ResumeIntakeExperience;
}

interface Draft {
  fullName: string;
  headline: string;
  location: string;
  phone: string;
  summary: string;
  skills: string[];
  languages: string[];
  experiences: DraftExperience[];
}

function draftFrom(intake: ResumeIntake): Draft {
  return {
    fullName: intake.full_name ?? '',
    headline: intake.headline ?? '',
    location: intake.location ?? '',
    phone: intake.phone ?? '',
    summary: intake.summary ?? '',
    skills: intake.skills,
    languages: intake.languages,
    experiences: intake.experiences.map((entry, index) => ({
      key: index,
      include: true,
      role: entry.role,
      company: entry.company,
      source: entry,
    })),
  };
}

function toCreate(entry: DraftExperience, position: number): ExperienceCreate {
  const { source } = entry;
  return {
    company: entry.company.trim(),
    role: entry.role.trim(),
    employment_type: source.employment_type,
    location: source.location,
    started_on: source.started_on,
    // The backend refuses an end date on a current position, and the parser can
    // report both when a document prints "2023 - Present · left in 2024".
    ended_on: source.is_current ? null : source.ended_on,
    is_current: source.is_current,
    summary: source.summary || null,
    responsibilities: source.responsibilities,
    technologies: source.technologies,
    position,
  };
}

/* -------------------------------------------------------------------------- */
/* Step 1 — the upload                                                        */
/* -------------------------------------------------------------------------- */

function UploadStep({
  onRead,
  isPending,
  hasStoredText,
  onReadStored,
}: {
  onRead: (file: File) => void;
  isPending: boolean;
  hasStoredText: boolean;
  onReadStored: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const accept = (file: File | undefined) => {
    setLocalError(null);
    if (!file) return;
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    if (!isPdf) {
      setLocalError('Por enquanto aceitamos apenas PDF.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setLocalError(`Esse arquivo tem ${formatBytes(file.size)}. O limite é ${formatBytes(MAX_BYTES)}.`);
      return;
    }
    onRead(file);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    accept(event.dataTransfer.files?.[0]);
  };

  return (
    <Card>
      <div className="card-body">
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            'rounded-xl border border-dashed px-5 py-10 text-center transition-colors duration-150',
            dragging
              ? 'border-accent-500 bg-accent-500/[0.07]'
              : 'border-line-strong bg-surface-sunken',
          )}
        >
          <span
            aria-hidden
            className="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-line bg-surface-raised text-content-subtle"
          >
            <Upload className="h-5 w-5" />
          </span>
          <p className="mt-3 text-md font-semibold text-content">Solte o seu currículo aqui</p>
          <p className="mt-1 text-sm text-content-muted">
            PDF, até {formatBytes(MAX_BYTES)}. É este arquivo que vai junto nas candidaturas.
          </p>

          <input
            ref={inputRef}
            id="onboarding-resume"
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            onChange={(event) => {
              accept(event.target.files?.[0]);
              event.target.value = '';
            }}
          />
          <Button
            variant="primary"
            className="mt-5"
            loading={isPending}
            onClick={() => inputRef.current?.click()}
          >
            Escolher o meu currículo
          </Button>
        </div>

        {localError ? (
          <p role="alert" className="mt-3 text-sm text-danger">
            {localError}
          </p>
        ) : null}

        {hasStoredText ? (
          <p className="mt-4 text-center text-sm text-content-muted">
            Ou{' '}
            <button
              type="button"
              className="font-medium text-accent-400 underline-offset-2 hover:underline"
              onClick={onReadStored}
              disabled={isPending}
            >
              usar o currículo que já está no seu perfil
            </button>
            .
          </p>
        ) : null}
      </div>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Step 2 — the confirmation                                                  */
/* -------------------------------------------------------------------------- */

function ExperienceCard({
  entry,
  onChange,
}: {
  entry: DraftExperience;
  onChange: (next: DraftExperience) => void;
}) {
  const { source } = entry;
  const bullets = source.responsibilities.length;

  return (
    <li
      className={cn(
        'rounded-xl border px-4 py-4 transition-colors duration-150',
        entry.include ? 'border-line bg-surface-sunken' : 'border-line bg-transparent opacity-60',
      )}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Cargo" htmlFor={`role-${entry.key}`}>
          <Input
            id={`role-${entry.key}`}
            value={entry.role}
            placeholder="Desenvolvedor Full Stack"
            onChange={(event) => onChange({ ...entry, role: event.target.value })}
          />
        </Field>
        <Field label="Empresa" htmlFor={`company-${entry.key}`}>
          <Input
            id={`company-${entry.key}`}
            value={entry.company}
            placeholder="Nome da empresa"
            onChange={(event) => onChange({ ...entry, company: event.target.value })}
          />
        </Field>
      </div>

      <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-content-subtle">
        {source.period_text ? <span>{source.period_text}</span> : null}
        {source.location ? <span>{source.location}</span> : null}
        {bullets > 0 ? (
          <span>
            {bullets} {bullets === 1 ? 'atividade' : 'atividades'}
          </span>
        ) : null}
      </p>

      {source.technologies.length > 0 ? (
        <ul className="mt-2.5 flex flex-wrap gap-1.5">
          {source.technologies.slice(0, 8).map((term) => (
            <li
              key={term}
              className="rounded-full border border-line bg-surface-raised px-2 py-0.5 text-2xs text-content-muted"
            >
              {term}
            </li>
          ))}
        </ul>
      ) : null}

      <label className="mt-3 flex items-center gap-2 text-xs text-content-muted">
        <input
          type="checkbox"
          className="h-3.5 w-3.5 rounded border-line-strong"
          checked={entry.include}
          onChange={(event) => onChange({ ...entry, include: event.target.checked })}
        />
        Incluir esta experiência no meu perfil
      </label>
    </li>
  );
}

function ConfirmStep({
  intake,
  draft,
  setDraft,
  existingCount,
  replaceExisting,
  setReplaceExisting,
  onSave,
  isSaving,
  onRestart,
}: {
  intake: ResumeIntake;
  draft: Draft;
  setDraft: (next: Draft) => void;
  existingCount: number;
  replaceExisting: boolean;
  setReplaceExisting: (next: boolean) => void;
  onSave: () => void;
  isSaving: boolean;
  onRestart: () => void;
}) {
  const patch = (partial: Partial<Draft>) => setDraft({ ...draft, ...partial });
  const included = draft.experiences.filter((entry) => entry.include);
  const incomplete = included.filter((entry) => !entry.role.trim() || !entry.company.trim());

  return (
    <div className="space-y-4">
      {intake.warnings.map((warning) => (
        <Note key={warning} tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
          {warning}
        </Note>
      ))}

      <Card>
        <CardHeader title="Você" description="Corrija o que estiver errado." />
        <div className="card-body grid gap-4 sm:grid-cols-2">
          <Field label="Nome" htmlFor="intake-name" className="sm:col-span-2">
            <Input
              id="intake-name"
              value={draft.fullName}
              onChange={(event) => patch({ fullName: event.target.value })}
            />
          </Field>
          <Field
            label="Cargo atual"
            htmlFor="intake-headline"
            hint="Uma linha, como no seu LinkedIn."
            className="sm:col-span-2"
          >
            <Input
              id="intake-headline"
              value={draft.headline}
              placeholder="Desenvolvedor Full Stack"
              onChange={(event) => patch({ headline: event.target.value })}
            />
          </Field>
          <Field label="Onde você mora" htmlFor="intake-location">
            <Input
              id="intake-location"
              value={draft.location}
              onChange={(event) => patch({ location: event.target.value })}
            />
          </Field>
          <Field label="Telefone" htmlFor="intake-phone">
            <Input
              id="intake-phone"
              type="tel"
              value={draft.phone}
              onChange={(event) => patch({ phone: event.target.value })}
            />
          </Field>
          <Field label="Resumo" htmlFor="intake-summary" className="sm:col-span-2">
            <Textarea
              id="intake-summary"
              rows={4}
              value={draft.summary}
              onChange={(event) => patch({ summary: event.target.value })}
            />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Tecnologias"
          description="Enter ou vírgula adiciona. Só o que estiver aqui pode aparecer nos seus currículos."
        />
        <div className="card-body space-y-4">
          <TagEditor
            id="intake-skills"
            tags={draft.skills}
            onChange={(skills) => patch({ skills })}
            placeholder="C#, .NET, React…"
          />
          <div>
            <p className="label">Idiomas</p>
            <TagEditor
              id="intake-languages"
              tags={draft.languages}
              onChange={(languages) => patch({ languages })}
              placeholder="Português, Inglês…"
            />
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Suas experiências"
          description={
            draft.experiences.length > 0
              ? 'Encontramos estas no seu currículo.'
              : 'Não encontramos nenhuma. Você pode adicioná-las depois, no seu perfil.'
          }
        />
        <div className="card-body space-y-3">
          {draft.experiences.length > 0 ? (
            <ul className="space-y-3">
              {draft.experiences.map((entry) => (
                <ExperienceCard
                  key={entry.key}
                  entry={entry}
                  onChange={(next) =>
                    patch({
                      experiences: draft.experiences.map((item) =>
                        item.key === next.key ? next : item,
                      ),
                    })
                  }
                />
              ))}
            </ul>
          ) : null}

          {existingCount > 0 ? (
            <Note tone="neutral" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
              O seu perfil já tem {existingCount}{' '}
              {existingCount === 1 ? 'experiência' : 'experiências'}.
              <label className="mt-2 flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 rounded border-line-strong"
                  checked={replaceExisting}
                  onChange={(event) => setReplaceExisting(event.target.checked)}
                />
                Substituir as anteriores por estas
              </label>
            </Note>
          ) : null}
        </div>
      </Card>

      <div className="sticky bottom-4 z-20">
        <Card className="flex flex-wrap items-center gap-3 border-accent-500/40 px-4 py-3 shadow-lifted">
          <p className="text-sm text-content-muted">
            {included.length > 0
              ? `${included.length} ${included.length === 1 ? 'experiência' : 'experiências'} para salvar`
              : 'Nada marcado para salvar'}
          </p>
          <Button variant="ghost" size="sm" onClick={onRestart} disabled={isSaving}>
            Enviar outro arquivo
          </Button>
          <Button
            variant="primary"
            className="ml-auto"
            loading={isSaving}
            disabled={incomplete.length > 0}
            title={
              incomplete.length > 0
                ? 'Preencha o cargo e a empresa das experiências marcadas'
                : undefined
            }
            onClick={onSave}
            icon={<CheckCircle2 aria-hidden className="h-4 w-4" />}
          >
            Está certo, salvar
          </Button>

          {incomplete.length > 0 ? (
            <p className="w-full text-xs text-warning">
              Preencha o cargo e a empresa das experiências marcadas, ou desmarque-as.
            </p>
          ) : null}
        </Card>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* The page                                                                   */
/* -------------------------------------------------------------------------- */

const STEPS = ['Currículo', 'Conferir', 'Pronto'] as const;

export function Onboarding() {
  const toast = useToast();
  const navigate = useNavigate();
  const { data: profile } = useProfile();
  const { data: experiences } = useExperiences();

  const [intake, setIntake] = useState<ResumeIntake | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [done, setDone] = useState(false);

  const read = useReadResumeIntake({
    onSuccess: (result) => {
      setIntake(result);
      setDraft(draftFrom(result));
    },
    onError: (error) => toast.error('Não conseguimos ler o arquivo', errorMessage(error)),
  });

  const apply = useApplyResumeIntake({
    onSuccess: (result) => {
      setDone(true);
      toast.success(
        'Perfil salvo',
        result.experiences_created > 0
          ? `${result.experiences_created} ${result.experiences_created === 1 ? 'experiência salva' : 'experiências salvas'}.`
          : undefined,
      );
    },
    onError: (error) => toast.error('Não foi possível salvar', errorMessage(error)),
  });

  const existingCount = experiences?.length ?? 0;
  const step = done ? 2 : draft ? 1 : 0;

  const save = () => {
    if (!draft || !intake) return;
    const included = draft.experiences.filter((entry) => entry.include);
    apply.mutate({
      full_name: draft.fullName.trim() || null,
      headline: draft.headline.trim() || null,
      location: draft.location.trim() || null,
      phone: draft.phone.trim() || null,
      summary: draft.summary.trim() || null,
      skills: draft.skills,
      preferred_languages: draft.languages,
      // What the AI reads when scoring a posting. Only sent when the file
      // actually yielded text, so a failed extraction never blanks it.
      resume_text: intake.resume_text || undefined,
      experiences: included.map(toCreate),
      replace_experiences: existingCount > 0 && replaceExisting,
    });
  };

  const restart = () => {
    setIntake(null);
    setDraft(null);
  };

  const heading = useMemo(() => {
    if (done) return 'Perfil pronto';
    if (draft) return 'Encontramos estas informações no seu currículo';
    return 'Vamos começar pelo seu currículo';
  }, [done, draft]);

  return (
    <div className="mx-auto w-full max-w-3xl space-y-5 pb-24">
      <div>
        <ol className="flex items-center gap-2 text-2xs font-medium uppercase tracking-wider text-content-subtle">
          {STEPS.map((label, index) => (
            <li key={label} className="flex items-center gap-2">
              <span className={cn(index <= step && 'text-accent-400')}>{label}</span>
              {index < STEPS.length - 1 ? <span aria-hidden>·</span> : null}
            </li>
          ))}
        </ol>
        <h1 className="mt-2 text-xl leading-snug">{heading}</h1>
        <p className="mt-1.5 text-sm text-content-muted">
          {done
            ? 'Agora é escolher que tipo de vaga você procura.'
            : draft
              ? 'Nada foi salvo ainda. Confira, corrija o que estiver errado e salve.'
              : 'Envie o PDF que você já usa. A gente lê e mostra o que encontrou para você conferir.'}
        </p>
      </div>

      {done ? (
        <Card>
          <div className="card-body space-y-4 text-center">
            <span
              aria-hidden
              className="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-accent-500/40 bg-accent-500/10 text-accent-400"
            >
              <Sparkles className="h-5 w-5" />
            </span>
            <p className="text-md font-semibold text-content">
              Seu currículo é a base de tudo daqui em diante.
            </p>
            <p className="mx-auto max-w-md text-sm text-content-muted">
              Cada candidatura vai partir dele, destacando o que a vaga pede — sem nunca
              acrescentar nada que você não tenha.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3 pt-1">
              <Link to="/profile" className="btn">
                <FileText aria-hidden className="h-4 w-4" />
                Ver meu perfil
              </Link>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate('/searches')}
              >
                Encontrar vagas
                <ArrowRight aria-hidden className="h-4 w-4" />
              </button>
            </div>
          </div>
        </Card>
      ) : draft && intake ? (
        <ConfirmStep
          intake={intake}
          draft={draft}
          setDraft={setDraft}
          existingCount={existingCount}
          replaceExisting={replaceExisting}
          setReplaceExisting={setReplaceExisting}
          onSave={save}
          isSaving={apply.isPending}
          onRestart={restart}
        />
      ) : (
        <UploadStep
          onRead={(file) => read.mutate(file)}
          onReadStored={() => read.mutate(null)}
          isPending={read.isPending}
          hasStoredText={Boolean(profile?.resume_text?.trim())}
        />
      )}
    </div>
  );
}
