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
                  aria-label={`Remover ${tag}`}
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
    onSuccess: () => toast.success('Perfil salvo'),
    onError: (error) => toast.error('Não foi possível salvar o seu perfil', errorMessage(error)),
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
        title="Perfil"
        description="O que a IA sabe sobre você. Tudo aqui alimenta a pontuação de vagas, as cartas de apresentação e as respostas de triagem."
      />

      <Card>
        <CardHeader title="Informações básicas" />
        <div className="card-body grid gap-4 sm:grid-cols-2">
          <Field
            label="Título"
            htmlFor="profile-headline"
            hint="Uma linha, como o título do seu LinkedIn."
            className="sm:col-span-2"
          >
            <Input
              id="profile-headline"
              value={draft.headline}
              onChange={(event) => patch({ headline: event.target.value })}
              placeholder="Engenheiro backend sênior — Python, sistemas distribuídos"
            />
          </Field>

          <Field label="Localização" htmlFor="profile-location">
            <Input
              id="profile-location"
              value={draft.location}
              onChange={(event) => patch({ location: event.target.value })}
              placeholder="Lisboa, Portugal"
            />
          </Field>

          <Field label="Telefone" htmlFor="profile-phone" hint="Usado para preencher campos de contato nos formulários.">
            <Input
              id="profile-phone"
              type="tel"
              value={draft.phone}
              onChange={(event) => patch({ phone: event.target.value })}
              placeholder="+351 900 000 000"
            />
          </Field>

          <Field label="Anos de experiência" htmlFor="profile-years">
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
          title="Resumo"
          description="Um breve resumo profissional. A IA se apoia nisso para as cartas de apresentação."
        />
        <div className="card-body">
          <label htmlFor="profile-summary" className="sr-only">
            Resumo
          </label>
          <Textarea
            id="profile-summary"
            rows={5}
            value={draft.summary}
            onChange={(event) => patch({ summary: event.target.value })}
            placeholder="Oito anos construindo sistemas de pagamento, principalmente Python e Postgres…"
          />
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Habilidades" description="Pressione Enter ou vírgula para adicionar. Backspace remove a última." />
          <div className="card-body">
            <label htmlFor="profile-skills" className="sr-only">
              Adicionar uma habilidade
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
            title="Idiomas preferidos"
            description="Em quais idiomas você se sente confortável para se candidatar."
          />
          <div className="card-body">
            <label htmlFor="profile-languages" className="sr-only">
              Adicionar um idioma
            </label>
            <TagEditor
              id="profile-languages"
              tags={draft.languages}
              onChange={(languages) => patch({ languages })}
              placeholder="Inglês, Português…"
            />
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Currículo"
          description="O PDF é enviado ao LinkedIn; a versão em texto é o que a IA lê."
        />
        <div className="card-body grid gap-4 lg:grid-cols-2">
          <ResumeUploader filename={profile?.resume_filename ?? null} />

          <div>
            <label htmlFor="profile-resume-text" className="label">
              Texto do currículo
            </label>
            <Textarea
              id="profile-resume-text"
              rows={10}
              value={draft.resumeText}
              onChange={(event) => patch({ resumeText: event.target.value })}
              placeholder="Cole aqui o texto puro do seu currículo."
            />
            <p className="hint">
              Mantenha isto em sincronia com o PDF. Afirmações que não batem são o que as perguntas de
              triagem pegam.
            </p>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Banco de respostas"
          description="Respostas fixas para as perguntas que o LinkedIn faz sem parar."
          actions={
            <Button
              size="sm"
              onClick={() => {
                answerRowId += 1;
                patch({ answers: [...draft.answers, { id: answerRowId, key: '', value: '' }] });
              }}
              icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
            >
              Adicionar resposta
            </Button>
          }
        />
        <div className="card-body space-y-3">
          <Note tone="neutral" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
            A IA consulta este banco primeiro e só inventa uma resposta quando nada corresponde — e
            qualquer resposta que ela invente com baixa confiança é sinalizada para a sua revisão antes
            do envio. Use chaves como <span className="font-mono">work_authorization</span> ou{' '}
            <span className="font-mono">notice_period</span>.
          </Note>

          {draft.answers.length === 0 ? (
            <p className="text-xs text-content-subtle">
              Nenhuma resposta salva ainda. Adicione as que você digita com mais frequência.
            </p>
          ) : (
            <ul className="space-y-2">
              {draft.answers.map((row, index) => (
                <li key={row.id} className="flex flex-col gap-2 sm:flex-row sm:items-start">
                  <div className="sm:w-64">
                    <label htmlFor={`answer-key-${row.id}`} className="sr-only">
                      Chave da pergunta {index + 1}
                    </label>
                    <Input
                      id={`answer-key-${row.id}`}
                      value={row.key}
                      placeholder="chave da pergunta"
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
                      Resposta {index + 1}
                    </label>
                    <Input
                      id={`answer-value-${row.id}`}
                      value={row.value}
                      placeholder="resposta"
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
                    aria-label={`Remover resposta ${row.key || index + 1}`}
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
            <p className="text-sm text-content-muted">Você tem alterações não salvas.</p>
            <Button
              className="ml-auto"
              onClick={() => baseline && setDraft(baseline)}
              disabled={update.isPending}
            >
              Reverter
            </Button>
            <Button
              variant="primary"
              loading={update.isPending}
              onClick={save}
              icon={<Save aria-hidden className="h-4 w-4" />}
            >
              Salvar perfil
            </Button>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
