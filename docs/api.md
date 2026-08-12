# Referência da API

Toda rota fica sob `/api`. Os corpos de requisição e resposta são JSON salvo indicação em contrário.

> **Os docs ao vivo superam esta página.** O app em execução serve o OpenAPI interativo em
> **<http://localhost:8000/docs>** (e o schema bruto em `/openapi.json`), gerado a partir dos modelos
> Pydantic reais. Use-o para experimentar chamadas e confirmar os tipos exatos dos campos; use esta página para o formato de
> toda a superfície e o raciocínio por trás dela.

## Autenticação

Todas as rotas exceto `POST /api/auth/register`, `POST /api/auth/login` e `GET /api/health` exigem um bearer
token:

```
Authorization: Bearer <access_token>
```

Obtenha um em `/api/auth/login`. É um JWT assinado com `SECRET_KEY`, válido por
`ACCESS_TOKEN_TTL_MINUTES` (12 horas por padrão). Não há refresh token — faça login de novo quando ele expirar.

Toda query é escopada ao usuário autenticado. Requisitar a vaga ou candidatura de outro usuário retorna `404`,
não `403`, para que os ids não sejam enumeráveis.

## Convenções

| | |
|---|---|
| Timestamps | ISO 8601, UTC, com timezone — `2026-08-11T14:23:05+00:00` |
| Enums | strings snake_case em minúsculas (`awaiting_review`, `job_found`) |
| Paginação | `?limit=&offset=` nos endpoints de lista, embrulhado em `Page` |
| Limites de taxa | `120/minute` por padrão, `10/minute` nas rotas de auth |

`Page<T>`:

```json
{ "items": [], "total": 0, "limit": 50, "offset": 0 }
```

`Message`:

```json
{ "detail": "..." }
```

### Códigos de status

| Código | Significado |
|---|---|
| `200` | Sucesso |
| `201` | Criado (apenas `POST /api/auth/register`) |
| `204` | Sucesso, sem corpo (apenas `DELETE /api/searches/{id}`) |
| `401` | Token ausente, malformado ou expirado |
| `404` | Não encontrado, ou não é seu |
| `409` | Conflito — ex.: registrar um e-mail que existe, ou preparar uma vaga que já tem uma candidatura |
| `422` | Erro de validação — o formato padrão `{"detail": [...]}` do Pydantic |
| `429` | Limite de taxa atingido |

---

## Auth

### `POST /api/auth/register`

Cria uma conta local. Este é o login do próprio aplicativo, sem relação com o LinkedIn.

```json
{ "email": "you@example.com", "password": "at-least-ten-chars", "full_name": "Your Name" }
```

`password` tem 10–72 caracteres; 72 bytes é o limite do bcrypt e entradas mais longas são rejeitadas em vez de
silenciosamente truncadas. `full_name` é opcional.

A nova conta é criada com um perfil vazio e salvaguardas padrão conservadoras — dry run ligado, aprovação
manual obrigatória — para que não consiga enviar nada antes de você configurá-la.

→ `201` com `TokenResponse`:

```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 43200,
  "user": { "id": 1, "email": "you@example.com", "full_name": "Your Name",
            "is_active": true, "is_admin": false,
            "created_at": "2026-08-11T12:00:00+00:00", "last_login_at": null }
}
```

### `POST /api/auth/login`

```json
{ "email": "you@example.com", "password": "..." }
```

→ `TokenResponse`. `401` em credenciais inválidas, sem distinguir uma senha errada de um e-mail desconhecido.

### `GET /api/auth/me`

→ `UserRead` para o sujeito do bearer token.

---

## Perfil

O seu currículo e o banco de respostas de que a IA se vale. Tudo aqui é opcional, mas um perfil raso produz notas
fracas e cartas de apresentação vagas.

### `GET /api/profile`

→ `ProfileRead`:

