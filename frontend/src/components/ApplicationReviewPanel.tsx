import { Info, Save, Send, Sparkles, Trash2, TriangleAlert } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  useDiscardApplication,
  useGenerateCoverLetter,
  useSettings,
  useSubmitApplication,
  useUpdateApplication,
} from '@/hooks/useApi';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';
import type { ApplicationDetail, ScreeningAnswer } from '@/types/api';

import { Modal } from './Modal';
import { Button, Card, CardHeader, Note, Textarea } from './primitives';
import { ScreeningAnswerEditor } from './ScreeningAnswerEditor';
import { useToast } from './ToastProvider';

const SOFT_COVER_LETTER_LIMIT = 2000;

interface Draft {
  coverLetter: string;
  answers: ScreeningAnswer[];
}

function draftFrom(application: ApplicationDetail): Draft {
  return {
    coverLetter: application.cover_letter ?? '',
    answers: application.screening_answers,
  };
}

export interface ApplicationReviewPanelProps {
  application: ApplicationDetail;
  className?: string;
}

/**
 * The human-approval surface.
 *
 * "Save changes" and "Approve & submit" are deliberately separate actions, and
 * submitting is gated behind a second confirmation that names the company and
 * role. It stays disabled while any answer is still flagged, while edits are
 * unsaved, and while dry run is on — with the reason spelled out, never a
 * mysteriously grey button.
 */
