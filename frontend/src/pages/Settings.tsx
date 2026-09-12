import {
  Bot,
  Info,
  KeyRound,
  Lock,
  Save,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { DryRunToggle } from '@/components/DryRunToggle';
import {
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  Note,
  PageHeader,
  Select,
  Skeleton,
  Toggle,
} from '@/components/primitives';
import { useToast } from '@/components/ToastProvider';
import {
  useAIProviders,
  useAIStatus,
  useSettings,
  useTestAICredentials,
  useUpdateSettings,
} from '@/hooks/useApi';
import { errorMessage } from '@/services/client';
import type { AICredentialResult, UserSettings, UserSettingsUpdate } from '@/types/api';

const TONES = ['professional', 'friendly', 'direct', 'enthusiastic'] as const;

const TONE_LABELS: Record<(typeof TONES)[number], string> = {
  professional: 'Profissional',
  friendly: 'Amigável',
  direct: 'Direto',
  enthusiastic: 'Entusiasmado',
};

const LANGUAGES: Array<{ value: string; label: string }> = [
  { value: 'auto', label: 'Acompanhar o idioma da vaga' },
  { value: 'en', label: 'Inglês' },
  { value: 'pt-BR', label: 'Português (Brasil)' },
  { value: 'es', label: 'Espanhol' },
  { value: 'fr', label: 'Francês' },
  { value: 'de', label: 'Alemão' },
];

interface Errors {
  actionDelay?: string;
  applyDelay?: string;
  workingHours?: string;
  aiKey?: string;
}

/** Empty means "use whatever provider the server configured". */
const INHERIT_PROVIDER = '';

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic (Claude)',
  groq: 'Groq',
  gemini: 'Google Gemini',
  openrouter: 'OpenRouter',
  cerebras: 'Cerebras',
};

function providerLabel(name: string) {
  return PROVIDER_LABELS[name] ?? name;
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
  id,
  tone,
}: {
  label: string;
  description: ReactNode;
  checked: boolean;
  onChange: (next: boolean) => void;
  id: string;
  tone?: 'accent' | 'warning' | 'success';
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div className="min-w-0">
        <label htmlFor={id} className="text-sm font-medium text-content">
          {label}
        </label>
        <p className="mt-0.5 text-xs leading-relaxed text-content-subtle">{description}</p>
      </div>
      <Toggle id={id} label={label} checked={checked} onChange={onChange} tone={tone} />
    </div>
  );
}

