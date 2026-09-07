import {
  ArrowUpRight,
  FileText,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Wand2,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  Button,
  Card,
  CardHeader,
  Note,
  SectionLabel,
  Skeleton,
  Textarea,
} from '@/components/primitives';
import { useToast } from '@/components/ToastProvider';
import {
  useApplicationResume,
  useDeriveApplicationResume,
  useUpdateApplicationResume,
} from '@/hooks/useApi';
import { badgeClass } from '@/lib/format';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';
import type { ApplicationResume, ResumeEmphasis, TailoredExperience } from '@/types/api';

interface ApplicationResumePanelProps {
  applicationId: number;
  aiConfigured: boolean;
  className?: string;
}

const EMPHASIS_LABEL: Record<ResumeEmphasis, string> = {
  lead: 'destaque',
  support: 'apoio',
  context: 'contexto',
};

const EMPHASIS_TONE: Record<ResumeEmphasis, 'accent' | 'info' | 'neutral'> = {
  lead: 'accent',
  support: 'info',
  context: 'neutral',
};

/** A skill chip. Highlighted ones are what this posting asked for. */
function Chip({ label, highlighted = false }: { label: string; highlighted?: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
        highlighted
          ? 'border-accent-500/40 bg-accent-500/12 text-accent-400'
          : 'border-line bg-surface-sunken text-content-muted',
      )}
    >
      {label}
    </span>
  );
}

/**
 * One experience as this version presents it.
 *
 * The description is the point: it is composed from the user's own bullets, and
 * the *same* job reads differently here than it does on another application,
 * because a different subset of those bullets was relevant. `omitted` is shown
 * on purpose — a version that quietly drops history is one the user cannot trust.
 */
