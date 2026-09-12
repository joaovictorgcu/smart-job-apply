import {
  ArrowUpRight,
  CircleAlert,
  FileText,
  Pencil,
  RefreshCw,
  Save,
  Star,
  TriangleAlert,
  Wand2,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { EmptyState } from '@/components/EmptyState';
import { ResumeComparisonPanel } from '@/components/ResumeComparisonPanel';
import {
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  Note,
  SectionLabel,
  Skeleton,
  Textarea,
} from '@/components/primitives';
import { useToast } from '@/components/ToastProvider';
import {
  useAdaptApplicationResume,
  useApplicationResume,
  useResumeVersions,
  useUpdateApplicationResume,
} from '@/hooks/useApi';
import {
  applicationStatusLabel,
  badgeClass,
  experiencePeriod,
  fitFactorLabel,
  formatDateTime,
  resumeChangeLabel,
  RESUME_CHANGE_ORDER,
  scoreTone,
} from '@/lib/format';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';
import type {
  AdaptedExperience,
  AdaptedExperienceEdit,
  ApplicationResume,
  ResumeChange,
} from '@/types/api';

type TabKey = 'resume' | 'changes' | 'versions';

const TABS: ReadonlyArray<{ key: TabKey; label: string }> = [
  { key: 'resume', label: 'Currículo' },
  { key: 'changes', label: 'O que foi adaptado' },
  { key: 'versions', label: 'Outras versões' },
];

interface Draft {
  headline: string;
  summary: string;
  skills: string;
  experiences: AdaptedExperienceEdit[];
}

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

function draftFrom(resume: ApplicationResume): Draft {
  return {
    headline: resume.headline ?? '',
    summary: resume.summary ?? '',
    skills: resume.skills.join(', '),
    experiences: resume.experiences.map((experience) => ({
      summary: experience.summary,
      responsibilities: experience.responsibilities,
      technologies: experience.technologies,
      results: experience.results,
    })),
  };
}

/** A term chip, accented when this posting is the reason it is being shown. */
function Term({ children, matched }: { children: string; matched?: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-2xs font-medium',
        matched
          ? 'border-accent-500/35 bg-accent-500/12 text-accent-400'
          : 'border-line bg-surface-sunken text-content-subtle',
      )}
    >
      {children}
    </span>
  );
}

