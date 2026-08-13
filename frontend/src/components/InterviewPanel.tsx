import { BookOpenCheck, Check, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Modal } from '@/components/Modal';
import { Button, Card, CardHeader, Select } from '@/components/primitives';
import { useToast } from '@/components/ToastProvider';
import { formatDate } from '@/lib/format';
import {
  addStage,
  completeStage,
  deleteStage,
  fetchInterviewPrep,
  listStages,
} from '@/services/applications';
import { errorMessage } from '@/services/client';
import type { InterviewPrep, InterviewStage, StageType } from '@/types/api';

const STAGE_LABELS: Record<StageType, string> = {
  phone_screen: 'Triagem por telefone',
  technical: 'Entrevista técnica',
  case_study: 'Estudo de caso',
  final_round: 'Rodada final',
  offer_discussion: 'Conversa de proposta',
};

const STAGE_OPTIONS = Object.keys(STAGE_LABELS) as StageType[];

const stagesKey = (applicationId: number) => ['applications', 'stages', applicationId] as const;

export interface InterviewPanelProps {
  applicationId: number;
  /** Stages and prep only exist for a submitted application. */
  enabled: boolean;
  className?: string;
}

/**
 * The interview process of one application: granular stages under the board's
 * single Interview column, plus the AI prep pack grounded in what was actually
 * submitted.
 */
export function InterviewPanel({ applicationId, enabled, className }: InterviewPanelProps) {
  const toast = useToast();
  const client = useQueryClient();
  const [stageType, setStageType] = useState<StageType>('phone_screen');
  const [prepOpen, setPrepOpen] = useState(false);

  const { data: stages } = useQuery<InterviewStage[]>({
    queryKey: stagesKey(applicationId),
    queryFn: ({ signal }) => listStages(applicationId, signal),
    enabled,
  });

  const invalidate = () => void client.invalidateQueries({ queryKey: stagesKey(applicationId) });

  const add = useMutation({
    mutationFn: () => addStage(applicationId, { stage_type: stageType }),
    onSuccess: invalidate,
    onError: (error) => toast.error('Não foi possível registrar a etapa', errorMessage(error)),
  });

  const complete = useMutation({
    mutationFn: (stageId: number) => completeStage(applicationId, stageId),
    onSuccess: invalidate,
    onError: (error) => toast.error('Não foi possível concluir a etapa', errorMessage(error)),
  });

  const remove = useMutation({
    mutationFn: (stageId: number) => deleteStage(applicationId, stageId),
    onSuccess: invalidate,
    onError: (error) => toast.error('Não foi possível remover a etapa', errorMessage(error)),
  });

  const prep = useMutation<InterviewPrep, Error, void>({
    mutationFn: () => fetchInterviewPrep(applicationId),
    onSuccess: () => setPrepOpen(true),
    onError: (error) => toast.error('Não foi possível preparar', errorMessage(error)),
  });

  if (!enabled) return null;

  return (
    <Card className={className}>
      <CardHeader
        title="Entrevistas"
        description="As etapas do processo e o preparo grounded no que foi enviado."
        actions={
          <Button
            size="sm"
            loading={prep.isPending}
            onClick={() => prep.mutate()}
            icon={<BookOpenCheck aria-hidden className="h-3.5 w-3.5" />}
          >
            Preparar entrevista
          </Button>
        }
      />
      <div className="card-body space-y-3">
        {(stages ?? []).length === 0 ? (
          <p className="text-xs text-content-subtle">
            Nenhuma etapa registrada. Marcou uma entrevista? Registre aqui.
          </p>
        ) : (
          <ul className="space-y-2">
            {(stages ?? []).map((stage) => (
              <li
                key={stage.id}
                className="flex items-center gap-2 rounded-lg border border-line bg-surface-sunken px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-content">
                    {STAGE_LABELS[stage.stage_type as StageType] ?? stage.stage_type}
                  </p>
                  <p className="text-2xs text-content-subtle">
                    {stage.completed_at
                      ? `Concluída em ${formatDate(stage.completed_at)}`
                      : stage.scheduled_at
                        ? `Agendada para ${formatDate(stage.scheduled_at)}`
                        : `Registrada em ${formatDate(stage.created_at)}`}
                    {stage.note ? ` · ${stage.note}` : ''}
                  </p>
                </div>
                {!stage.completed_at ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label="Marcar como concluída"
                    disabled={complete.isPending}
                    onClick={() => complete.mutate(stage.id)}
                    icon={<Check aria-hidden className="h-3.5 w-3.5" />}
                  >
                    Concluir
                  </Button>
                ) : null}
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Remover etapa"
                  className="text-danger hover:bg-danger/10 hover:text-danger"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(stage.id)}
                >
                  <Trash2 aria-hidden className="h-3.5 w-3.5" />
                </Button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex items-center gap-2 border-t border-line pt-3">
          <label htmlFor="stage-type" className="sr-only">
            Tipo de etapa
          </label>
          <Select
            id="stage-type"
            className="h-8 flex-1 py-0 text-xs"
            value={stageType}
            onChange={(event) => setStageType(event.target.value as StageType)}
          >
            {STAGE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {STAGE_LABELS[option]}
              </option>
            ))}
          </Select>
          <Button
            size="sm"
            loading={add.isPending}
            onClick={() => add.mutate()}
            icon={<Plus aria-hidden className="h-3.5 w-3.5" />}
          >
            Registrar
          </Button>
        </div>
      </div>

      <Modal
        open={prepOpen && Boolean(prep.data)}
        onClose={() => setPrepOpen(false)}
        size="lg"
        title="Preparo para a entrevista"
        description="Gerado só a partir do que está armazenado: o anúncio congelado no envio, os materiais exatos enviados e as lacunas da análise."
      >
        <div className="whitespace-pre-wrap text-sm leading-relaxed text-content-muted">
          {prep.data?.content}
        </div>
      </Modal>
    </Card>
  );
}
