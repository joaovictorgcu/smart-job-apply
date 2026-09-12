import { AlertOctagon } from 'lucide-react';
import { Link } from 'react-router-dom';

import { ActivityTimeline } from '@/components/admin/ActivityTimeline';
import { AIPanel } from '@/components/admin/AIPanel';
import { AlertsPanel } from '@/components/admin/AlertsPanel';
import { AutomationPanel } from '@/components/admin/AutomationPanel';
import { ErrorsPanel } from '@/components/admin/ErrorsPanel';
import { FunnelPanel } from '@/components/admin/FunnelPanel';
import { GrowthChart } from '@/components/admin/GrowthChart';
import { HealthStrip } from '@/components/admin/HealthStrip';
import { MetricGrid } from '@/components/admin/MetricCard';
import { useAdminPeriod } from '@/components/admin/period';
import { UsagePanel } from '@/components/admin/UsagePanel';
import { EmptyState } from '@/components/EmptyState';
import { Card, CardHeader, PageHeader, SectionLabel } from '@/components/primitives';
import { useAdminOverview } from '@/hooks/useApi';
import { formatDate, formatDateTime } from '@/lib/format';
import { errorMessage } from '@/services/client';

import { PERIOD_LABELS } from '@/components/admin/labels';

/** The period, spelled out, so "vs. período anterior" is a checkable claim. */
function PeriodCaption({
  start,
  end,
  label,
}: {
  start: string;
  end: string;
  label: string;
}) {
  return (
    <span className="text-xs text-content-subtle">
      {label} · {formatDate(start)} a {formatDate(end)}
    </span>
  );
}

export function AdminDashboard() {
  const { query, period } = useAdminPeriod();
  const { data, isLoading, isError, error, refetch } = useAdminOverview(query);

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Admin Dashboard" description="Visão geral da plataforma" />
        <Card>
          <EmptyState
            icon={AlertOctagon}
            title="Não foi possível carregar os indicadores"
            description={errorMessage(error, 'A API não respondeu.')}
            action={
              <button type="button" className="btn btn-primary" onClick={() => void refetch()}>
                Tentar novamente
              </button>
            }
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Admin Dashboard"
        description="Visão geral da plataforma"
        actions={
          data ? (
            <div className="text-right">
              <PeriodCaption
                start={data.period.start}
                end={data.period.end}
                label={PERIOD_LABELS[data.period.period]}
              />
              <p className="text-2xs text-content-subtle">
                Dados de {formatDateTime(data.generated_at)}
              </p>
            </div>
          ) : null
        }
      />

      {/* Anything that needs attention comes before the numbers that explain it. */}
      <AlertsPanel alerts={data?.alerts} isLoading={isLoading} />

      <section aria-labelledby="admin-headline" className="space-y-2.5">
        <SectionLabel id="admin-headline">Indicadores principais</SectionLabel>
        <MetricGrid metrics={data?.headline ?? []} isLoading={isLoading} columns={4} />
      </section>

      <section aria-labelledby="admin-operational" className="space-y-2.5">
        <SectionLabel id="admin-operational">Operação</SectionLabel>
        <MetricGrid
          metrics={data?.operational ?? []}
          isLoading={isLoading}
          columns={6}
          dense
        />
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <GrowthChart growth={data?.growth} isLoading={isLoading} className="xl:col-span-2" />
        <FunnelPanel funnel={data?.funnel} isLoading={isLoading} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <AutomationPanel automation={data?.automation} isLoading={isLoading} />
        <AIPanel ai={data?.ai} isLoading={isLoading} />
      </div>

      <HealthStrip health={data?.health} isLoading={isLoading} />

      <div className="grid gap-4 xl:grid-cols-2">
        <ErrorsPanel
          errors={data?.errors}
          isLoading={isLoading}
          action={
            <Link to="/admin/logs" className="btn btn-sm">
              Ver todos
            </Link>
          }
        />
        <ActivityTimeline
          activity={data?.activity}
          isLoading={isLoading}
          action={
            <Link to="/admin/logs" className="btn btn-sm">
              Ver tudo
            </Link>
          }
        />
      </div>

      <UsagePanel usage={data?.usage} isLoading={isLoading} />

      <section aria-labelledby="admin-product" className="space-y-2.5">
        <SectionLabel id="admin-product">Métricas de produto</SectionLabel>
        <MetricGrid metrics={data?.product ?? []} isLoading={isLoading} columns={6} dense />
      </section>

      <Card>
        <CardHeader
          title="Como ler estes números"
          description={
            period === 'today'
              ? 'Hoje é comparado com o mesmo intervalo de horas de ontem — antes do meio-dia, qualquer outra comparação enganaria.'
              : 'A comparação é sempre com uma janela de igual duração imediatamente anterior, não com o mês ou a semana do calendário.'
          }
        />
        <div className="card-body space-y-1.5 text-xs leading-relaxed text-content-muted">
          <p>
            Fluxos (vagas encontradas, candidaturas) contam o que aconteceu no período. Estoques
            (usuários cadastrados, fila de revisão) valem para o momento — o texto de cada card diz
            qual é qual.
          </p>
          <p>
            Taxas variam em pontos percentuais; contagens variam em percentual relativo. Um
            indicador sem base de comparação mostra o valor anterior em vez de uma variação
            impossível.
          </p>
          <p>
            Nada aqui é estimado ou preenchido com dados de exemplo: todo número vem de uma
            consulta ao banco, e o que ainda não existe aparece como “sem dados”.
          </p>
        </div>
      </Card>
    </div>
  );
}
