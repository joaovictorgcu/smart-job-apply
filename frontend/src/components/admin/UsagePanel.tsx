import { Users } from 'lucide-react';

import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader } from '@/components/primitives';
import { formatNumber, formatRelativeTime } from '@/lib/format';
import type { AdminUsageRow } from '@/types/api';

import { DataList, type DataColumn } from './DataList';

const COLUMNS: DataColumn<AdminUsageRow>[] = [
  {
    key: 'account',
    header: 'Conta',
    primary: true,
    cell: (row) => (
      <span className="block min-w-0">
        <span className="block truncate text-content">{row.full_name || row.email}</span>
        {row.full_name ? (
          <span className="block truncate text-2xs text-content-subtle">{row.email}</span>
        ) : null}
      </span>
    ),
  },
  {
    key: 'jobs',
    header: 'Vagas analisadas',
    align: 'right',
    cell: (row) => formatNumber(row.jobs),
  },
  {
    key: 'applications',
    header: 'Candidaturas',
    align: 'right',
    cell: (row) => formatNumber(row.applications),
  },
  {
    key: 'submitted',
    header: 'Enviadas',
    align: 'right',
    cell: (row) => formatNumber(row.submitted),
  },
  {
    key: 'last',
    header: 'Última atividade',
    align: 'right',
    cell: (row) => formatRelativeTime(row.last_activity_at),
  },
];

export interface UsagePanelProps {
  usage?: AdminUsageRow[];
  isLoading?: boolean;
  className?: string;
}

/**
 * "Uso da plataforma".
 *
 * Ordered by activity so the panel can answer whether anyone is actually using
 * the product. Not a leaderboard: no position is printed, the heading says
 * "uso", and the copy avoids "top" — the accounts here are users, not
 * contestants.
 */
export function UsagePanel({ usage, isLoading = false, className }: UsagePanelProps) {
  return (
    <Card className={className}>
      <CardHeader
        title="Uso da plataforma"
        description="Contas com mais atividade registrada, para entender como o produto é usado."
      />
      <DataList
        columns={COLUMNS}
        rows={usage ?? []}
        rowKey={(row) => row.user_id}
        caption="Contas com mais atividade"
        isLoading={isLoading || !usage}
        empty={
          <EmptyState
            compact
            icon={Users}
            title="Nenhuma conta com candidaturas"
            description="A lista se preenche quando a primeira candidatura for criada."
          />
        }
      />
    </Card>
  );
}
