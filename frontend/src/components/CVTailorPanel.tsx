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
    onSuccess: () => toast.success('Resume tailored', 'Review the changes and flags below.'),
    onError: (error) => toast.error('Could not tailor the resume', errorMessage(error)),
  });
  const save = useUpdateTailoredResume(jobId, {
    onSuccess: () => toast.toast({ title: 'Edits saved', variant: 'success' }),
    onError: (error) => toast.error('Could not save edits', errorMessage(error)),
  });

  const dirty = data != null && draft !== data.content;
  const generateLabel = data ? 'Regenerate' : 'Tailor my resume';
  const busy = tailor.isPending;

  return (
    <Card>
      <CardHeader
        title="Tailored resume"
        description="Adapts your CV to this job — reorganized and re-emphasized, never invented."
        actions={
          <Button
            loading={busy}
            disabled={!aiConfigured}
            title={aiConfigured ? 'Adapt your resume to this posting' : 'No AI API key is configured'}
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
            AI features are off. Set an Anthropic API key to tailor your resume.
          </Note>
        ) : isLoading ? (
          <Skeleton className="h-40 w-full rounded-lg" />
        ) : !data ? (
          <div className="space-y-2 text-sm text-content-muted">
            <p>
              Generate a version of your CV adapted to this posting. It reorganizes and
              re-emphasizes what is already in your profile — it never adds experience you
              do not have.
            </p>
            <p className="text-xs text-content-subtle">
              Needs the résumé text on your Profile page. Nothing is submitted anywhere.
            </p>
          </div>
        ) : (
          <>
            {data.is_stale ? (
              <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-4 w-4" />}>
                Your profile changed after this was generated. Regenerate to refresh it.
              </Note>
            ) : null}

            {data.invention_flags.length > 0 ? (
              <Note tone="danger" icon={<TriangleAlert aria-hidden className="h-4 w-4" />}>
                <span className="font-medium">Verify these yourself.</span> They appear in the
                tailored CV but not in your profile, so they may be invented:{' '}
                <span className="font-medium">{data.invention_flags.join(', ')}</span>. The tool
                flags them for you; it does not remove them.
              </Note>
            ) : (
              <Note tone="accent" icon={<ShieldCheck aria-hidden className="h-4 w-4" />}>
                No invented technologies detected against your profile.
              </Note>
            )}

            {data.unsupported_requirements.length > 0 ? (
              <div>
                <SectionLabel>Gaps it did not paper over</SectionLabel>
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
                <SectionLabel>What changed</SectionLabel>
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
                <SectionLabel>Tailored CV — edit before you use it</SectionLabel>
                {data.was_edited ? (
                  <span className="text-[11px] text-content-subtle">edited by you</span>
                ) : null}
              </div>
              <Textarea
                aria-label="Tailored resume"
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
                Save edits
              </Button>
              {dirty ? (
                <Button onClick={() => setDraft(data.content)}>Discard edits</Button>
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
