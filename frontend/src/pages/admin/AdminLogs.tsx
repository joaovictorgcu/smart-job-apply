import { AlertOctagon } from 'lucide-react';

import { ActivityTimeline } from '@/components/admin/ActivityTimeline';
import { ErrorsPanel } from '@/components/admin/ErrorsPanel';
import { useAdminPeriod } from '@/components/admin/period';
import { EmptyState } from '@/components/EmptyState';
import { Card, Note, PageHeader } from '@/components/primitives';
import { useAdminActivity, useAdminErrors } from '@/hooks/useApi';
import { errorMessage } from '@/services/client';

const ERROR_LIMIT = 50;
const ACTIVITY_LIMIT = 40;

/**
 * Errors and activity in full, for the period.
 *
 * The existing logging stays where it is — this reads the same rows the
 * application already writes (`automation_runs`, `ai_analyses`,
 * `application_events`) rather than adding a second log. Which is also why there
 * are no stack traces here to hide: they are never persisted in the first place.
 */
export function AdminLogs() {
  const { query } = useAdminPeriod();
  const errors = useAdminErrors({ ...query, limit: ERROR_LIMIT });
  const activity = useAdminActivity({ ...query, limit: ACTIVITY_LIMIT });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Logs"
        description="Erros e atividade registrados no período selecionado."
      />

      <Note tone="neutral">
        Esta tela lê os mesmos registros que a aplicação já grava — execuções da automação,
        chamadas de IA e o histórico de cada candidatura. Mensagens técnicas completas continuam
        apenas nos logs do servidor: nenhum stack trace é guardado no banco, e portanto nenhum
        aparece aqui.
      </Note>

      {errors.isError ? (
        <Card>
          <EmptyState
            icon={AlertOctagon}
            title="Não foi possível carregar os erros"
            description={errorMessage(errors.error, 'A API não respondeu.')}
          />
        </Card>
      ) : (
        <ErrorsPanel errors={errors.data} isLoading={errors.isLoading} />
      )}

      {activity.isError ? (
        <Card>
          <EmptyState
            icon={AlertOctagon}
            title="Não foi possível carregar a atividade"
            description={errorMessage(activity.error, 'A API não respondeu.')}
          />
        </Card>
      ) : (
        <ActivityTimeline activity={activity.data} isLoading={activity.isLoading} />
      )}
    </div>
  );
}
