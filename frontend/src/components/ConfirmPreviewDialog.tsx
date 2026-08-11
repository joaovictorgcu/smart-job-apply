import { CircleSlash, FlaskConical, ShieldCheck, TriangleAlert } from 'lucide-react';
import { useEffect, useState } from 'react';

import { formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { PreviewResponse } from '@/types/api';

import { Modal } from './Modal';
import { Button, Checkbox, Note, Skeleton } from './primitives';

function Metric({
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'neutral' | 'accent' | 'warning';
}) {
  return (
    <div
      className={cn(
        'rounded-lg border px-3 py-2.5',
        tone === 'accent'
          ? 'border-accent-500/40 bg-accent-500/[0.07]'
          : tone === 'warning'
            ? 'border-warning/40 bg-warning/[0.07]'
            : 'border-line bg-surface-sunken',
      )}
    >
      <p className="text-2xs uppercase tracking-wider text-content-subtle">{label}</p>
      <p
        className={cn(
          'tabular mt-1 text-xl font-semibold leading-none',
          tone === 'accent' ? 'text-accent-400' : tone === 'warning' ? 'text-warning' : 'text-content',
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-2xs leading-snug text-content-subtle">{hint}</p> : null}
    </div>
  );
}

export interface ConfirmPreviewDialogProps {
  open: boolean;
  onClose: () => void;
  preview: PreviewResponse | null;
  isLoading?: boolean;
  isSubmitting?: boolean;
  error?: string | null;
  onConfirm: () => void;
}

/**
 * The safety gate in front of form filling.
 *
 * Nothing here can submit an application — preparing always stops at the review
 * step. The dialog exists so the operator sees the exact volume, the quota and
 * every warning *before* a browser starts clicking, and has to tick an
 * acknowledgement rather than muscle-memory a primary button.
 */
export function ConfirmPreviewDialog({
  open,
  onClose,
  preview,
  isLoading = false,
  isSubmitting = false,
  error,
  onConfirm,
}: ConfirmPreviewDialogProps) {
  const [acknowledged, setAcknowledged] = useState(false);

  // Consent is per-dialog: never carry a tick over to the next batch.
  useEffect(() => {
    if (!open) setAcknowledged(false);
  }, [open]);

  const count = preview?.jobs_to_process ?? 0;
  const overQuota = preview !== null && count > preview.remaining_today;
  const canConfirm = Boolean(preview) && count > 0 && acknowledged && !isSubmitting;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title="Review before anything is filled in"
      description="This step opens each posting and fills the Easy Apply form. Submitting is a separate action you take per application."
      footer={
        <>
          <Button onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!canConfirm} loading={isSubmitting} onClick={onConfirm}>
            {count > 0
              ? `Fill ${count} ${count === 1 ? 'application' : 'applications'} for review — nothing will be submitted`
              : 'Nothing to fill'}
          </Button>
        </>
      }
    >
      {isLoading || !preview ? (
        <div className="space-y-3">
          <Skeleton className="h-16 w-full" />
          <div className="grid gap-3 sm:grid-cols-3">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
          <Skeleton className="h-12 w-full" />
        </div>
      ) : (
        <div className="space-y-4">
          {error ? (
            <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2.5 text-xs leading-relaxed text-danger-strong">
              {error}
            </div>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              label="Will be filled"
              value={formatNumber(count)}
              hint="Forms filled, then paused for review"
              tone="accent"
            />
            <Metric
              label="Already applied"
              value={formatNumber(preview.already_applied)}
              hint="Skipped — no duplicates"
            />
            <Metric
              label="Below threshold"
              value={formatNumber(preview.below_threshold)}
              hint="Under your minimum score"
            />
            <Metric
              label="Quota left today"
              value={`${formatNumber(preview.remaining_today)} / ${formatNumber(preview.daily_cap)}`}
              hint={overQuota ? 'Fewer than requested will be sendable' : 'Submissions remaining'}
              tone={overQuota ? 'warning' : 'neutral'}
            />
          </div>

          <div
            className={cn(
              'flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5',
              preview.dry_run
                ? 'border-success/40 bg-success/[0.07]'
                : 'border-warning/40 bg-warning/[0.07]',
            )}
          >
            {preview.dry_run ? (
              <FlaskConical aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-success" />
            ) : (
              <TriangleAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            )}
            <div className="min-w-0 text-xs leading-relaxed">
              <p
                className={cn(
                  'font-semibold',
                  preview.dry_run ? 'text-success' : 'text-warning-strong',
                )}
              >
                {preview.dry_run ? 'Dry run is ON' : 'Dry run is OFF'}
              </p>
              <p className="text-content-muted">
                {preview.dry_run
                  ? 'Even after you approve an application, the submit button will not be clicked. Turn dry run off in Settings when you are ready to send for real.'
                  : 'Applications you explicitly approve will be really submitted to LinkedIn. This batch still only fills forms.'}
              </p>
            </div>
          </div>

          {overQuota ? (
            <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
              You picked {formatNumber(count)} jobs but only{' '}
              {formatNumber(preview.remaining_today)} submissions are left under today&apos;s cap of{' '}
              {formatNumber(preview.daily_cap)}. The extra drafts will wait for tomorrow.
            </Note>
          ) : null}

          {preview.warnings.length > 0 ? (
            <ul className="space-y-2">
              {preview.warnings.map((warning) => (
                <li key={warning}>
                  <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
                    {warning}
                  </Note>
                </li>
              ))}
            </ul>
          ) : null}

          {count === 0 ? (
            <Note tone="neutral" icon={<CircleSlash aria-hidden className="h-3.5 w-3.5" />}>
              Nothing in this selection is eligible. Everything you picked is already applied to, is
              below your minimum score, or is not an Easy Apply posting.
            </Note>
          ) : (
            <>
              <div className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
                <p className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-content-subtle">
                  <ShieldCheck aria-hidden className="h-3.5 w-3.5" />
                  What happens next
                </p>
                <ol className="mt-2 list-decimal space-y-1 pl-4 text-xs leading-relaxed text-content-muted">
                  <li>Each posting is opened in the browser window you signed in to.</li>
                  <li>The Easy Apply form is filled from your profile and answer bank.</li>
                  <li>
                    The run stops at the review step and the application appears under{' '}
                    <span className="font-medium text-content">Awaiting review</span>.
                  </li>
                  <li>You open each one, edit it, and approve it individually — or discard it.</li>
                </ol>
              </div>

              <Checkbox
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
                label={`I understand this will open and fill ${count} LinkedIn ${
                  count === 1 ? 'application' : 'applications'
                } and stop for my review.`}
                description="Automating LinkedIn violates its Terms of Service and is done at your own risk."
              />
            </>
          )}
        </div>
      )}
    </Modal>
  );
}
