/**
 * Portuguese wording for the admin panel's keys.
 *
 * The API returns `key` strings and lets the client name them, the same way
 * `lib/format.ts` names the job and application enums. Keeping the copy here
 * means adding an indicator is a service change plus one line of label, and the
 * backend never has to grow a translation table.
 */

import {
  Activity,
  AlertTriangle,
  Bot,
  Brain,
  Briefcase,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Database,
  Gauge,
  Globe,
  Layers,
  ListChecks,
  MessageSquare,
  Percent,
  Send,
  Server,
  TriangleAlert,
  Users,
  XCircle,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type {
  AdminPeriod,
  AdminUserFilter,
  AlertSeverity,
  HealthStatus,
  MetricUnit,
  ServiceState,
} from '@/types/api';

export interface MetricCopy {
  label: string;
  /** One objective line under the number. Never a sales pitch. */
  hint: string;
  icon: LucideIcon;
  /** Where the tile links, when a screen can answer "why". */
  to?: string;
  /** True when a rising value is bad — the arrow keeps its direction, the colour flips. */
  inverse?: boolean;
}

const METRICS: Record<string, MetricCopy> = {
  users: {
    label: 'Usuários',
    hint: 'Contas cadastradas até o fim do período.',
    icon: Users,
    to: '/admin/users',
  },
  jobs_found: {
    label: 'Vagas encontradas',
    hint: 'Vagas descobertas pelas buscas no período.',
    icon: Briefcase,
    to: '/admin/jobs',
  },
  applications: {
    label: 'Candidaturas',
    hint: 'Candidaturas criadas no período, enviadas ou não.',
    icon: Send,
  },
  success_rate: {
    label: 'Taxa de sucesso',
    hint: 'Enviadas ÷ tentativas (enviadas + com erro).',
    icon: Percent,
  },
  applications_submitted: {
    label: 'Enviadas',
    hint: 'Aprovadas por uma pessoa e enviadas de fato.',
    icon: CheckCircle2,
  },
  awaiting_review: {
    label: 'Aguardando revisão',
    hint: 'Fila atual, não do período: preenchidas e paradas.',
    icon: ClipboardCheck,
  },
  applications_failed: {
    label: 'Com erro',
    hint: 'Candidaturas que terminaram em falha no período.',
    icon: XCircle,
    inverse: true,
  },
  interviews: {
    label: 'Entrevistas',
    hint: 'Desfechos marcados como entrevista ou proposta.',
    icon: MessageSquare,
  },
  active_runs: {
    label: 'Automação ativa',
    hint: 'Execuções em andamento neste momento.',
    icon: Bot,
  },
  active_users: {
    label: 'Usuários ativos',
    hint: 'Contas que entraram durante o período.',
    icon: Activity,
    to: '/admin/users',
  },
  approval_rate: {
    label: 'Taxa de aprovação',
    hint: 'Candidaturas aprovadas por uma pessoa ÷ criadas.',
    icon: ListChecks,
  },
  submit_rate: {
    label: 'Taxa de envio',
    hint: 'Candidaturas enviadas ÷ criadas.',
    icon: Send,
  },
  manual_review_rate: {
    label: 'Revisadas à mão',
    hint: 'Rascunhos que alguém editou antes de aprovar.',
    icon: ClipboardCheck,
  },
  time_to_apply: {
    label: 'Da vaga ao envio',
    hint: 'Tempo médio entre encontrar a vaga e enviar.',
    icon: CalendarClock,
  },
  applications_per_user: {
    label: 'Candidaturas por conta',
    hint: 'Média entre as contas com atividade no período.',
    icon: Layers,
  },
  jobs_per_user: {
    label: 'Vagas por conta',
    hint: 'Média entre as contas com atividade no período.',
    icon: Gauge,
  },
};

const FALLBACK: MetricCopy = {
  label: 'Indicador',
  hint: '',
  icon: Gauge,
};

export function metricCopy(key: string): MetricCopy {
  return METRICS[key] ?? { ...FALLBACK, label: key };
}

export const PERIOD_LABELS: Record<AdminPeriod, string> = {
  today: 'Hoje',
  '7d': '7 dias',
  '30d': '30 dias',
  '90d': '90 dias',
  custom: 'Personalizado',
};

export const USER_FILTER_LABELS: Record<AdminUserFilter, string> = {
  all: 'Todos',
  active: 'Ativos',
  inactive: 'Inativos',
  new: 'Novos no período',
  with_applications: 'Com candidaturas',
  without_applications: 'Sem candidaturas',
};

export const FUNNEL_LABELS: Record<string, string> = {
  jobs_found: 'Vagas encontradas',
  jobs_selected: 'Vagas selecionadas',
  applications_prepared: 'Candidaturas preparadas',
  applications_approved: 'Candidaturas aprovadas',
  applications_submitted: 'Candidaturas enviadas',
  interviews: 'Entrevistas',
};

export const HEALTH_LABELS: Record<HealthStatus, string> = {
  healthy: 'Saudável',
  attention: 'Atenção',
  problem: 'Problema',
};

export const HEALTH_TONE: Record<HealthStatus, 'success' | 'warning' | 'danger'> = {
  healthy: 'success',
  attention: 'warning',
  problem: 'danger',
};

export const SERVICE_LABELS: Record<string, string> = {
  api: 'API',
  database: 'Banco',
  ai: 'IA',
  automation: 'Automação',
  queue: 'Fila',
  frontend: 'Frontend',
};

export const SERVICE_ICONS: Record<string, LucideIcon> = {
  api: Server,
  database: Database,
  ai: Brain,
  automation: Bot,
  queue: Layers,
  frontend: Globe,
};

export const SERVICE_STATE_LABELS: Record<ServiceState, string> = {
  online: 'Online',
  attention: 'Atenção',
  offline: 'Offline',
};

export const SERVICE_STATE_TONE: Record<ServiceState, 'success' | 'warning' | 'danger'> = {
  online: 'success',
  attention: 'warning',
  offline: 'danger',
};

export const SEVERITY_LABELS: Record<AlertSeverity, string> = {
  info: 'Informativo',
  warning: 'Atenção',
  critical: 'Crítico',
};

export const SEVERITY_TONE: Record<AlertSeverity, 'info' | 'warning' | 'danger'> = {
  info: 'info',
  warning: 'warning',
  critical: 'danger',
};

export const SEVERITY_ICON: Record<AlertSeverity, LucideIcon> = {
  info: AlertTriangle,
  warning: TriangleAlert,
  critical: TriangleAlert,
};

export const ERROR_SOURCE_LABELS: Record<string, string> = {
  automation: 'Automação',
  ai: 'IA',
  application: 'Candidatura',
};

export const GROWTH_SERIES: Array<{ key: 'users' | 'jobs' | 'applications'; label: string }> = [
  { key: 'users', label: 'Usuários' },
  { key: 'jobs', label: 'Vagas' },
  { key: 'applications', label: 'Candidaturas' },
];

/** Units the metric tiles know how to print. Kept beside the labels they serve. */
export const UNIT_SUFFIX: Partial<Record<MetricUnit, string>> = {
  usd: 'USD',
};