export function Settings() {
  const toast = useToast();
  const { data: settings, isLoading } = useSettings();
  const { data: aiStatus } = useAIStatus();
  const { data: providers } = useAIProviders();
  const [draft, setDraft] = useState<UserSettings | null>(null);
  const [errors, setErrors] = useState<Errors>({});
  // Kept out of `draft` on purpose: the key is write-only. It is never part of
  // what the server sent back, so it must never be part of the object compared
  // against it either.
  const [apiKey, setApiKey] = useState('');
  const [testResult, setTestResult] = useState<AICredentialResult | null>(null);

  useEffect(() => {
    if (settings) setDraft(settings);
  }, [settings]);

  const update = useUpdateSettings({
    onSuccess: () => {
      setApiKey('');
      setTestResult(null);
      toast.success('Configurações salvas');
    },
    onError: (error) => toast.error('Não foi possível salvar as configurações', errorMessage(error)),
  });

  const testCredentials = useTestAICredentials({
    onSuccess: (result) => setTestResult(result),
    onError: (error) => toast.error('Não foi possível testar a chave', errorMessage(error)),
  });

  const isDirty = useMemo(() => {
    if (!settings || !draft) return false;
    return JSON.stringify(draft) !== JSON.stringify(settings) || apiKey.length > 0;
  }, [settings, draft, apiKey]);

  if (isLoading || !draft) {
    return (
      <div className="space-y-5" aria-busy="true">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-72 rounded-xl" />
        <Skeleton className="h-56 rounded-xl" />
      </div>
    );
  }

  const patch = (partial: Partial<UserSettings>) =>
    setDraft((current) => (current ? { ...current, ...partial } : current));

  const numberPatch = (key: keyof UserSettings, raw: string, min: number, max: number) => {
    const parsed = Number(raw);
    if (Number.isNaN(parsed)) return;
    patch({ [key]: Math.max(min, Math.min(max, parsed)) } as Partial<UserSettings>);
  };

  const save = () => {
    const nextErrors: Errors = {};
    if (draft.action_delay_min > draft.action_delay_max) {
      nextErrors.actionDelay = 'O atraso mínimo não pode ser maior que o máximo.';
    }
    if (draft.apply_delay_min > draft.apply_delay_max) {
      nextErrors.applyDelay = 'O atraso mínimo não pode ser maior que o máximo.';
    }
    if (draft.working_hour_start >= draft.working_hour_end) {
      nextErrors.workingHours = 'A hora de início deve ser anterior à hora de término.';
    }
    const provider = draft.ai_provider ?? INHERIT_PROVIDER;
    const providerChanged = provider !== (settings?.ai_provider ?? INHERIT_PROVIDER);
    if (provider && !apiKey && (providerChanged || !settings?.ai_key_set)) {
      // The server refuses this too. Saying so here spares a round trip and,
      // more to the point, spares the user retyping every other field.
      // Two different problems: nothing stored at all, versus something stored
      // that belongs to the provider being left behind.
      nextErrors.aiKey =
        settings?.ai_key_set && providerChanged
          ? `A chave guardada é do provedor anterior. Cole uma chave de ${providerLabel(provider)}.`
          : `Escolher ${providerLabel(provider)} exige uma chave de API.`;
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    // dry_run is owned by the dedicated toggle, which has its own confirmation step.
    const payload: UserSettingsUpdate = { ...draft };
    delete payload.dry_run;
    // Read-only: it says whether a key is stored, and is not a field to send back.
    delete payload.ai_key_set;
    if (apiKey) payload.ai_api_key = apiKey;
    update.mutate(payload);
  };

  const provider = draft.ai_provider ?? INHERIT_PROVIDER;
  const providerChanged = provider !== (settings?.ai_provider ?? INHERIT_PROVIDER);
  const storedKeyUsable = Boolean(settings?.ai_key_set) && !providerChanged;

  return (
    <div className="space-y-5 pb-24">
      <PageHeader
        title="Configurações"
        description="Salvaguardas, interruptores de segurança e comportamento da IA. Afrouxar uma salvaguarda não deixa a ferramenta mais rápida — deixa a sua conta mais fácil de sinalizar."
      />

      <Card>
        <CardHeader
          title="Salvaguardas da automação"
          description="Limites que mantêm o volume baixo e o ritmo lento. Eles reduzem o risco de detecção — não o eliminam."
        />
        <div className="card-body space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Limite diário de envios"
              htmlFor="settings-daily-cap"
              hint="Máximo de candidaturas que você pode enviar por dia (1–50). Um humano se candidatando a 40 vagas numa noite já é incomum; ir além é o jeito mais rápido de parecer um robô."
            >
              <Input
                id="settings-daily-cap"
                type="number"
                min={1}
                max={50}
                value={draft.daily_cap}
                onChange={(event) => numberPatch('daily_cap', event.target.value, 1, 50)}
              />
            </Field>

            <Field
              label="Nota mínima de aderência"
              htmlFor="settings-min-score"
              hint="Vagas com nota abaixo disso são puladas em vez de recebermos candidatura. Baixar isso gasta o seu limite diário em vagas que não combinam com você, o que é pior para você do que para o LinkedIn."
            >
              <Input
                id="settings-min-score"
                type="number"
                min={0}
                max={100}
                value={draft.min_score}
                onChange={(event) => numberPatch('min_score', event.target.value, 0, 100)}
              />
            </Field>
          </div>

          <div>
            <p className="label">Atraso entre ações (segundos)</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Mínimo" htmlFor="settings-action-min">
                <Input
                  id="settings-action-min"
                  type="number"
                  step={0.5}
                  min={0.5}
                  max={60}
                  value={draft.action_delay_min}
                  onChange={(event) => numberPatch('action_delay_min', event.target.value, 0.5, 60)}
                />
              </Field>
              <Field label="Máximo" htmlFor="settings-action-max" error={errors.actionDelay}>
                <Input
                  id="settings-action-max"
                  type="number"
                  step={0.5}
                  min={0.5}
                  max={120}
                  value={draft.action_delay_max}
                  onChange={(event) => numberPatch('action_delay_max', event.target.value, 0.5, 120)}
                />
              </Field>
            </div>
            <p className="hint">
              Cada clique e tecla espera um tempo aleatório dentro dessa faixa. Atrasos aleatórios
              reduzem, mas não eliminam, o risco de detecção — nenhuma configuração de atraso torna a
              automação segura ou permitida.
            </p>
          </div>

          <div>
            <p className="label">Atraso entre candidaturas (segundos)</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Mínimo" htmlFor="settings-apply-min">
                <Input
                  id="settings-apply-min"
                  type="number"
                  step={1}
                  min={5}
                  max={600}
                  value={draft.apply_delay_min}
                  onChange={(event) => numberPatch('apply_delay_min', event.target.value, 5, 600)}
                />
              </Field>
              <Field label="Máximo" htmlFor="settings-apply-max" error={errors.applyDelay}>
                <Input
                  id="settings-apply-max"
                  type="number"
                  step={1}
                  min={5}
                  max={1800}
                  value={draft.apply_delay_max}
                  onChange={(event) => numberPatch('apply_delay_max', event.target.value, 5, 1800)}
                />
              </Field>
            </div>
            <p className="hint">
              A pausa entre duas candidaturas. Pausas curtas produzem uma rajada de atividade que não
              se parece em nada com uma pessoa lendo descrições de vagas.
            </p>
          </div>

          <div>
            <p className="label">Horário de funcionamento</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Hora de início" htmlFor="settings-hour-start">
                <Input
                  id="settings-hour-start"
                  type="number"
                  min={0}
                  max={23}
                  value={draft.working_hour_start}
                  onChange={(event) => numberPatch('working_hour_start', event.target.value, 0, 23)}
                />
              </Field>
              <Field label="Hora de término" htmlFor="settings-hour-end" error={errors.workingHours}>
                <Input
                  id="settings-hour-end"
                  type="number"
                  min={1}
                  max={24}
                  value={draft.working_hour_end}
                  onChange={(event) => numberPatch('working_hour_end', event.target.value, 1, 24)}
                />
              </Field>
            </div>
            <p className="hint">
              As execuções ficam restritas a esta janela, no seu horário local. Uma janela que cobre o
              dia inteiro significa atividade às 4h da manhã, um dos padrões mais fáceis de detectar.
            </p>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader title="Segurança" description="Os interruptores que decidem se algo pode ser enviado." />
        <div className="card-body space-y-4">
          <div className="flex items-start justify-between gap-4 rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-sm font-medium text-content">
                Modo de teste
                <ShieldCheck aria-hidden className="h-3.5 w-3.5 text-success" />
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-content-subtle">
                Com o modo de teste ligado, os formulários são preenchidos e revisados, mas o botão de
                enviar nunca é clicado. Desligue apenas quando estiver pronto para mandar candidaturas
                de verdade — e espere confirmar essa escolha.
              </p>
            </div>
            <DryRunToggle />
          </div>

          {draft.require_manual_approval ? (
            <div className="flex items-start justify-between gap-4 rounded-lg border border-success/40 bg-success/[0.07] px-3.5 py-3">
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 text-sm font-medium text-content">
                  Aprovação manual obrigatória
                  <Lock aria-hidden className="h-3.5 w-3.5 text-success" />
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-content-subtle">
                  Toda candidatura espera você abrir, ler e aprovar. É isso que o modo assistido
                  significa, então este painel não vai desligar — não existe envio em massa em lugar
                  nenhum do app.
                </p>
              </div>
              <span className="badge badge-success shrink-0">Sempre ativa</span>
            </div>
          ) : (
            <div className="rounded-lg border border-danger/40 bg-danger/[0.07] px-3.5 py-3">
              <p className="flex items-center gap-1.5 text-sm font-medium text-danger-strong">
                <ShieldAlert aria-hidden className="h-4 w-4" />
                A aprovação manual está desativada no momento
              </p>
              <p className="mt-1 text-xs leading-relaxed text-content-muted">
                Algo desligou essa opção fora deste painel. Candidaturas poderiam ser enviadas sem
                você lê-las antes. Ligue de novo.
              </p>
              <Button
                className="mt-2.5"
                size="sm"
                variant="primary"
                onClick={() => patch({ require_manual_approval: true })}
              >
                Exigir aprovação manual de novo
              </Button>
            </div>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="IA"
          description="Quem responde, com a chave de quem, e como soa o texto gerado."
        />
        <div className="card-body space-y-4">
          <div className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
            <p className="flex items-center gap-1.5 text-sm font-medium text-content">
              <KeyRound aria-hidden className="h-3.5 w-3.5 text-content-subtle" />
              Chave de IA
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-content-subtle">
              Todo tier gratuito é limitado <strong>por chave</strong>. Usando a do servidor, você
              divide esse limite com as outras contas; trazendo a sua, o limite é só seu e não custa
              nada — Groq, Gemini, OpenRouter e Cerebras dão chave grátis em dois minutos.
            </p>

            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <Field label="Provedor" htmlFor="settings-ai-provider">
                <Select
                  id="settings-ai-provider"
                  value={provider}
                  onChange={(event) => {
                    setTestResult(null);
                    setApiKey('');
                    patch({ ai_provider: event.target.value || null });
                  }}
                >
                  <option value={INHERIT_PROVIDER}>Usar o provedor do servidor</option>
                  {(providers ?? []).map((option) => (
                    <option key={option.name} value={option.name}>
                      {providerLabel(option.name)}
                    </option>
                  ))}
                </Select>
              </Field>

              {provider ? (
                <Field
                  label="Chave de API"
                  htmlFor="settings-ai-key"
                  error={errors.aiKey}
                  hint={
                    storedKeyUsable
                      ? 'Uma chave já está guardada. Deixe em branco para mantê-la.'
                      : 'Guardada criptografada. Não é exibida de volta, nem mascarada.'
                  }
                >
                  <Input
                    id="settings-ai-key"
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={apiKey}
                    placeholder={storedKeyUsable ? '••••••••  (guardada)' : 'Cole a chave aqui'}
                    onChange={(event) => {
                      setTestResult(null);
                      setApiKey(event.target.value);
                    }}
                  />
                </Field>
              ) : null}
            </div>

            {provider ? (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  loading={testCredentials.isPending}
                  disabled={!apiKey && !storedKeyUsable}
                  onClick={() => testCredentials.mutate({ provider, api_key: apiKey })}
                >
                  Testar chave
                </Button>
                {providers?.find((option) => option.name === provider)?.key_url ? (
                  <span className="text-xs text-content-subtle">
                    {providers.find((option) => option.name === provider)?.key_url}
                  </span>
                ) : null}
              </div>
            ) : null}

            {testResult ? (
              <p
                className={`mt-2.5 text-xs leading-relaxed ${
                  testResult.ok ? 'text-success' : 'text-danger-strong'
                }`}
                role="status"
              >
                {testResult.ok
                  ? `Respondeu: ${testResult.provider}/${testResult.model}. A chave ainda não foi salva — use "Salvar configurações".`
                  : testResult.detail}
              </p>
            ) : null}

            {aiStatus ? (
              <p className="mt-2.5 text-xs text-content-subtle">
                {aiStatus.configured
                  ? `Agora respondendo: ${aiStatus.provider}/${aiStatus.model} — ${
                      aiStatus.source === 'account' ? 'a sua chave' : 'a chave do servidor'
                    }.`
                  : aiStatus.detail || 'Nenhum provedor de IA disponível para esta conta.'}
              </p>
            ) : null}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Modelo"
              htmlFor="settings-model"
              hint="Deixe vazio para usar o modelo padrão do provedor."
            >
              <Input
                id="settings-model"
                value={draft.ai_model ?? ''}
                placeholder="Padrão do servidor"
                onChange={(event) => patch({ ai_model: event.target.value.trim() || null })}
              />
            </Field>

            <Field label="Tom da carta de apresentação" htmlFor="settings-tone">
              <Select
                id="settings-tone"
                value={draft.cover_letter_tone}
                onChange={(event) => patch({ cover_letter_tone: event.target.value })}
              >
                {TONES.map((tone) => (
                  <option key={tone} value={tone}>
                    {TONE_LABELS[tone]}
                  </option>
                ))}
              </Select>
            </Field>

            <Field
              label="Idioma do conteúdo"
              htmlFor="settings-language"
              hint="Aplica-se às cartas de apresentação e às respostas de triagem."
            >
              <Select
                id="settings-language"
                value={draft.content_language}
                onChange={(event) => patch({ content_language: event.target.value })}
              >
                {LANGUAGES.map((language) => (
                  <option key={language.value} value={language.value}>
                    {language.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <div className="divide-y divide-line border-t border-line">
            <ToggleRow
              id="settings-generate-cover-letter"
              label="Gerar uma carta de apresentação para cada candidatura"
              description="Custa uma chamada extra de IA por vaga. Desligue se os formulários que você encontra raramente pedem uma."
              checked={draft.generate_cover_letter}
              onChange={(next) => patch({ generate_cover_letter: next })}
            />
          </div>

          <Note tone="neutral" icon={<Bot aria-hidden className="h-3.5 w-3.5" />}>
            A IA nunca decide enviar nada. Ela apenas pontua vagas e redige textos que você lê e
            aprova.
          </Note>
        </div>
      </Card>

      <Note tone="warning" icon={<TriangleAlert aria-hidden className="h-3.5 w-3.5" />}>
        Nenhuma combinação dessas configurações torna a automação do LinkedIn permitida. Ela viola os
        Termos de Uso do LinkedIn, e restrições de conta são um resultado possível e real.
      </Note>

      {isDirty ? (
        <div className="sticky bottom-4 z-20 mx-auto w-full max-w-2xl">
          <Card className="flex items-center gap-3 border-accent-500/40 px-4 py-3 shadow-lifted">
            <p className="flex items-center gap-1.5 text-sm text-content-muted">
              <Info aria-hidden className="h-3.5 w-3.5" />
              Alterações não salvas
            </p>
            <Button
              className="ml-auto"
              disabled={update.isPending}
              onClick={() => settings && setDraft(settings)}
            >
              Reverter
            </Button>
            <Button
              variant="primary"
              loading={update.isPending}
              onClick={save}
              icon={<Save aria-hidden className="h-4 w-4" />}
            >
              Salvar configurações
            </Button>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