function ExperienceCard({
  experience,
  keywords,
}: {
  experience: TailoredExperience;
  keywords: string[];
}) {
  const matched = new Set(experience.matched.map((term) => term.toLowerCase()));
  const wanted = new Set(keywords.map((term) => term.toLowerCase()));

  return (
    <li className="rounded-lg border border-line bg-surface-sunken/40 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-sm font-semibold text-content">
          {experience.role}
          {experience.company ? (
            <span className="font-normal text-content-muted"> — {experience.company}</span>
          ) : null}
        </p>
        <span className={badgeClass(EMPHASIS_TONE[experience.emphasis])}>
          {EMPHASIS_LABEL[experience.emphasis]}
          {experience.relevance > 0 ? ` · ${experience.relevance}%` : null}
        </span>
      </div>

      {experience.period || experience.location ? (
        <p className="mt-0.5 text-2xs text-content-subtle">
          {[experience.period, experience.location].filter(Boolean).join(' · ')}
        </p>
      ) : null}

      {experience.highlights.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {experience.highlights.map((line) => (
            <li key={line} className="text-xs leading-relaxed text-content-muted">
              — {line}
            </li>
          ))}
        </ul>
      ) : null}

      {experience.technologies.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {experience.technologies.map((technology) => (
            <li key={technology}>
              <Chip label={technology} highlighted={wanted.has(technology.toLowerCase())} />
            </li>
          ))}
        </ul>
      ) : null}

      {matched.size === 0 ? (
        <p className="mt-2 text-2xs text-content-subtle">
          Nada nesta experiência responde ao anúncio, então ela entra como contexto — o
          histórico continua completo.
        </p>
      ) : null}

      {experience.omitted.length > 0 ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-2xs text-content-subtle hover:text-content-muted">
            {experience.omitted.length} ponto(s) do currículo principal fora desta versão
          </summary>
          <ul className="mt-1.5 space-y-1 border-l border-line pl-2.5">
            {experience.omitted.map((line) => (
              <li key={line} className="text-2xs leading-relaxed text-content-subtle">
                {line}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </li>
  );
}

/** The derived structure: which vacancy, which skills, which experiences. */
function Derivation({ resume }: { resume: ApplicationResume }) {
  const { sections, focus } = resume;
  if (!sections) {
    return (
      <Note tone="neutral" icon={<FileText aria-hidden className="h-4 w-4" />}>
        Esta versão foi gerada antes de o app registrar a estrutura da personalização, então
        só o documento está disponível. Gere novamente para ver quais experiências e
        competências foram priorizadas.
      </Note>
    );
  }

  const keywords = focus?.keywords ?? [];
  const relevantProjects = sections.projects.filter((project) => project.matched.length > 0);

  return (
    <div className="space-y-4">
      {keywords.length > 0 ? (
        <div>
          <SectionLabel>O que esta vaga pede</SectionLabel>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {keywords.map((keyword) => (
              <li key={keyword}>
                <Chip label={keyword} highlighted />
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <SectionLabel>Competências priorizadas</SectionLabel>
        {sections.prioritized_skills.length > 0 ? (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {sections.prioritized_skills.map((skill) => (
              <li key={skill}>
                <Chip label={skill} highlighted />
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 text-xs text-content-subtle">
            Nenhuma das suas competências aparece neste anúncio, então a ordem do currículo
            principal foi mantida.
          </p>
        )}
        {sections.other_skills.length > 0 ? (
          <details className="mt-2">
            <summary className="cursor-pointer text-2xs text-content-subtle hover:text-content-muted">
              Demais competências ({sections.other_skills.length}) — mantidas, só não em
              primeiro lugar
            </summary>
            <ul className="mt-1.5 flex flex-wrap gap-1.5">
              {sections.other_skills.map((skill) => (
                <li key={skill}>
                  <Chip label={skill} />
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>

      {sections.experiences.length > 0 ? (
        <div>
          <SectionLabel>Experiências, na ordem desta candidatura</SectionLabel>
          <ul className="mt-2 space-y-2">
            {sections.experiences.map((experience) => (
              <ExperienceCard
                key={experience.id || `${experience.company}-${experience.role}`}
                experience={experience}
                keywords={keywords}
              />
            ))}
          </ul>
        </div>
      ) : null}

      {relevantProjects.length > 0 ? (
        <div>
          <SectionLabel>Projetos em destaque nesta versão</SectionLabel>
          <ul className="mt-2 space-y-1.5">
            {relevantProjects.map((project) => (
              <li key={project.id || project.name} className="text-xs leading-relaxed">
                <span className="font-medium text-content">{project.name}</span>
                {project.matched.length > 0 ? (
                  <span className="text-content-muted"> — {project.matched.join(', ')}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The resume this one application will use.
 *
 * The user has one master resume and may have ten applications open; this panel
 * is where the version belonging to *this* one is read, understood and edited.
 * Three things it must always answer: which vacancy this version was built for,
 * what was changed relative to the master, and where the master itself is.
 *
 * An application with no version yet is a normal state, not an error — an
 * application prepared before this existed simply offers to build one.
 */
export function ApplicationResumePanel({
  applicationId,
  aiConfigured,
  className,
}: ApplicationResumePanelProps) {
  const toast = useToast();
  const { data, isLoading } = useApplicationResume(applicationId);
  const [draft, setDraft] = useState('');

  // Reseed the editor whenever a new server version arrives (derive / save).
  useEffect(() => {
    setDraft(data?.content ?? '');
  }, [data?.content, data?.updated_at]);

  const derive = useDeriveApplicationResume(applicationId, {
    onSuccess: (resume) =>
      toast.success(
        'Currículo desta candidatura pronto',
        resume.focus?.title
          ? `Adaptado para ${resume.focus.title}.`
          : 'Confira o que foi priorizado abaixo.',
      ),
    onError: (error) => toast.error('Não foi possível gerar esta versão', errorMessage(error)),
  });
  const save = useUpdateApplicationResume(applicationId, {
    onSuccess: () => toast.toast({ title: 'Edições salvas nesta candidatura', variant: 'success' }),
    onError: (error) => toast.error('Não foi possível salvar as edições', errorMessage(error)),
  });

  const dirty = data != null && draft !== data.content;
  const busy = derive.isPending;
  const vacancy = [data?.job_title, data?.job_company].filter(Boolean).join(' — ');

  return (
    <Card className={className}>
      <CardHeader
        title="Currículo desta candidatura"
        description={
          data
            ? 'Uma versão própria do seu currículo principal, adaptada a esta vaga. Editá-la aqui não altera nenhuma outra candidatura.'
            : 'Cada candidatura tem a sua própria versão do currículo, adaptada à vaga.'
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              loading={busy && derive.variables !== 'ai'}
              onClick={() => derive.mutate('deterministic')}
              icon={
                data ? (
                  <RefreshCw aria-hidden className="h-4 w-4" />
                ) : (
                  <Wand2 aria-hidden className="h-4 w-4" />
                )
              }
            >
              {data ? 'Gerar novamente' : 'Gerar para esta vaga'}
            </Button>
            {data ? (
              <Button
                loading={busy && derive.variables === 'ai'}
                disabled={!aiConfigured}
                title={
                  aiConfigured
                    ? 'Reescrever o texto com IA, mantendo a mesma seleção de experiências'
                    : 'Nenhuma chave de API de IA configurada'
                }
                onClick={() => derive.mutate('ai')}
                icon={<Sparkles aria-hidden className="h-4 w-4" />}
              >
                Reescrever com IA
              </Button>
            ) : null}
          </div>
        }
      />

      <div className="card-body space-y-4">
        {isLoading ? (
          <Skeleton className="h-40 w-full rounded-lg" />
        ) : !data ? (
          <div className="space-y-2 text-sm text-content-muted">
            <p>
              Ainda não existe uma versão para esta candidatura. Gerar uma reorganiza e
              reenfatiza o que já está no seu currículo principal para esta vaga — priorizando
              as experiências e competências que o anúncio pede, sem inventar nada.
            </p>
            <p className="text-xs text-content-subtle">
              As outras candidaturas continuam com as versões delas. Nada é enviado a lugar
              nenhum.
            </p>
            <p className="pt-1">
              <Link
                to="/profile"
                className="inline-flex items-center gap-1.5 text-xs font-medium text-accent-400 hover:underline"
              >
                Ver o currículo principal
                <ArrowUpRight aria-hidden className="h-3.5 w-3.5" />
              </Link>
            </p>
          </div>
        ) : (
          <>
            {/* Which vacancy this version exists for — the first thing to know
                when several applications are open at once. */}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-line bg-surface-sunken/60 px-3 py-2">
              <span className="text-2xs uppercase tracking-wide text-content-subtle">
                versão criada para
              </span>
              <span className="text-sm font-medium text-content">
                {vacancy || `candidatura #${data.application_id}`}
              </span>
              {data.focus?.level ? (
                <span className={badgeClass('neutral')}>nível {data.focus.level}</span>
              ) : null}
              <span className={badgeClass(data.strategy === 'ai' ? 'info' : 'neutral')}>
                {data.strategy === 'ai' ? 'texto reescrito por IA' : 'do seu próprio currículo'}
              </span>
              {data.was_edited ? (
                <span className={badgeClass('accent')}>editado por você</span>
              ) : null}
              <Link
                to="/profile"
                className="ml-auto inline-flex items-center gap-1.5 text-xs font-medium text-accent-400 hover:underline"
              >
                Currículo principal
                <ArrowUpRight aria-hidden className="h-3.5 w-3.5" />
              </Link>
            </div>

            {data.is_stale ? (
              <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-4 w-4" />}>
                O seu currículo principal mudou depois que esta versão foi criada. Ela foi
                mantida exatamente como você revisou — gere novamente se quiser trazer as
                alterações para cá.
              </Note>
            ) : null}

            {data.invention_flags.length > 0 ? (
              <Note tone="danger" icon={<TriangleAlert aria-hidden className="h-4 w-4" />}>
                <span className="font-medium">Verifique você mesmo.</span> Aparecem nesta versão,
                mas não no seu currículo principal:{' '}
                <span className="font-medium">{data.invention_flags.join(', ')}</span>. A
                ferramenta sinaliza; ela não remove.
              </Note>
            ) : (
              <Note tone="accent" icon={<ShieldCheck aria-hidden className="h-4 w-4" />}>
                Tudo nesta versão vem do seu currículo principal — nenhuma tecnologia inventada.
              </Note>
            )}

            <Derivation resume={data} />

            {data.unsupported_requirements.length > 0 ? (
              <div>
                <SectionLabel>Lacunas que esta versão não disfarça</SectionLabel>
                <ul className="mt-2 space-y-1.5">
                  {data.unsupported_requirements.map((requirement) => (
                    <li
                      key={requirement}
                      className="flex items-start gap-2 text-xs leading-relaxed text-content-muted"
                    >
                      <TriangleAlert
                        aria-hidden
                        className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning"
                      />
                      <span>{requirement}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-2xs text-content-subtle">
                  Fica de fora do documento de propósito. Uma lacuna admitida é melhor que uma
                  afirmação que não se sustenta na entrevista.
                </p>
              </div>
            ) : null}

            {data.stretch_flags.length > 0 ? (
              <div>
                <SectionLabel>Afirmações no limite — manter, suavizar ou remover</SectionLabel>
                <ul className="mt-2 space-y-2">
                  {data.stretch_flags.map((flag) => (
                    <li key={flag.text} className="text-xs leading-relaxed">
                      <p className="font-medium text-content">“{flag.text}”</p>
                      <p className="mt-0.5 text-content-muted">{flag.why_stretch}</p>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {data.changes.length > 0 ? (
              <details>
                <summary className="cursor-pointer text-xs font-medium text-content-muted hover:text-content">
                  O que mudou em relação ao currículo principal ({data.changes.length})
                </summary>
                <ul className="mt-2 space-y-2">
                  {data.changes.map((change, index) => (
                    <li key={`${change.section}-${index}`} className="text-xs leading-relaxed">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className={badgeClass('accent')}>{change.action}</span>
                        <span className="font-medium text-content">{change.section}</span>
                      </div>
                      <p className="mt-1 text-content-muted">{change.detail}</p>
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}

            <div>
              <SectionLabel>Documento desta candidatura — edite antes de usar</SectionLabel>
              <Textarea
                aria-label="Currículo desta candidatura"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                rows={16}
                className="mt-2 w-full font-mono text-xs leading-relaxed"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
              <Button
                variant="primary"
                loading={save.isPending}
                disabled={!dirty}
                onClick={() => save.mutate(draft)}
                icon={<Save aria-hidden className="h-4 w-4" />}
              >
                Salvar nesta candidatura
              </Button>
              {dirty ? (
                <Button onClick={() => setDraft(data.content)}>Descartar edições</Button>
              ) : null}
              <span className="ml-auto inline-flex items-center gap-1.5 text-[11px] text-content-subtle">
                {data.model ? (
                  <>
                    <Sparkles aria-hidden className="h-3.5 w-3.5" />
                    {data.model}
                  </>
                ) : (
                  <FileText aria-hidden className="h-3.5 w-3.5" />
                )}
              </span>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}