function ExperienceView({ experience }: { experience: AdaptedExperience }) {
  const matched = new Set(experience.matched_terms.map((term) => term.toLowerCase()));

  return (
    <li className="border-t border-line pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-sm font-semibold text-content">
          {experience.role} <span className="font-normal text-content-muted">· {experience.company}</span>
        </p>
        <p className="text-2xs text-content-subtle">
          {experiencePeriod(experience.started_on, experience.ended_on, experience.is_current)}
          {experience.location ? ` · ${experience.location}` : ''}
        </p>
      </div>

      {experience.relevance > 0 ? (
        <p className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <span className={badgeClass(scoreTone(experience.relevance))}>
            {experience.relevance}% de relação com a vaga
          </span>
          {experience.promoted > 0 ? (
            <span className={badgeClass('neutral')}>
              {experience.promoted} {experience.promoted === 1 ? 'item' : 'itens'} promovidos
            </span>
          ) : null}
        </p>
      ) : null}

      {experience.summary ? (
        <p className="mt-2 text-xs leading-relaxed text-content-muted">{experience.summary}</p>
      ) : null}

      {experience.responsibilities.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {experience.responsibilities.map((line) => (
            <li key={line} className="flex gap-2 text-xs leading-relaxed text-content-muted">
              <span aria-hidden className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-content-subtle" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {experience.results.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {experience.results.map((line) => (
            <li key={line} className="flex gap-2 text-xs leading-relaxed text-content">
              <Star aria-hidden className="mt-0.5 h-3 w-3 shrink-0 text-accent-400" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {experience.technologies.length > 0 ? (
        <p className="mt-2 flex flex-wrap gap-1">
          {experience.technologies.map((term) => (
            <Term key={term} matched={matched.has(term.toLowerCase())}>
              {term}
            </Term>
          ))}
        </p>
      ) : null}

      {experience.projects.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {experience.projects.map((project) => (
            <li key={project.name} className="rounded-lg border border-line bg-surface-sunken px-3 py-2">
              <p className="text-xs font-medium text-content">{project.name}</p>
              {project.description ? (
                <p className="mt-0.5 text-2xs leading-relaxed text-content-muted">
                  {project.description}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function ExperienceEditor({
  experience,
  draft,
  index,
  disabled,
  onChange,
}: {
  experience: AdaptedExperience;
  draft: AdaptedExperienceEdit;
  index: number;
  disabled: boolean;
  onChange: (next: AdaptedExperienceEdit) => void;
}) {
  return (
    <li className="space-y-2 border-t border-line pt-3 first:border-t-0 first:pt-0">
      <p className="text-sm font-semibold text-content">
        {experience.role} <span className="font-normal text-content-muted">· {experience.company}</span>
      </p>
      {/* Company, role and period are not editable here: this screen adapts a
          resume, it does not invent a job history. Fix those on the master. */}
      <Field label="Resumo" htmlFor={`exp-${index}-summary`}>
        <Textarea
          id={`exp-${index}-summary`}
          rows={2}
          value={draft.summary}
          disabled={disabled}
          onChange={(event) => onChange({ ...draft, summary: event.target.value })}
        />
      </Field>
      <Field
        label="Responsabilidades"
        htmlFor={`exp-${index}-responsibilities`}
        hint="Uma por linha."
      >
        <Textarea
          id={`exp-${index}-responsibilities`}
          rows={4}
          value={draft.responsibilities.join('\n')}
          disabled={disabled}
          onChange={(event) =>
            onChange({ ...draft, responsibilities: lines(event.target.value) })
          }
        />
      </Field>
      <Field label="Resultados" htmlFor={`exp-${index}-results`} hint="Um por linha.">
        <Textarea
          id={`exp-${index}-results`}
          rows={2}
          value={draft.results.join('\n')}
          disabled={disabled}
          onChange={(event) => onChange({ ...draft, results: lines(event.target.value) })}
        />
      </Field>
      <Field label="Tecnologias" htmlFor={`exp-${index}-technologies`} hint="Separadas por vírgula.">
        <Input
          id={`exp-${index}-technologies`}
          value={draft.technologies.join(', ')}
          disabled={disabled}
          onChange={(event) => onChange({ ...draft, technologies: commas(event.target.value) })}
        />
      </Field>
    </li>
  );
}

function ChangeReport({ resume }: { resume: ApplicationResume }) {
  const grouped = useMemo(() => {
    const buckets = new Map<string, ResumeChange[]>();
    for (const change of resume.changes) {
      const bucket = buckets.get(change.kind) ?? [];
      bucket.push(change);
      buckets.set(change.kind, bucket);
    }
    const known = RESUME_CHANGE_ORDER.filter((kind) => buckets.has(kind));
    const extra = [...buckets.keys()].filter((kind) => !RESUME_CHANGE_ORDER.includes(kind));
    return [...known, ...extra].map((kind) => [kind, buckets.get(kind) ?? []] as const);
  }, [resume.changes]);

  if (resume.changes.length === 0) {
    return (
      <div className="space-y-4">
        {/* Still shown with no changes: "nothing moved" is the strongest form
            of "this is still your resume", and the invention count is worth
            stating either way. */}
        <ResumeComparisonPanel comparison={resume.comparison} />
        <EmptyState
          compact
          title="Nada foi reorganizado"
          description="O anúncio não menciona nenhuma tecnologia que este currículo reconheça, então a ordem do currículo principal foi mantida."
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Before the adherence bars: how much changed is what the reviewer has
          to sign off on, and the score is context for it. */}
      <ResumeComparisonPanel comparison={resume.comparison} />

      {resume.fit_factors.length > 0 ? (
        <div className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <SectionLabel>Aderência à vaga</SectionLabel>
            <span className={badgeClass(scoreTone(resume.fit_score))}>{resume.fit_score}%</span>
          </div>
          <ul className="mt-2 space-y-1.5">
            {resume.fit_factors.map((factor) => (
              <li key={factor.factor} className="flex items-center gap-2">
                <span className="w-40 shrink-0 text-2xs text-content-muted">
                  {fitFactorLabel(factor.factor)}
                </span>
                <div className="h-1.5 flex-1 overflow-hidden rounded bg-surface-overlay">
                  <div
                    className={cn(
                      'h-full origin-left rounded',
                      factor.score >= 80
                        ? 'bg-success'
                        : factor.score >= 60
                          ? 'bg-accent-500'
                          : factor.score >= 40
                            ? 'bg-warning'
                            : 'bg-danger',
                    )}
                    style={{ width: `${factor.score}%` }}
                  />
                </div>
                <span className="tabular w-16 shrink-0 text-right text-2xs text-content-subtle">
                  {factor.factor === 'seniority'
                    ? `${factor.matched}/${factor.total} anos`
                    : `${factor.matched}/${factor.total}`}
                </span>
                <span
                  className="tabular w-10 shrink-0 text-right text-2xs text-content-subtle"
                  title={`Peso de ${factor.weight_pct}% na aderência`}
                >
                  ×{factor.weight_pct}%
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-2xs leading-relaxed text-content-subtle">
            Calculado a partir do que o anúncio pede e do que o seu histórico comprova. Nada aqui é
            enviado à empresa.
          </p>
        </div>
      ) : null}

      {grouped.map(([kind, changes]) => (
        <div key={kind}>
          <SectionLabel>{resumeChangeLabel(kind)}</SectionLabel>
          <ul className="mt-2 space-y-1.5">
            {changes.map((change) => (
              <li key={`${kind}-${change.target}`} className="text-xs leading-relaxed">
                <span className="font-medium text-content">{change.target}</span>
                {change.total > 0 ? (
                  <span className="text-content-subtle">
                    {' '}
                    — {change.matched} de {change.total} itens subiram na descrição
                  </span>
                ) : null}
                {change.terms.length > 0 ? (
                  <span className="mt-1 flex flex-wrap gap-1">
                    {change.terms.map((term) => (
                      <Term key={term} matched>
                        {term}
                      </Term>
                    ))}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {resume.uncovered_requirements.length > 0 ? (
        <div>
          <SectionLabel>O que o anúncio pede e o histórico não cobre</SectionLabel>
          <p className="mt-2 flex flex-wrap gap-1">
            {resume.uncovered_requirements.map((term) => (
              <Term key={term}>{term}</Term>
            ))}
          </p>
          <p className="mt-2 text-2xs leading-relaxed text-content-subtle">
            Aparecem aqui, e não no currículo. A adaptação reorganiza o que você já tem — ela nunca
            adiciona uma tecnologia que o seu histórico não comprova.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function VersionList({ applicationId }: { applicationId: number }) {
  const { data, isLoading, isError } = useResumeVersions();

  if (isLoading) return <Skeleton className="h-24 w-full rounded-lg" />;
  if (isError) {
    return <Note tone="danger">Não foi possível carregar as outras versões.</Note>;
  }

  const versions = data ?? [];
  const others = versions.filter((version) => version.application_id !== applicationId);

  return (
    <div className="space-y-3">
      <Link
        to="/profile"
        className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface-sunken px-3.5 py-3 hover:border-line-strong"
      >
        <span className="min-w-0">
          <span className="block text-xs font-semibold text-content">Currículo principal</span>
          <span className="block text-2xs text-content-subtle">
            A origem de todas as versões. Editá-lo não altera nenhuma candidatura já existente.
          </span>
        </span>
        <ArrowUpRight aria-hidden className="h-4 w-4 shrink-0 text-content-subtle" />
      </Link>

      {others.length === 0 ? (
        <p className="text-xs text-content-subtle">
          Esta é a sua única versão adaptada até agora. Cada nova candidatura ganha a sua própria.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {others.map((version) => (
            <li key={version.application_id}>
              <Link
                to={`/applications/${version.application_id}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-line px-3.5 py-2.5 hover:border-line-strong hover:bg-surface-overlay/60"
              >
                <span className="min-w-0">
                  <span className="block truncate text-xs font-medium text-content">
                    {version.job_title}
                  </span>
                  <span className="block truncate text-2xs text-content-subtle">
                    {version.job_company} · {applicationStatusLabel(version.application_status)}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1.5">
                  {version.has_fit ? (
                    <span className={badgeClass(scoreTone(version.fit_score))}>
                      {version.fit_score}%
                    </span>
                  ) : null}
                  {version.was_edited ? (
                    <span className={badgeClass('neutral')}>editada</span>
                  ) : null}
                  {version.is_stale ? (
                    <span className={badgeClass('warning')}>desatualizada</span>
                  ) : null}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export interface ApplicationResumePanelProps {
  applicationId: number;
  jobTitle?: string | null;
  jobCompany?: string | null;
  className?: string;
}

/**
 * The resume one application presents, and why it looks the way it does.
 *
 * Three tabs rather than three screens, because the questions a reviewer asks
 * here are about one document: what does this application send, what was
 * reorganised for this posting, and how does it relate to my other versions.
 *
 * Editing writes only this application's copy. The master resume is a different
 * document (linked from "Outras versões") and every sibling application is a
 * different row, so nothing typed here can reach them — the backend enforces
 * that, and the copy shows it by reporting itself *stale* rather than silently
 * changing when the master moves.
 */
export function ApplicationResumePanel({
  applicationId,
  jobTitle,
  jobCompany,
  className,
}: ApplicationResumePanelProps) {
  const toast = useToast();
  const { data: resume, isLoading, isError } = useApplicationResume(applicationId);
  const [tab, setTab] = useState<TabKey>('resume');
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);

  // Server state wins whenever the document itself changes underneath us, but a
  // plain refetch of identical data must not wipe edits in progress — the same
  // version-key trick `ApplicationReviewPanel` uses.
  const syncKey = resume ? `${resume.application_id}:${resume.version}:${resume.updated_at ?? ''}` : '';
  const [syncedKey, setSyncedKey] = useState(syncKey);
  if (syncKey !== syncedKey) {
    setSyncedKey(syncKey);
    setDraft(resume ? draftFrom(resume) : null);
    setEditing(false);
  }

  const adapt = useAdaptApplicationResume(applicationId, {
    onSuccess: () => {
      setTab('changes');
      toast.success('Currículo adaptado', 'Veja em “O que foi adaptado” o que mudou para esta vaga.');
    },
    onError: (error) => toast.error('Não foi possível adaptar o currículo', errorMessage(error)),
  });

  const save = useUpdateApplicationResume(applicationId, {
    onSuccess: () => {
      setEditing(false);
      toast.toast({ title: 'Versão desta candidatura salva', variant: 'success' });
    },
    onError: (error) => toast.error('Não foi possível salvar', errorMessage(error)),
  });

  const dirty = useMemo(() => {
    if (!resume || !draft) return false;
    return JSON.stringify(draft) !== JSON.stringify(draftFrom(resume));
  }, [draft, resume]);

  const busy = adapt.isPending || save.isPending;
  const title = resume?.job_title ?? jobTitle ?? null;
  const company = resume?.job_company ?? jobCompany ?? null;

  const header = (
    <CardHeader
      title="Currículo desta candidatura"
      description={
        title
          ? `Adaptado para ${title}${company ? ` · ${company}` : ''}`
          : 'Uma versão do seu currículo principal, adaptada a esta vaga.'
      }
      actions={
        <>
          {resume && resume.fit_factors.length > 0 ? (
            <span className={badgeClass(scoreTone(resume.fit_score))}>
              Aderência {resume.fit_score}%
            </span>
          ) : null}
          <Button
            size="sm"
            loading={adapt.isPending}
            disabled={busy}
            onClick={() => adapt.mutate()}
            icon={
              resume ? (
                <RefreshCw aria-hidden className="h-3.5 w-3.5" />
              ) : (
                <Wand2 aria-hidden className="h-3.5 w-3.5" />
              )
            }
          >
            {resume ? 'Adaptar novamente' : 'Adaptar currículo'}
          </Button>
        </>
      }
    />
  );

  if (isLoading) {
    return (
      <Card className={className} aria-busy="true">
        {header}
        <div className="card-body space-y-3">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-32 w-full rounded-lg" />
        </div>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className={className}>
        {header}
        <div className="card-body">
          <Note tone="danger" icon={<CircleAlert aria-hidden className="h-4 w-4" />}>
            Não foi possível carregar o currículo desta candidatura. Recarregue a página para tentar
            de novo.
          </Note>
        </div>
      </Card>
    );
  }

  if (!resume) {
    return (
      <Card className={className}>
        {header}
        <div className="card-body">
          <EmptyState
            icon={FileText}
            compact
            title="Esta candidatura ainda não tem currículo próprio"
            description="Gere uma versão do seu currículo principal adaptada a esta vaga. Ela fica só nesta candidatura — o principal e as outras candidaturas não mudam."
            action={
              <Button
                variant="primary"
                loading={adapt.isPending}
                onClick={() => adapt.mutate()}
                icon={<Wand2 aria-hidden className="h-4 w-4" />}
              >
                Adaptar currículo para esta vaga
              </Button>
            }
          />
        </div>
      </Card>
    );
  }

  return (
    <Card className={className}>
      {header}

      <div className="card-body space-y-4">
        {resume.is_stale ? (
          <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-4 w-4" />}>
            O seu currículo principal mudou depois desta versão ser gerada. Esta candidatura continua
            usando exatamente o que você está vendo — use <strong>Adaptar novamente</strong> se quiser
            trazer as mudanças.
          </Note>
        ) : null}

        <div role="tablist" aria-label="Currículo desta candidatura" className="flex flex-wrap gap-1">
          {TABS.map((entry) => (
            <button
              key={entry.key}
              type="button"
              role="tab"
              aria-selected={tab === entry.key}
              onClick={() => setTab(entry.key)}
              className={cn(
                'rounded-lg border px-3 py-1.5 text-xs font-medium transition duration-150 ease-snap',
                tab === entry.key
                  ? 'border-accent-500/35 bg-accent-500/12 text-accent-400'
                  : 'border-transparent text-content-muted hover:bg-surface-overlay hover:text-content',
              )}
            >
              {entry.label}
            </button>
          ))}
        </div>

        {tab === 'resume' ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className={badgeClass('neutral')}>versão {resume.version}</span>
              {resume.was_edited ? (
                <span className={badgeClass('info')}>editada por você</span>
              ) : null}
              <span className="ml-auto text-2xs text-content-subtle">
                adaptada em {formatDateTime(resume.adapted_at)}
              </span>
            </div>

            {editing && draft ? (
              <div className="space-y-3">
                <Field label="Título" htmlFor="resume-headline">
                  <Input
                    id="resume-headline"
                    value={draft.headline}
                    disabled={busy}
                    onChange={(event) => setDraft({ ...draft, headline: event.target.value })}
                  />
                </Field>
                <Field label="Resumo" htmlFor="resume-summary">
                  <Textarea
                    id="resume-summary"
                    rows={3}
                    value={draft.summary}
                    disabled={busy}
                    onChange={(event) => setDraft({ ...draft, summary: event.target.value })}
                  />
                </Field>
                <Field
                  label="Competências"
                  htmlFor="resume-skills"
                  hint="Separadas por vírgula, na ordem em que devem aparecer."
                >
                  <Input
                    id="resume-skills"
                    value={draft.skills}
                    disabled={busy}
                    onChange={(event) => setDraft({ ...draft, skills: event.target.value })}
                  />
                </Field>

                <ul className="space-y-3">
                  {resume.experiences.map((experience, index) => (
                    <ExperienceEditor
                      key={`${experience.company}-${experience.role}-${index}`}
                      experience={experience}
                      draft={draft.experiences[index]}
                      index={index}
                      disabled={busy}
                      onChange={(next) =>
                        setDraft({
                          ...draft,
                          experiences: draft.experiences.map((entry, position) =>
                            position === index ? next : entry,
                          ),
                        })
                      }
                    />
                  ))}
                </ul>
              </div>
            ) : (
              <div className="space-y-4">
                {resume.headline ? (
                  <p className="text-sm font-medium text-content">{resume.headline}</p>
                ) : null}
                {resume.summary ? (
                  <p className="text-xs leading-relaxed text-content-muted">{resume.summary}</p>
                ) : null}

                {resume.skills.length > 0 ? (
                  <div>
                    <SectionLabel>Competências</SectionLabel>
                    <p className="mt-1.5 flex flex-wrap gap-1">
                      {resume.skills.map((skill) => (
                        <Term key={skill} matched={resume.highlighted_skills.includes(skill)}>
                          {skill}
                        </Term>
                      ))}
                    </p>
                  </div>
                ) : null}

                {resume.experiences.length > 0 ? (
                  <div>
                    <SectionLabel>Experiência — na ordem que faz sentido para esta vaga</SectionLabel>
                    <ul className="mt-2 space-y-3">
                      {resume.experiences.map((experience, index) => (
                        <ExperienceView
                          key={`${experience.company}-${experience.role}-${index}`}
                          experience={experience}
                        />
                      ))}
                    </ul>
                  </div>
                ) : (
                  <EmptyState
                    compact
                    title="Nenhuma experiência no currículo principal"
                    description="Cadastre as suas experiências no Perfil para que elas possam ser priorizadas por vaga."
                  />
                )}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
              {editing ? (
                <>
                  <Button
                    variant="primary"
                    loading={save.isPending}
                    disabled={!dirty || busy}
                    onClick={() =>
                      draft &&
                      save.mutate({
                        headline: draft.headline.trim() || null,
                        summary: draft.summary.trim() || null,
                        skills: commas(draft.skills),
                        experiences: draft.experiences,
                      })
                    }
                    icon={<Save aria-hidden className="h-4 w-4" />}
                  >
                    Salvar esta versão
                  </Button>
                  <Button
                    disabled={save.isPending}
                    onClick={() => {
                      setDraft(draftFrom(resume));
                      setEditing(false);
                    }}
                  >
                    Cancelar
                  </Button>
                </>
              ) : (
                <Button
                  disabled={busy}
                  onClick={() => {
                    setDraft(draftFrom(resume));
                    setEditing(true);
                  }}
                  icon={<Pencil aria-hidden className="h-4 w-4" />}
                >
                  Editar esta versão
                </Button>
              )}
              <span className="ml-auto text-2xs text-content-subtle">
                As edições ficam nesta candidatura. O currículo principal não muda.
              </span>
            </div>
          </div>
        ) : null}

        {tab === 'changes' ? <ChangeReport resume={resume} /> : null}
        {tab === 'versions' ? <VersionList applicationId={applicationId} /> : null}
      </div>
    </Card>
  );
}
