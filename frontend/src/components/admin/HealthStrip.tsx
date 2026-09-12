import { Card, CardHeader, Skeleton } from '@/components/primitives';
import { badgeClass } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { HealthStatus, SystemHealth } from '@/types/api';

import {
  HEALTH_LABELS,
  HEALTH_TONE,
  SERVICE_ICONS,
  SERVICE_LABELS,
  SERVICE_STATE_LABELS,
  SERVICE_STATE_TONE,
} from './labels';

/**
 * The one badge every health verdict on the panel uses.
 *
 * Colour alone never carries the state: the word is always there too, which is
 * what makes the panel readable to someone who cannot tell the green from the
 * amber.
 */
export function HealthPill({
  status,
  className,
}: {
  status: HealthStatus;
  className?: string;
}) {
  return (
    <span className={cn(badgeClass(HEALTH_TONE[status]), className)}>
      <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
      {HEALTH_LABELS[status]}
    </span>
  );
}

export interface HealthStripProps {
  health?: SystemHealth;
  isLoading?: boolean;
  className?: string;
}

export function HealthStrip({ health, isLoading = false, className }: HealthStripProps) {
  if (isLoading || !health) {
    return (
      <Card className={cn('px-4 py-3.5', className)} aria-busy="true">
        <Skeleton className="h-4 w-32" />
        <div className="mt-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-12" />
          ))}
        </div>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader
        title="Status do sistema"
        description={`Versão ${health.version} · ambiente ${health.environment}.`}
        actions={<HealthPill status={health.status} />}
      />
      <ul className="grid gap-2 px-4 py-3.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {health.services.map((service) => {
          const Icon = SERVICE_ICONS[service.service];
          const tone = SERVICE_STATE_TONE[service.status];
          return (
            <li
              key={service.service}
              className="rounded-lg border border-line bg-surface-sunken px-3 py-2.5"
            >
              <p className="flex items-center gap-1.5 text-xs font-medium text-content">
                {Icon ? <Icon aria-hidden className="h-3.5 w-3.5 shrink-0" /> : null}
                {SERVICE_LABELS[service.service] ?? service.service}
              </p>
              <p className={cn('mt-1.5', badgeClass(tone))}>
                <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
                {SERVICE_STATE_LABELS[service.status]}
              </p>
              <p className="mt-1.5 text-2xs leading-snug text-content-subtle">{service.detail}</p>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
