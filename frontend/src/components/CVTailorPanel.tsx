import { FileText, RefreshCw, Save, ShieldCheck, Sparkles, TriangleAlert, Wand2 } from 'lucide-react';
import { useEffect, useState } from 'react';

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
import { useTailoredResume, useTailorResume, useUpdateTailoredResume } from '@/hooks/useApi';
import { badgeClass } from '@/lib/format';
import { errorMessage } from '@/services/client';

interface CVTailorPanelProps {
  jobId: number;
  aiConfigured: boolean;
}

/**
 * Generate, review and edit a resume tailored to one job.
 *
 * The whole point is honesty about what the AI did: the change list shows what it
 * reorganized, `unsupported_requirements` shows gaps it refused to paper over, and
 * the invention flags surface any technology it slipped in that is not in the
 * profile — so the user can catch a fabrication the model was told never to make.
 */
export function CVTailorPanel({ jobId, aiConfigured }: CVTailorPanelProps) {
  const toast = useToast();
  const { data, isLoading } = useTailoredResume(jobId);
  const [draft, setDraft] = useState('');

  // Reseed the editor whenever a new server version arrives (generate / save).
  useEffect(() => {
    setDraft(data?.content ?? '');
  }, [data?.content, data?.updated_at]);

  const tailor = useTailorResume(jobId, {
    onSuccess: () => toast.success('Currículo adaptado', 'Revise as mudanças e os alertas abaixo.'),
    onError: (error) => toast.error('Não foi possível adaptar o currículo', errorMessage(error)),
  });
  const save = useUpdateTailoredResume(jobId, {
    onSuccess: () => toast.toast({ title: 'Edições salvas', variant: 'success' }),
    onError: (error) => toast.error('Não foi possível salvar as edições', errorMessage(error)),
  });

  const dirty = data != null && draft !== data.content;
  const generateLabel = data ? 'Gerar novamente' : 'Adaptar meu currículo';
  const busy = tailor.isPending;

  return (
    <Card>
      <CardHeader
        title="Currículo adaptado"
        description="Adapta o seu CV a esta vaga — reorganizado e reenfatizado, nunca inventado."
        actions={
          <Button
            loading={busy}
            disabled={!aiConfigured}
            title={aiConfigured ? 'Adaptar o seu currículo a este anúncio' : 'Nenhuma chave de API de IA configurada'}
            onClick={() => tailor.mutate()}
            icon={
              data ? (
                <RefreshCw aria-hidden className="h-4 w-4" />
              ) : (
                <Wand2 aria-hidden className="h-4 w-4" />
              )
            }
          >
            {generateLabel}
          </Button>
        }
      />

      <div className="card-body space-y-4">
        {/* A present draft always renders — viewing and editing it never calls the
            AI — so the "AI is off" note only shows when there is nothing to show. */}
        {!isLoading && !aiConfigured && !data ? (
          <Note tone="warning">
            Os recursos de IA estão desligados. Configure uma chave de API da Anthropic para adaptar o seu currículo.
          </Note>
        ) : isLoading ? (
          <Skeleton className="h-40 w-full rounded-lg" />
        ) : !data ? (
          <div className="space-y-2 text-sm text-content-muted">
            <p>
              Gere uma versão do seu CV adaptada a este anúncio. Ela reorganiza e reenfatiza o que já
              está no seu perfil — nunca adiciona experiência que você não tem.
            </p>
            <p className="text-xs text-content-subtle">
              Precisa do texto do currículo na sua página de Perfil. Nada é enviado a lugar nenhum.
            </p>
          </div>
        ) : (
          <>
            {data.is_stale ? (
              <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-4 w-4" />}>
                O seu perfil mudou depois que isto foi gerado. Gere novamente para atualizar.
              </Note>
            ) : null}

            {data.invention_flags.length > 0 ? (
              <Note tone="danger" icon={<TriangleAlert aria-hidden className="h-4 w-4" />}>
                <span className="font-medium">Verifique você mesmo.</span> Aparecem no CV adaptado, mas
                não no seu perfil, então podem ter sido inventados:{' '}
                <span className="font-medium">{data.invention_flags.join(', ')}</span>. A ferramenta
                os sinaliza para você; ela não os remove.
              </Note>
            ) : (
              <Note tone="accent" icon={<ShieldCheck aria-hidden className="h-4 w-4" />}>
                Nenhuma tecnologia inventada detectada em relação ao seu perfil.
              </Note>
            )}

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
                <p className="mt-2 text-2xs text-content-subtle">
                  Cada uma é fundamentada no seu currículo, mas agressiva o bastante para uma
                  entrevista fazer você recuar. Edite o texto abaixo para suavizar ou remover.
                </p>
              </div>
            ) : null}

            {data.unsupported_requirements.length > 0 ? (
              <div>
                <SectionLabel>Lacunas que ele não disfarçou</SectionLabel>
                <ul className="mt-2 space-y-1.5">
                  {data.unsupported_requirements.map((requirement) => (
                    <li
                      key={requirement}
                      className="flex items-start gap-2 text-xs leading-relaxed text-content-muted"
                    >
                      <TriangleAlert aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                      <span>{requirement}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {data.changes.length > 0 ? (
              <div>
                <SectionLabel>O que mudou</SectionLabel>
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
              </div>
            ) : null}

            <div>
              <div className="flex items-center justify-between">
                <SectionLabel>CV adaptado — edite antes de usar</SectionLabel>
                {data.was_edited ? (
                  <span className="text-[11px] text-content-subtle">editado por você</span>
                ) : null}
              </div>
              <Textarea
                aria-label="Currículo adaptado"
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
                Salvar edições
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
