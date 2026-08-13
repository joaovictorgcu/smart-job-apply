import { Briefcase } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';
import type { Job } from '@/types/api';

import { EmptyState } from './EmptyState';
import { JobCard } from './JobCard';
import { Card, Skeleton } from './primitives';

function JobCardSkeleton() {
  return (
    <Card className="flex gap-4 px-5 py-3.5">
      <Skeleton className="h-10 w-10 shrink-0 rounded-xl" />
      <div className="flex-1 space-y-2.5">
        <Skeleton className="h-4 w-2/5" />
        <Skeleton className="h-3 w-3/5" />
        <div className="flex gap-1.5">
          <Skeleton className="h-5 w-20 rounded-full" />
          <Skeleton className="h-5 w-24 rounded-full" />
        </div>
      </div>
    </Card>
  );
}

export interface JobListProps {
  jobs: Job[];
  isLoading?: boolean;
  selectable?: boolean;
  selectedIds?: number[];
  onToggleSelect?: (id: number) => void;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  className?: string;
}

export function JobList({
  jobs,
  isLoading = false,
  selectable = false,
  selectedIds = [],
  onToggleSelect,
  emptyTitle = 'Nenhuma vaga corresponde a esses filtros',
  emptyDescription = 'Afrouxe os filtros, ou rode uma busca salva para trazer anúncios novos.',
  emptyAction,
  className,
}: JobListProps) {
  if (isLoading) {
    return (
      <div className={cn('space-y-2.5', className)} aria-busy="true">
        <JobCardSkeleton />
        <JobCardSkeleton />
        <JobCardSkeleton />
        <JobCardSkeleton />
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <Card className={className}>
        <EmptyState
          icon={Briefcase}
          title={emptyTitle}
          description={emptyDescription}
          action={emptyAction}
        />
      </Card>
    );
  }

  const selected = new Set(selectedIds);

  return (
    <ul className={cn('space-y-2.5', className)}>
      {jobs.map((job, index) => (
        <li
          key={job.id}
          className="animate-fade-in"
          style={{ animationDelay: `${Math.min(index, 10) * 35}ms` }}
        >
          <JobCard
            job={job}
            selectable={selectable}
            selected={selected.has(job.id)}
            onToggleSelect={onToggleSelect}
          />
        </li>
      ))}
    </ul>
  );
}
