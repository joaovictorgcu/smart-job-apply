import { AlertOctagon, Search, Users } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { DataList, type DataColumn } from '@/components/admin/DataList';
import { USER_FILTER_LABELS } from '@/components/admin/labels';
import { useAdminPeriod } from '@/components/admin/period';
import { EmptyState } from '@/components/EmptyState';
import { Pagination } from '@/components/Pagination';
import { Card, CardHeader, Field, Input, PageHeader, Select } from '@/components/primitives';
import { useAdminUsers } from '@/hooks/useApi';
import { badgeClass, formatDate, formatNumber, formatRelativeTime } from '@/lib/format';
import { errorMessage } from '@/services/client';
import { ADMIN_USER_FILTERS, type AdminUserFilter, type AdminUserRow } from '@/types/api';

const PAGE_SIZE = 25;

const COLUMNS: DataColumn<AdminUserRow>[] = [
  {
    key: 'account',
    header: 'Conta',
    primary: true,
    cell: (row) => (
      <span className="block min-w-0">
        <span className="flex items-center gap-2">
          <span className="truncate text-content">{row.full_name || '—'}</span>
          {row.is_admin ? <span className={badgeClass('accent')}>admin</span> : null}
        </span>
        <span className="block truncate text-2xs text-content-subtle">{row.email}</span>
      </span>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    cell: (row) => (
      <span className={badgeClass(row.is_active ? 'success' : 'neutral')}>
        {row.is_active ? 'Ativo' : 'Inativo'}
      </span>
    ),
  },
  {
    key: 'created',
    header: 'Cadastro',
    cell: (row) => formatDate(row.created_at),
  },
  {
    key: 'last_login',
    header: 'Último acesso',
    cell: (row) =>
      row.last_login_at ? formatRelativeTime(row.last_login_at) : 'Nunca entrou',
  },
  { key: 'jobs', header: 'Vagas', align: 'right', cell: (row) => formatNumber(row.jobs) },
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
];

/**
 * Accounts, with the counters that say how much each one uses the product.
 *
 * Contact details and totals only — no profile, no resume, no session. The
 * backend has no field for those in this payload, so this screen could not show
 * them even if it tried.
 */
export function AdminUsers() {
  const { query: period } = useAdminPeriod();
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [filter, setFilter] = useState<AdminUserFilter>('all');
  const [offset, setOffset] = useState(0);

  // Typing must not fire a request per keystroke; 300ms is the usual pause.
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Any change to the query invalidates the page the user was on.
  useEffect(() => {
    setOffset(0);
  }, [debounced, filter, period.period, period.start, period.end]);

  const query = useMemo(
    () => ({ ...period, search: debounced || undefined, filter, limit: PAGE_SIZE, offset }),
    [period, debounced, filter, offset],
  );
  const { data, isLoading, isError, error } = useAdminUsers(query);

  const rows = data?.items ?? [];
  const filtering = Boolean(debounced) || filter !== 'all';

  return (
    <div className="space-y-5">
      <PageHeader
        title="Usuários"
        description="Contas da plataforma, com as contagens de vagas e candidaturas de cada uma."
      />

      <Card>
        <CardHeader
          title="Contas"
          description={
            data
              ? `${formatNumber(data.total)} ${data.total === 1 ? 'conta' : 'contas'} com os filtros atuais.`
              : undefined
          }
        />

        <div className="grid gap-3 border-b border-line px-4 py-3.5 sm:grid-cols-[1fr,14rem]">
          <Field label="Buscar" htmlFor="admin-user-search" hint="Nome ou e-mail.">
            <div className="relative">
              <Search
                aria-hidden
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-content-subtle"
              />
              <Input
                id="admin-user-search"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="ana@exemplo.com"
                className="pl-9"
              />
            </div>
          </Field>

          <Field label="Filtro" htmlFor="admin-user-filter">
            <Select
              id="admin-user-filter"
              value={filter}
              onChange={(event) => setFilter(event.target.value as AdminUserFilter)}
            >
              {ADMIN_USER_FILTERS.map((option) => (
                <option key={option} value={option}>
                  {USER_FILTER_LABELS[option]}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        {isError ? (
          <EmptyState
            icon={AlertOctagon}
            title="Não foi possível carregar as contas"
            description={errorMessage(error, 'A API não respondeu.')}
          />
        ) : (
          <DataList
            columns={COLUMNS}
            rows={rows}
            rowKey={(row) => row.id}
            caption="Contas da plataforma"
            isLoading={isLoading}
            empty={
              <EmptyState
                compact
                icon={Users}
                title={filtering ? 'Nenhuma conta com esses filtros' : 'Nenhuma conta cadastrada'}
                description={
                  filtering
                    ? 'Ajuste a busca ou escolha outro filtro.'
                    : 'A primeira conta aparece aqui assim que for criada.'
                }
              />
            }
          />
        )}

        {data && data.total > PAGE_SIZE ? (
          <div className="border-t border-line px-4 py-3">
            <Pagination
              total={data.total}
              limit={PAGE_SIZE}
              offset={offset}
              onOffsetChange={setOffset}
              unit="contas"
            />
          </div>
        ) : null}
      </Card>
    </div>
  );
}
