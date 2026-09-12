import {
  Briefcase,
  FileText,
  ListOrdered,
  MailCheck,
  MessageSquare,
  ShieldAlert,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Card, CardHeader } from '@/components/primitives';
import { ScoreBadge } from '@/components/ScoreBadge';
import { useApplicationResume } from '@/hooks/useApi';
import { cn } from '@/lib/utils';
import type { ApplicationDetail } from '@/types/api';

export interface SubmissionSummaryProps {
  application: ApplicationDetail;
  className?: string;
}

type Tone = 'neutral' | 'warn' | 'bad';

const TONE_TEXT: Record<Tone, string> = {
  neutral: 'text-content-muted',
  warn: 'text-warning',
  bad: 'text-danger',
};

function Row({
  icon: Icon,
  label,
  value,
  detail,
  tone = 'neutral',
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail?: string;
  tone?: Tone;
}) {
  return (
    <li className="flex items-start gap-2.5">
      <Icon
        aria-hidden
        className={cn('mt-0.5 h-4 w-4 shrink-0', tone === 'neutral' ? 'text-content-subtle' : TONE_TEXT[tone])}
      />
      <div className="min-w-0 flex-1">
        <p className="text-2xs uppercase tracking-wider text-content-subtle">{label}</p>
        <p className={cn('text-sm leading-snug', tone === 'neutral' ? 'text-content' : TONE_TEXT[tone])}>
          {value}
        </p>
        {detail ? <p className="mt-0.5 text-xs text-content-subtle">{detail}</p> : null}
      </div>
    </li>
  );
}

/**
 * Exactly what goes out, in one place, above everything that can edit it.
 *
 * The review screen is a stack of editors — letter, answers, resume — and a
 * reviewer scrolling through them is reading *parts*. Approval is a decision
 * about the whole, so the whole is stated first: which vacancy, which resume
 * file and how far it drifted from the master, how long the letter is, how many
 * screening answers and how many of them are still flagged.
 *
 * It describes the **saved record**, not the draft on screen, because that
 * record is what the submission rebuilds from. Unsaved edits are a separate,
 * already-enforced gate: approval stays disabled while the draft is dirty.
 *
 * The attached file and the per-vacancy version are two rows on purpose. The
 * employer receives the PDF from the profile — the same one every time — and
 * the adapted document is never rendered into it. Stating them together would
 * read as "the attachment carries these changes", which is the single most
 * expensive thing this screen could get wrong.
 */
export function SubmissionSummary({ application, className }: SubmissionSummaryProps) {
  const { data: resume } = useApplicationResume(application.id);

  const job = application.job;
  const letter = (application.cover_letter ?? '').trim();
  const answers = application.screening_answers;
  const flagged = answers.filter((answer) => answer.needs_review).length;
  const comparison = resume?.comparison ?? null;
  const invented = comparison?.invented ?? [];

  const isExternal = application.channel === 'external';

  return (
    <Card className={className}>
      <CardHeader
        title={isExternal ? 'O que você vai levar' : 'O que será enviado'}
        description={
          isExternal
            ? 'Esta vaga é respondida no site da empresa. Isto é o material preparado para você levar.'
            : 'Exatamente isto, e nada além disto, chega ao empregador quando você aprovar.'
        }
      />
      <div className="card-body">
        <ul className="space-y-3.5">
          <li className="flex items-start gap-3">
            <ScoreBadge score={job?.score ?? null} size="md" className="mt-0.5 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="text-2xs uppercase tracking-wider text-content-subtle">Vaga</p>
              <p className="truncate text-sm font-medium text-content">
                {job?.title ?? `Candidatura #${application.id}`}
              </p>
              <p className="truncate text-xs text-content-subtle">
                {job?.company ?? 'Empresa desconhecida'}
              </p>
            </div>
          </li>

          {/* Two rows, not one, and the wording is deliberate. The file the
              employer receives is the PDF from the profile — the same one on
              every application. The per-vacancy version is a document to read,
              copy or attach by hand; it is never rendered into that file.
              Folding them into a single "Currículo" row reads as though the
              attachment carries the adaptation, which it does not. */}
          <Row
            icon={FileText}
            label="Arquivo que vai anexado"
            value={application.resume_filename ?? 'Nenhum arquivo anexado'}
            tone={application.resume_filename ? 'neutral' : 'warn'}
            detail="É o PDF do seu perfil, igual em todas as candidaturas."
          />

          {comparison && comparison.is_comparable ? (
            <Row
              icon={ListOrdered}
              label="Versão para esta vaga"
              value={`${comparison.changes_total} ${
                comparison.changes_total === 1 ? 'alteração' : 'alterações'
              } · ${invented.length} ${
                invented.length === 1 ? 'informação inventada' : 'informações inventadas'
              }`}
              detail="Um documento para você ler e reaproveitar — ele não entra no PDF anexado."
            />
          ) : null}

          <Row
            icon={MailCheck}
            label="Carta de apresentação"
            value={
              letter
                ? `${letter.length} ${letter.length === 1 ? 'caractere' : 'caracteres'}`
                : 'Nenhuma — o formulário vai sem carta'
            }
            tone={letter ? 'neutral' : 'warn'}
          />

          <Row
            icon={MessageSquare}
            label="Respostas de triagem"
            value={
              answers.length === 0
                ? 'Nenhuma pergunta foi feita'
                : `${answers.length} ${answers.length === 1 ? 'resposta' : 'respostas'}`
            }
            tone={flagged > 0 ? 'warn' : 'neutral'}
            detail={
              flagged > 0
                ? `${flagged} ${flagged === 1 ? 'precisa' : 'precisam'} da sua confirmação antes de aprovar`
                : undefined
            }
          />

          {invented.length > 0 ? (
            <Row
              icon={ShieldAlert}
              label="Atenção"
              tone="bad"
              value={`${invented.join(', ')} não ${invented.length === 1 ? 'está' : 'estão'} no seu currículo principal`}
              detail="Confira antes de aprovar — isto sai em seu nome."
            />
          ) : null}

          {job?.url ? (
            <Row
              icon={Briefcase}
              label="Anúncio"
              value={job.url}
              detail="Abra e confira se a vaga ainda é a que você leu."
            />
          ) : null}
        </ul>
      </div>
    </Card>
  );
}