export function ApplicationReviewPanel({ application, className }: ApplicationReviewPanelProps) {
  const toast = useToast();
  const { data: settings } = useSettings();
  const [draft, setDraft] = useState<Draft>(() => draftFrom(application));
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);

  // Server state wins whenever the application itself changes underneath us.
  useEffect(() => {
    setDraft(draftFrom(application));
  }, [application.id, application.updated_at]);

  const update = useUpdateApplication({
    onSuccess: () => toast.success('Changes saved'),
    onError: (error) => toast.error('Could not save your changes', errorMessage(error)),
  });

  const submit = useSubmitApplication({
    onSuccess: () => {
      setConfirmOpen(false);
      toast.success('Application submitted', 'LinkedIn has received it.');
    },
    onError: (error) => toast.error('Submission failed', errorMessage(error)),
  });

  const discard = useDiscardApplication({
    onSuccess: () => {
      setDiscardOpen(false);
      toast.toast({ title: 'Application discarded', variant: 'info' });
    },
    onError: (error) => toast.error('Could not discard', errorMessage(error)),
  });

  const generate = useGenerateCoverLetter({
    onSuccess: (result) => {
      setDraft((current) => ({ ...current, coverLetter: result.content }));
      toast.success('Cover letter drafted', 'Review it, then save your changes.');
    },
    onError: (error) => toast.error('Could not draft a cover letter', errorMessage(error)),
  });

  const dryRun = settings?.dry_run ?? true;
  const isDirty = useMemo(() => {
    if (draft.coverLetter !== (application.cover_letter ?? '')) return true;
    return JSON.stringify(draft.answers) !== JSON.stringify(application.screening_answers);
  }, [draft, application.cover_letter, application.screening_answers]);

  const pendingReview = draft.answers.filter((answer) => answer.needs_review).length;
  const isReviewable = application.status === 'awaiting_review';
  const isBusy = update.isPending || submit.isPending || discard.isPending;

  const blockers: string[] = [];
  if (!isReviewable) {
    blockers.push(
      `This application is "${application.status.replace(/_/g, ' ')}", not waiting for review, so it cannot be submitted.`,
    );
  }
  if (pendingReview > 0) {
    blockers.push(
      `${pendingReview} ${pendingReview === 1 ? 'answer' : 'answers'} still need your review. Confirm each flagged answer above.`,
    );
  }
  if (isDirty) {
    blockers.push('You have unsaved edits. Save them first so LinkedIn gets what you see here.');
  }
  if (dryRun) {
    blockers.push(
      'Dry run is on, so submitting is blocked on purpose. Turn it off in Settings when you are ready to send applications for real.',
    );
  }

  const canSubmit = blockers.length === 0 && !isBusy;
  const jobTitle = application.job?.title ?? `job #${application.job_id}`;
  const company = application.job?.company ?? 'this company';

  return (
    <div className={cn('space-y-4', className)}>
      <Card>
        <CardHeader
          title="Cover letter"
          description="Edit freely — this exact text is what gets pasted into the form."
          actions={
            <Button
              size="sm"
              loading={generate.isPending}
              disabled={isBusy}
              onClick={() => generate.mutate(application.job_id)}
              icon={<Sparkles aria-hidden className="h-3.5 w-3.5" />}
            >
              Draft with AI
            </Button>
          }
        />
        <div className="card-body space-y-2">
          <label htmlFor="cover-letter" className="sr-only">
            Cover letter
          </label>
          <Textarea
            id="cover-letter"
            rows={10}
            value={draft.coverLetter}
            disabled={isBusy}
            placeholder="No cover letter was generated for this application."
            onChange={(event) =>
              setDraft((current) => ({ ...current, coverLetter: event.target.value }))
            }
          />
          <p
            className={cn(
              'tabular text-2xs',
              draft.coverLetter.length > SOFT_COVER_LETTER_LIMIT
                ? 'text-warning'
                : 'text-content-subtle',
            )}
            aria-live="polite"
          >
            {draft.coverLetter.length.toLocaleString()} characters
            {draft.coverLetter.length > SOFT_COVER_LETTER_LIMIT
              ? ' — long answers are often truncated by LinkedIn'
              : ''}
          </p>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Screening answers"
          description={
            pendingReview > 0
              ? `${pendingReview} of ${draft.answers.length} need your attention.`
              : 'All answers are confirmed.'
          }
        />
        <div className="card-body">
          <ScreeningAnswerEditor
            answers={draft.answers}
            disabled={isBusy}
            onChange={(answers) => setDraft((current) => ({ ...current, answers }))}
          />
        </div>
      </Card>

      <Card>
        <div className="card-body space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="default"
              disabled={!isDirty || isBusy}
              loading={update.isPending}
              onClick={() =>
                update.mutate({
                  id: application.id,
                  payload: {
                    cover_letter: draft.coverLetter,
                    screening_answers: draft.answers,
                  },
                })
              }
              icon={<Save aria-hidden className="h-4 w-4" />}
            >
              Save changes
            </Button>

            <Button
              variant="primary"
              disabled={!canSubmit}
              onClick={() => setConfirmOpen(true)}
              icon={<Send aria-hidden className="h-4 w-4" />}
            >
              Approve &amp; submit
            </Button>

            <Button
              variant="ghost"
              className="ml-auto text-danger hover:bg-danger/10 hover:text-danger"
              disabled={isBusy || application.status === 'discarded'}
              onClick={() => setDiscardOpen(true)}
              icon={<Trash2 aria-hidden className="h-4 w-4" />}
            >
              Discard
            </Button>
          </div>

          {blockers.length > 0 ? (
            <div className="space-y-2">
              <p className="text-2xs font-semibold uppercase tracking-wider text-content-subtle">
                Why &ldquo;Approve &amp; submit&rdquo; is disabled
              </p>
              <ul className="space-y-1.5">
                {blockers.map((blocker) => (
                  <li key={blocker}>
                    <Note tone="neutral" icon={<Info aria-hidden className="h-3.5 w-3.5" />}>
                      {blocker}
                    </Note>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
              Approving will really submit this application to LinkedIn. There is no undo.
            </Note>
          )}
        </div>
      </Card>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        size="md"
        title="Submit this application?"
        description="This is the only action in the app that sends anything to LinkedIn."
        footer={
          <>
            <Button onClick={() => setConfirmOpen(false)} disabled={submit.isPending}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={submit.isPending}
              onClick={() => submit.mutate(application.id)}
            >
              Submit to {company}
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-sm leading-relaxed text-content-muted">
          <div className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
            <p className="text-2xs uppercase tracking-wider text-content-subtle">Applying to</p>
            <p className="mt-1 font-semibold text-content">{jobTitle}</p>
            <p className="text-xs text-content-muted">{company}</p>
          </div>
          <p>
            The saved cover letter and all {draft.answers.length} screening{' '}
            {draft.answers.length === 1 ? 'answer' : 'answers'} will be sent exactly as they appear
            on this page, and the form will be submitted. This cannot be undone.
          </p>
        </div>
      </Modal>

      <Modal
        open={discardOpen}
        onClose={() => setDiscardOpen(false)}
        size="sm"
        title="Discard this application?"
        description="The draft is closed and the job is left un-applied. Nothing is sent."
        footer={
          <>
            <Button onClick={() => setDiscardOpen(false)} disabled={discard.isPending}>
              Keep it
            </Button>
            <Button
              variant="danger"
              loading={discard.isPending}
              onClick={() => discard.mutate(application.id)}
            >
              Discard
            </Button>
          </>
        }
      />
    </div>
  );
}