```json
{
  "headline": "Backend Engineer",
  "location": "Fortaleza, Brazil",
  "phone": "+55 85 ...",
  "years_of_experience": 6,
  "summary": "...",
  "resume_text": "...",
  "resume_filename": "cv.pdf",
  "skills": ["Python", "FastAPI", "PostgreSQL"],
  "preferred_languages": ["pt-BR", "en"],
  "answer_bank": { "salary_expectation": "R$ 15.000", "notice_period": "30 days" },
  "updated_at": "2026-08-11T12:00:00+00:00"
}
```

### `PUT /api/profile`

`ProfileUpdate` — todo campo opcional; campos omitidos ficam intocados.

| Campo | Restrição |
|---|---|
| `headline` | ≤ 300 caracteres |
| `location` | ≤ 200 caracteres |
| `phone` | ≤ 50 caracteres |
| `years_of_experience` | 0–70 |
| `summary`, `resume_text` | texto livre |
| `skills`, `preferred_languages` | arrays de strings — substituídos por inteiro, não mesclados |
| `answer_bank` | objeto livre — substituído por inteiro |

→ `ProfileRead`.

O `answer_bank` é o que transforma perguntas de triagem recorrentes em respostas confiáveis. As chaves são suas para
escolher; o modelo as compara semanticamente contra o texto da pergunta:

```json
{ "salary_expectation": "R$ 15.000/month",
  "notice_period": "30 days",
  "work_authorization": "Brazilian citizen",
  "years_python": "6" }
```

### `POST /api/profile/resume`

`multipart/form-data`, um campo chamado `file`, um PDF.

```bash
curl -X POST http://localhost:8000/api/profile/resume \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/cv.pdf"
```

O arquivo é armazenado em `DATA_DIR/resumes/`, o texto dele é extraído para `resume_text`, e ambos são
retornados no `ProfileRead` atualizado. O mesmo arquivo é anexado aos formulários de Candidatura Simplificada.

---

## Configurações

