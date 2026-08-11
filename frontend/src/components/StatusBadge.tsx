import {
  applicationStatusLabel,
  applicationStatusTone,
  badgeClass,
  jobStatusLabel,
  jobStatusTone,
  runStatusLabel,
  runStatusTone,
  type ToneName,
} from '@/lib/format';
import { cn } from '@/lib/utils';
import type { ApplicationStatus, AutomationRunStatus, JobStatus } from '@/types/api';

/** Statuses that mean work is happening right now and deserve a live dot. */
const IN_FLIGHT = new Set<string>(['preparing', 'submitting', 'running']);

export type StatusBadgeProps = { className?: string } & (
  | { kind: 'job'; status: JobStatus }
  | { kind: 'application'; status: ApplicationStatus }
  | { kind: 'run'; status: AutomationRunStatus }
);

function resolve(props: StatusBadgeProps): { label: string; tone: ToneName } {
  switch (props.kind) {
    case 'job':
      return { label: jobStatusLabel(props.status), tone: jobStatusTone(props.status) };
    case 'application':
      return {
        label: applicationStatusLabel(props.status),
        tone: applicationStatusTone(props.status),
      };
    case 'run':
      return { label: runStatusLabel(props.status), tone: runStatusTone(props.status) };
  }
}

export function StatusBadge(props: StatusBadgeProps) {
  const { label, tone } = resolve(props);

  return (
    <span className={cn(badgeClass(tone), props.className)}>
      {IN_FLIGHT.has(props.status) ? (
        <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-current animate-pulse-soft" />
      ) : null}
      {label}
    </span>
  );
}
