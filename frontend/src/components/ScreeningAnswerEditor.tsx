import { Check, CircleHelp, Lightbulb, TriangleAlert } from 'lucide-react';

import { badgeClass, type ToneName } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { AnswerConfidence, ScreeningAnswer } from '@/types/api';

import { EmptyState } from './EmptyState';
import { Button, Input, Select, Textarea } from './primitives';

const CONFIDENCE_TONE: Record<AnswerConfidence, ToneName> = {
  high: 'success',
  medium: 'neutral',
  low: 'warning',
};

const CONFIDENCE_LABEL: Record<AnswerConfidence, string> = {
  high: 'Confiança alta',
  medium: 'Confiança média',
  low: 'Confiança baixa',
};

// Where the answer came from. "Sua resposta" is the trust anchor: the user's own
// words, either stored in the bank or typed during review.
const SOURCE_LABEL: Record<NonNullable<ScreeningAnswer['source']>, string> = {
  answer_bank: 'Do seu banco de respostas',
  user: 'Sua resposta',
  ai: 'Gerada pela IA',
};

export interface ScreeningAnswerEditorProps {
  answers: ScreeningAnswer[];
  onChange: (answers: ScreeningAnswer[]) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * Every screening answer the AI produced, editable before approval.
 *
 * Low-confidence answers arrive with `needs_review` set and stay visually flagged
 * until the operator confirms them; the submit action stays disabled while any
 * flag is open, so a guessed answer can never be sent silently.
 */
export function ScreeningAnswerEditor({
  answers,
  onChange,
  disabled = false,
  className,
}: ScreeningAnswerEditorProps) {
  if (answers.length === 0) {
    return (
      <EmptyState
        compact
        icon={CircleHelp}
        title="Sem perguntas de triagem"
        description="Esta candidatura não tinha perguntas extras a responder."
        className={className}
      />
    );
  }

  const patch = (index: number, partial: Partial<ScreeningAnswer>) => {
    onChange(answers.map((answer, position) => (position === index ? { ...answer, ...partial } : answer)));
  };

  return (
    <ul className={cn('space-y-3', className)}>
      {answers.map((answer, index) => {
        const inputId = `screening-answer-${index}`;
        const flagged = answer.needs_review;

        return (
          <li
            key={`${answer.field_id ?? 'q'}-${index}`}
            className={cn(
              'rounded-xl border px-3.5 py-3',
              flagged ? 'border-warning/50 bg-warning/[0.06]' : 'border-line bg-surface-sunken',
            )}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <label htmlFor={inputId} className="min-w-0 flex-1 text-sm font-medium leading-snug text-content">
                {answer.question}
              </label>
              <div className="flex shrink-0 items-center gap-1.5">
                {answer.source ? (
                  <span className={badgeClass(answer.source === 'ai' ? 'info' : 'accent')}>
                    {SOURCE_LABEL[answer.source]}
                  </span>
                ) : null}
                <span className={badgeClass(CONFIDENCE_TONE[answer.confidence])}>
                  {CONFIDENCE_LABEL[answer.confidence]}
                </span>
                {flagged ? (
                  <span className={badgeClass('warning')}>
                    <TriangleAlert aria-hidden className="h-3 w-3" />
                    Precisa da sua revisão
                  </span>
                ) : null}
              </div>
            </div>

            <div className="mt-2">
              {answer.question_type === 'textarea' ? (
                <Textarea
                  id={inputId}
                  rows={3}
                  disabled={disabled}
                  value={answer.answer}
                  onChange={(event) => patch(index, { answer: event.target.value })}
                />
              ) : answer.question_type === 'number' ? (
                <Input
                  id={inputId}
                  type="number"
                  inputMode="numeric"
                  disabled={disabled}
                  value={answer.answer}
                  onChange={(event) => patch(index, { answer: event.target.value })}
                />
              ) : answer.question_type === 'checkbox' ? (
                <Select
                  id={inputId}
                  disabled={disabled}
                  value={answer.answer}
                  onChange={(event) => patch(index, { answer: event.target.value })}
                >
                  <option value="Yes">Sim</option>
                  <option value="No">Não</option>
                </Select>
              ) : (
                <Input
                  id={inputId}
                  disabled={disabled}
                  value={answer.answer}
                  placeholder={
                    answer.question_type === 'select' || answer.question_type === 'radio'
                      ? 'Deve corresponder a uma das opções que o LinkedIn oferece'
                      : undefined
                  }
                  onChange={(event) => patch(index, { answer: event.target.value })}
                />
              )}
            </div>

            {answer.reasoning ? (
              <p className="mt-2 flex items-start gap-1.5 text-xs leading-relaxed text-content-subtle">
                <Lightbulb aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{answer.reasoning}</span>
              </p>
            ) : null}

            {flagged ? (
              <div className="mt-2.5 flex items-center justify-between gap-3">
                <p className="text-xs leading-relaxed text-warning-strong">
                  Confira esta resposta com o anúncio antes de aprovar.
                </p>
                <Button
                  size="sm"
                  disabled={disabled}
                  // The backend re-derives needs_review from the confidence and
                  // re-flags anything still marked "low", so clearing the flag on
                  // its own would not survive a save. A human confirming the
                  // answer is precisely what raises its confidence.
                  onClick={() =>
                    patch(index, {
                      needs_review: false,
                      confidence: answer.confidence === 'low' ? 'high' : answer.confidence,
                    })
                  }
                  icon={<Check aria-hidden className="h-3.5 w-3.5" />}
                >
                  Está correta
                </Button>
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