Salvaguardas e preferências de IA por usuário. Os significados campo a campo, faixas e o risco de afrouxar cada
salvaguarda estão em [configuration.md](configuration.md#per-user-settings-usersettings).

### `GET /api/settings`

→ `UserSettingsRead`:

```json
{
  "daily_cap": 15, "min_score": 70,
  "action_delay_min": 2.5, "action_delay_max": 7.0,
  "apply_delay_min": 45.0, "apply_delay_max": 120.0,
  "working_hour_start": 8, "working_hour_end": 20,
  "require_manual_approval": true, "dry_run": true,
  "ai_model": null, "cover_letter_tone": "profissional",
  "content_language": "job", "generate_cover_letter": true
}
```

### `PUT /api/settings`

`UserSettingsUpdate` — todos os campos opcionais. Regras entre campos são impostas e retornam `422` quando quebradas:
`action_delay_min ≤ action_delay_max`, `apply_delay_min ≤ apply_delay_max` e
`working_hour_start < working_hour_end`.

→ `UserSettingsRead`.

---

## Buscas

Um conjunto de filtros salvo. Salvo em vez de ad-hoc para que uma execução seja reproduzível e `max_results` limite a varredura.

### `GET /api/searches`

→ `SearchRead[]`.

### `POST /api/searches`

`SearchCreate`:

```json
{
  "name": "Senior Python — remote",
  "keywords": "senior python engineer",
  "location": "Brazil",
  "remote_filter": "remote",
  "experience_levels": ["mid_senior", "director"],
  "date_posted": "week",
  "easy_apply_only": true,
  "max_results": 25
}
```

| Campo | Notas |
|---|---|
| `name` | obrigatório, ≤ 200 caracteres |
| `keywords` | obrigatório, 1–300 caracteres |
| `location` | ≤ 200 caracteres |
| `remote_filter` | string livre, ≤ 50 — `remote`, `hybrid`, `onsite` |
| `experience_levels` | array de strings |
| `date_posted` | ≤ 30 caracteres — `day`, `week`, `month` |
| `easy_apply_only` | padrão `true`. Só vagas de Candidatura Simplificada podem ser preenchidas automaticamente |
| `max_results` | 1–100, padrão 25. Um teto por execução que mantém as varreduras curtas |

→ `SearchRead` (adiciona `id`, `is_active`, `last_run_at`, `created_at`).

### `PATCH /api/searches/{id}`

`SearchUpdate` — os mesmos campos, todos opcionais, mais `is_active`. → `SearchRead`.

### `DELETE /api/searches/{id}`

→ `204`. As vagas já encontradas pela busca são mantidas; o `search_id` delas vira `null`.

---

## Vagas

### `GET /api/jobs`

| Query param | Tipo | Notas |
|---|---|---|
| `status` | `JobStatus` | `discovered`, `analyzed`, `skipped`, `queued`, `applied`, `failed` |
| `min_score` | int | Vagas com nota de pelo menos isto |
| `search_id` | int | Só vagas de uma busca salva |
| `limit` | int | Tamanho da página |
| `offset` | int | Offset da página |

→ `Page<JobRead>`:

```json
{
  "items": [{
    "id": 42,
    "external_id": "3812345678",
    "title": "Senior Python Engineer",
    "company": "Example Co",
    "location": "Remote — Brazil",
    "url": "https://www.linkedin.com/jobs/view/3812345678",
    "workplace_type": "remote",
    "easy_apply": true,
    "status": "analyzed",
    "score": 87,
    "score_reasons": ["6 years of Python matches the 5+ requirement", "FastAPI is named in the posting"],
    "missing_requirements": ["Kubernetes in production"],
    "skip_reason": null,
    "detected_language": "en",
    "posted_at": "2026-08-10T09:00:00+00:00",
    "created_at": "2026-08-11T12:05:00+00:00",
    "search_id": 3,
    "application_id": null
  }],
  "total": 1, "limit": 50, "offset": 0
}
```

`score_reasons` e `missing_requirements` vêm direto do modelo. A segunda lista é a útil:
ela diz o que um recrutador vai perguntar.

### `GET /api/jobs/{id}`

→ `JobDetail` — `JobRead` mais a `description` completa.

### `POST /api/jobs/{id}/skip`

Marca a vaga como `skipped` para que seja excluída de execuções futuras. → `JobRead`.

### `POST /api/jobs/{id}/analyze`

Pontua (ou repontua) uma vaga com a IA. Útil para uma vaga que chegou antes de você terminar o seu perfil,
ou quando `analyze: false` foi usado na execução da busca. → `JobRead` com `score`, `score_reasons` e
`missing_requirements` preenchidos, e `status` definido como `analyzed`.

Exige `ANTHROPIC_API_KEY`; sem ela a chamada falha em vez de inventar uma nota.

---

## Candidaturas

### `GET /api/applications`

| Query param | Tipo |
|---|---|
| `status` | `ApplicationStatus` — `draft`, `preparing`, `awaiting_review`, `submitting`, `submitted`, `discarded`, `failed` |
| `limit`, `offset` | int |

→ `Page<ApplicationRead>`:

```json
{
  "items": [{
    "id": 7,
    "job_id": 42,
    "status": "awaiting_review",
    "cover_letter": "Dear hiring team, ...",
    "screening_answers": [{
      "question": "How many years of Python experience do you have?",
      "answer": "6",
      "question_type": "number",
      "confidence": "high",
      "needs_review": false,
      "reasoning": "Profile states 6 years",
      "field_id": "urn:li:fs_easyApplyFormElement:123"
    }],
    "resume_filename": "cv.pdf",
    "total_steps": 4,
    "current_step": 4,
    "needs_human_input": false,
    "was_dry_run": true,
    "approved_at": null,
    "submitted_at": null,
    "error_message": null,
    "created_at": "2026-08-11T12:10:00+00:00",
    "updated_at": "2026-08-11T12:12:00+00:00"
  }],
  "total": 1, "limit": 50, "offset": 0
}
```

Dois campos dirigem a UI de revisão. `needs_review` numa resposta significa que o modelo não estava confiante — um valor de
confiança `low` o seta automaticamente, para que uma resposta de baixa confiança nunca chegue a você sem marcação.
`needs_human_input` na candidatura significa que pelo menos um campo não pôde ser preenchido de forma alguma.

`was_dry_run` registra se isto foi um ensaio, para que o seu histórico distinga treinos de envios
reais.

### `GET /api/applications/{id}`

→ `ApplicationDetail` — `ApplicationRead` mais o `job` aninhado (`JobRead`) e o array `events` completo
(`ApplicationEventOut[]`).

### `PATCH /api/applications/{id}`

As suas edições durante a revisão, antes de aprovar.

```json
{
  "cover_letter": "My edited letter...",
  "screening_answers": [
    { "question": "Years of Python?", "answer": "4", "question_type": "number",
      "confidence": "high", "needs_review": false,
      "field_id": "urn:li:fs_easyApplyFormElement:123" }
  ]
}
```

Ambos os campos são opcionais. `screening_answers` é validado contra `ScreeningAnswer` e substitui o array
inteiro — envie cada resposta, não só as que você mudou. Preserve cada `field_id`; é assim que uma resposta é
casada de volta ao seu campo de formulário.

→ `ApplicationDetail`. Registra um evento `USER_EDITED`.

### `POST /api/applications/{id}/submit`

**O único endpoint que envia algo ao LinkedIn.**

```json
{ "confirm": true }
```

`confirm` é obrigatório e precisa ser `true` — é o consentimento, e não há padrão. O endpoint age sobre
exatamente uma candidatura, identificada no caminho. Não há rota de envio em massa, por design.

→ `ApplicationDetail` com `status: "submitted"`, `approved_at` e `submitted_at` definidos. Registra
os eventos `USER_APPROVED` e `SUBMITTED`.

Recusa quando a candidatura não está em `awaiting_review`, quando o limite diário é atingido, ou quando a hora
atual está fora da janela de horário.

Com `dry_run: true` o fluxo completa sem um envio real e a candidatura é marcada
`was_dry_run: true`.

### `POST /api/applications/{id}/discard`

Abandona o rascunho e fecha o modal do LinkedIn. → `ApplicationDetail` com `status: "discarded"`. Registra
um evento `DISCARDED`.

### `GET /api/applications/{id}/events`

A trilha de auditoria, da mais antiga primeiro.

→ `ApplicationEventOut[]`:

```json
[
  { "id": 1, "event_type": "form_opened", "message": "Easy Apply modal opened",
    "payload": { "total_steps": 4 }, "is_error": false,
    "created_at": "2026-08-11T12:10:05+00:00" },
  { "id": 2, "event_type": "question_answered", "message": "Years of Python experience",
    "payload": { "field_id": "...", "value": "6", "confidence": "high" },
    "is_error": false, "created_at": "2026-08-11T12:10:12+00:00" }
]
```

Tipos de evento: `job_found`, `job_analyzed`, `score_assigned`, `cover_letter_generated`, `form_opened`,
`form_step_completed`, `question_answered`, `resume_uploaded`, `awaiting_review`, `user_edited`,
`user_approved`, `submitted`, `discarded`, `error`.

Este é o primeiro lugar a olhar quando uma candidatura falha. O `payload` carrega os detalhes —
qual campo, quais opções, qual seletor — para que uma falha seja diagnosticável sem reproduzi-la.

---

## Automação

O engine. Buscar, preparar e enviar são operações separadas que você invoca separadamente.

### `GET /api/automation/session`

→ `SessionStatus`:

```json
{
  "browser_open": true,
  "logged_in": true,
  "blocked": false,
  "blocked_reason": null,
  "active_run_id": null,
  "applications_today": 3,
  "daily_cap": 15,
  "dry_run": true,
  "ai_configured": true
}
```

`blocked: true` significa que uma verificação de segurança foi detectada. Resolva você mesmo no navegador; veja
[safety.md](safety.md#security-checkpoints).

### `POST /api/automation/session/start`

Abre o Chromium, restaurando a sessão salva se houver uma. → `SessionStatus`.

Se `logged_in` for `false`, faça login **manualmente na janela do navegador** — pelo noVNC em
<http://localhost:6080> no Docker, ou pela janela do desktop localmente. O projeto nunca recebe a sua
senha do LinkedIn.

### `POST /api/automation/session/stop`

Fecha o navegador e persiste o estado de sessão criptografado. → `SessionStatus`.

### `POST /api/automation/search`

Roda uma busca e, por padrão, pontua o que encontra. Nunca se candidata a nada.

`SearchRunRequest`:

```json
{ "search_id": 3, "analyze": true }
```

ou com filtros ad-hoc:

```json
{
  "keywords": "senior python engineer",
  "location": "Brazil",
  "remote_filter": "remote",
  "date_posted": "week",
  "experience_levels": ["mid_senior"],
  "max_results": 25,
  "analyze": true
}
```

`max_results` é 1–100 (padrão 25). `analyze: false` pula a pontuação por IA — mais rápido e grátis, e você pode pontuar
vagas individuais depois com `POST /api/jobs/{id}/analyze`.

→ `AutomationRunRead`:

```json
{
  "id": 12, "kind": "search", "status": "running", "dry_run": true, "search_id": 3,
  "jobs_found": 0, "jobs_analyzed": 0, "jobs_skipped": 0,
  "applications_prepared": 0, "applications_submitted": 0,
  "stop_requested": false, "blocked_reason": null, "error_message": null,
  "started_at": "2026-08-11T12:05:00+00:00", "finished_at": null,
  "created_at": "2026-08-11T12:05:00+00:00"
}
```

A execução prossegue em segundo plano. Acompanhe-a pelo WebSocket, ou consulte
`GET /api/automation/runs/{id}`.

### `POST /api/automation/preview`

**Sempre chame isto antes de `prepare`.** Ele reporta o que aconteceria, e não muda nada.

`PrepareRequest`:

```json
{ "job_ids": [42, 43, 44], "confirmed": false }
```

→ `PreviewResponse`:

```json
{
  "jobs_to_process": 2,
  "already_applied": 1,
  "below_threshold": 0,
  "remaining_today": 12,
  "daily_cap": 15,
  "dry_run": true,
  "requires_confirmation": true,
  "jobs": [],
  "warnings": ["Job 44 already has an application"]
}
```

O objetivo é que você veja o volume e as condições antes de qualquer coisa rodar. Não há caminho em que
dezenas de candidaturas sejam preparadas sem que o número tenha sido mostrado a você primeiro.

### `POST /api/automation/prepare`

Abre o formulário de Candidatura Simplificada para cada vaga, preenche, e **para na etapa de revisão**.

```json
{ "job_ids": [42, 43], "confirmed": true }
```

`job_ids` tem 1–50 entradas. `confirmed` precisa ser `true` — significa que você viu a pré-visualização.

→ `AutomationRunRead` com `kind: "prepare"`. Cada vaga ganha uma candidatura em `awaiting_review`.

**Isto nunca envia.** `LinkedInService.fill_and_advance()` não tem caminho de código para o envio; o envio é
`POST /api/applications/{id}/submit`, uma candidatura por vez, com a sua própria confirmação.

### `POST /api/automation/stop`

**O botão de parada.** Seta `stop_requested` na execução ativa. O engine verifica a flag entre etapas e
levanta `StopRequestedError`, para que pare de forma limpa em vez de no meio de um clique — nenhum formulário meio-enviado, nenhum
estado de banco rasgado.

→ `Message`. O status da execução vira `stopped`.

Parar não é instantâneo: tem efeito na próxima fronteira de etapa, que pode estar a alguns segundos dentro de um
atraso aleatório.

### `GET /api/automation/runs`

| Query param | Tipo |
|---|---|
| `limit` | int |

→ `AutomationRunRead[]`, da mais recente primeiro.

### `GET /api/automation/runs/{id}`

→ `AutomationRunRead`. Consulte isto se preferir não manter um WebSocket aberto.

Status: `pending`, `running`, `paused`, `completed`, `stopped` (botão de parada), `failed`, `blocked`
(verificação de segurança).

---

## IA

### `GET /api/ai/status`

```json
{ "configured": true, "model": "claude-opus-5" }
```

`configured: false` significa que `ANTHROPIC_API_KEY` não está definida. A busca e o preenchimento de formulários ainda funcionam; pontuação, cartas de
apresentação e sugestões de resposta não.

### `POST /api/ai/cover-letter/{job_id}`

Gera (ou regenera) uma carta de apresentação para uma vaga.

```json
{ "content": "Dear hiring team, ...", "language": "en" }
```

`language` reflete `UserSettings.content_language`: `job` significa o idioma detectado do anúncio,
caso contrário a tag que você fixou. Esta chamada usa esforço `high` — a carta vale mais que os tokens que
custa, diferente da pontuação em massa.

O modelo pode declinar. Isso é registrado em `AIAnalysis.was_refusal` e a candidatura recorre ao preenchimento
manual; escreva a carta você mesmo.

---

## Estatísticas

### `GET /api/stats`

→ `DashboardStats`:

```json
{
  "jobs_total": 128,
  "jobs_by_status": { "discovered": 12, "analyzed": 80, "skipped": 30, "applied": 6 },
  "applications_total": 6,
  "applications_today": 3,
  "awaiting_review": 2,
  "daily_cap": 15,
  "remaining_today": 12,
  "average_score": 71.4,
  "score_distribution": [{ "label": "80-100", "count": 24 }],
  "applications_last_7_days": [{ "date": "2026-08-11", "count": 3 }],
  "ai_calls_total": 92,
  "ai_tokens_input": 481203,
  "ai_tokens_output": 38112
}
```

Os três últimos campos são o seu medidor de custo.

---

## Saúde

### `GET /api/health`

Sem auth necessária.

```json
{ "status": "ok", "version": "0.1.0" }
```

---

## WebSocket

### `GET /api/ws?token=<jwt>`

O feed de atividade ao vivo. O token vai na query string porque navegadores não conseguem setar cabeçalhos num
handshake de WebSocket.

```javascript
const ws = new WebSocket(`ws://localhost:8000/api/ws?token=${token}`);
ws.onmessage = (e) => {
  const event = JSON.parse(e.data);
  console.log(event.name, event.level, event.message);
};
```

Na conexão, os últimos 200 eventos do seu usuário são reproduzidos, para que um recarregamento de página reconstrua o feed em vez de
começar vazio. Os eventos são endereçados por usuário — você nunca vê a atividade de outro usuário.

Publicar nunca levanta exceção no servidor: uma aba fechada não pode quebrar uma execução em andamento.

### Envelope

```json
{
  "name": "job.analyzed",
  "timestamp": "2026-08-11T12:06:31.482913+00:00",
  "run_id": 12,
  "job_id": 42,
  "application_id": null,
  "message": "Senior Python Engineer — 87",
  "level": "info",
  "data": { "score": 87, "recommend_apply": true }
}
```

| Campo | Tipo | Notas |
|---|---|---|
| `name` | `EventName` | Veja o catálogo abaixo |
| `timestamp` | ISO 8601 UTC | |
| `run_id` | int \| null | Presente em eventos do engine |
| `job_id` | int \| null | |
| `application_id` | int \| null | |
| `message` | string \| null | Linha legível por humanos |
| `level` | string | `info`, `warning`, `error`, `success` |
| `data` | object | Payload específico do evento |

A fonte de verdade em Python é
[`app/observability/events.py`](../backend/app/observability/events.py); o espelho no frontend é
`frontend/src/types/events.ts`. Mantenha-os em sincronia.

### Catálogo de eventos

| `name` | `level` típico | Quando dispara | O que geralmente está em `data` |
|---|---|---|---|
| `automation.started` | `info` | Uma execução começa | `kind`, `dry_run` |
| `automation.progress` | `info` | Progresso em nível de passo | contadores — `jobs_found`, `jobs_analyzed` |
| `automation.stopped` | `warning` | O botão de parada teve efeito | `reason` |
| `automation.error` | `error` | Uma execução falhou | `error`, `error_type` |
| `automation.blocked` | `error` | **Verificação de segurança detectada — tudo parou** | `blocked_reason` |
| `job.found` | `info` | Um anúncio foi descoberto | `title`, `company` |
| `job.analyzed` | `info` | A pontuação terminou | `score`, `recommend_apply`, `missing_requirements` |
| `application.started` | `info` | O modal de Candidatura Simplificada abriu | `total_steps` |
| `application.awaiting_review` | `success` | **Preenchida e esperando por você** | `needs_human_input`, `questions_flagged` |
| `application.completed` | `success` | Enviada após a sua aprovação | `was_dry_run` |
| `session.status` | `info` | Navegador aberto/fechado, estado de login do LinkedIn mudou | `browser_open`, `logged_in` |
| `log` | qualquer | Uma linha de log para o feed de atividade | livre |

`application.awaiting_review` e `automation.blocked` são os dois que a UI deveria tornar impossíveis de perder:
o primeiro é o momento em que você é necessário, o segundo o momento em que tudo parou.

---

## Uma sessão completa, do início ao fim

```bash
BASE=http://localhost:8000/api

# 1. Log in
TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"..."}' | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"

# 2. Open the browser, then log into LinkedIn by hand in the window
curl -s -X POST $BASE/automation/session/start -H "$AUTH" | jq
curl -s $BASE/automation/session -H "$AUTH" | jq .logged_in   # wait for true

# 3. Save a search and run it
SEARCH=$(curl -s -X POST $BASE/searches -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"Remote Python","keywords":"senior python engineer","remote_filter":"remote","max_results":25}' \
  | jq -r .id)
curl -s -X POST $BASE/automation/search -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"search_id\": $SEARCH, \"analyze\": true}" | jq .id

# 4. Look at what scored well
curl -s "$BASE/jobs?status=analyzed&min_score=80" -H "$AUTH" | jq '.items[] | {id, title, score}'

# 5. Preview, then prepare — always in that order
curl -s -X POST $BASE/automation/preview -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"job_ids":[42,43]}' | jq
curl -s -X POST $BASE/automation/prepare -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"job_ids":[42,43],"confirmed":true}' | jq .id

# 6. Read the draft in full — letter and every answer
curl -s $BASE/applications/7 -H "$AUTH" | jq '{cover_letter, screening_answers}'

# 7. Fix anything that is wrong
curl -s -X PATCH $BASE/applications/7 -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"cover_letter":"My edited letter..."}' | jq .status

# 8. Approve this one application
curl -s -X POST $BASE/applications/7/submit -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"confirm":true}' | jq '{status, submitted_at, was_dry_run}'

# Kill switch, at any point
curl -s -X POST $BASE/automation/stop -H "$AUTH" | jq
```

Note que os passos 5 a 8 não podem ser colapsados. A pré-visualização precede a preparação, a preparação para na revisão, e o
envio recebe um id e um `confirm` explícito. Essa separação é o produto.
