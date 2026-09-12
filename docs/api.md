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
  "skills": ["Arquitetura de software", "Liderança técnica"],
  "technologies": [".NET 8", "React", "Python", "APIs REST"],
  "experiences": [
    {
      "key": "globalthings-tech-lead",
      "company": "Globalthings",
      "role": "Tech Lead",
      "start": "2023-02",
      "end": null,
      "location": "Recife, PE",
      "summary": "Lidera a plataforma de gestão de acessos.",
      "technologies": [".NET 8", "SQL Server"],
      "highlights": [
        { "text": "Reescreveu o serviço de autorização em .NET 8.",
          "technologies": [".NET 8", "APIs REST"],
          "impact": "p95 de 420 ms para 120 ms" }
      ],
      "projects": [],
      "focus": []
    }
  ],
  "projects": [],
  "education": [],
  "certifications": ["AZ-204 — Azure Developer Associate"],
  "preferred_languages": ["pt-BR", "en"],
  "answer_bank": { "salary_expectation": "R$ 15.000", "notice_period": "30 days" },
  "updated_at": "2026-08-11T12:00:00+00:00"
}
```

Este é o **currículo principal**. `skills` são competências e `technologies` são ferramentas — uma vaga pede as duas
em frases diferentes e as pesa de forma diferente. Cada `highlights[]` carrega as tecnologias que aquela realização
envolveu de verdade: é isso que permite a uma candidatura de .NET abrir a mesma experiência com uma frase e a uma de
React abrir com outra, sem inventar nenhuma das duas. `key` é a identidade da experiência entre versões e é atribuída
pelo servidor — não a invente no cliente.

Editar o principal muda o que as **próximas** candidaturas vão derivar. Candidaturas que já têm a sua versão
continuam intocadas: veja `GET /api/applications/{id}/resume`.

### `PUT /api/profile`

`ProfileUpdate` — todo campo opcional; campos omitidos ficam intocados.

| Campo | Restrição |
|---|---|
| `headline` | ≤ 300 caracteres |
| `location` | ≤ 200 caracteres |
| `phone` | ≤ 50 caracteres |
| `years_of_experience` | 0–70 |
| `summary`, `resume_text` | texto livre |
| `skills`, `technologies`, `certifications`, `preferred_languages` | arrays de strings — substituídos por inteiro, não mesclados |
| `experiences`, `projects`, `education` | arrays estruturados — substituídos por inteiro, validados na entrada |
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

### `POST /api/profile/intake`

`multipart/form-data` com um campo `file` opcional. **Nada do perfil é escrito aqui.**

Com um arquivo, ele é armazenado (é esse PDF que vai anexado às candidaturas) e lido. Sem arquivo, o
`resume_text` que já está no perfil é lido no lugar.

→ `ResumeIntakeRead` — uma **proposta**:

```json
{
  "full_name": "João Victor Uchôa",
  "headline": "Desenvolvedor Full Stack",
  "location": "Recife, PE",
  "email": "joao@example.com",
  "phone": "+55 81 99999-1234",
  "summary": "...",
  "skills": ["C#", ".NET", "React"],
  "languages": ["Português (nativo)", "Inglês (avançado)"],
  "experiences": [
    {
      "role": "Desenvolvedor Full Stack",
      "company": "GlobalThings",
      "started_on": "2023-01-01", "ended_on": null, "is_current": true,
      "period_text": "Jan 2023 - Presente",
      "responsibilities": ["Construí APIs REST em .NET 8."],
      "technologies": [".NET", "React"],
      "is_complete": true
    }
  ],
  "education": [{ "degree": "Bacharelado em Ciência da Computação",
                  "institution": "CESAR School", "period_text": "2020 — 2024" }],
  "projects": [], "certifications": [],
  "warnings": [],
  "resume_text": "...", "resume_filename": "user_1_resume.pdf"
}
```

Duas propriedades valem mais que o formato. **Nada é inventado**: toda string devolvida é um trecho do
arquivo enviado, o que é verificado estruturalmente nos testes — uma vaga que pede Kubernetes não faz
Kubernetes aparecer num currículo que nunca o citou. E **nada é escondido**: um layout que o leitor não
reconheceu volta em `warnings`, nunca como uma lista vazia. `is_complete: false` marca a experiência cujo
cargo ou empresa o layout ocultou; ela vem em branco para o usuário preencher, jamais adivinhada.

Determinístico e offline — este endpoint se comporta igual num deploy sem chave de IA.

### `POST /api/profile/intake/apply`

`IntakeApply` — a proposta como o usuário a corrigiu. Só o que está no corpo é escrito.

| Campo | Efeito |
|---|---|
| `headline`, `location`, `phone`, `summary`, `years_of_experience`, `resume_text` | gravados no perfil; campos omitidos ficam intocados |
| `skills`, `preferred_languages` | arrays de strings — substituídos por inteiro |
| `full_name` | gravado na conta **apenas** quando ela ainda não tem nome |
| `experiences` | `ExperienceCreate[]` — a mesma validação da tela de perfil; **acrescentadas**, não mescladas |
| `replace_experiences` | destrutivo e opcional: remove as experiências desta conta antes de acrescentar |

→ `IntakeApplied` com o `ProfileRead` atualizado, `experiences_created` e `experiences_removed`.

---

## Preferências de vaga

Que tipo de vaga a conta procura. Alimenta três coisas: a busca, a triagem antes da pontuação e quais das
tecnologias que o candidato **já tem** ganham destaque.

### `GET /api/preferences`

→ `JobPreferencesRead`:

```json
{
  "target_role": "Full Stack Developer",
  "alternative_roles": ["Backend Developer"],
  "seniority": ["entry", "associate"],
  "work_models": ["remote", "hybrid"],
  "locations": ["Recife, PE"],
  "salary_min": 5000, "salary_currency": "BRL",
  "priority_technologies": ["C#", ".NET", "React"],
  "excluded_terms": ["call center", "vendas"],
  "updated_at": "2026-09-10T12:00:00+00:00"
}
```

Vazio na primeira leitura, e vazio é um estado com significado: **nada declarado não descarta nada.**

### `PUT /api/preferences`

`JobPreferencesUpdate` — todo campo opcional; campos omitidos ficam intocados.

| Campo | Restrição |
|---|---|
| `target_role` | ≤ 200 caracteres. É ele que puxa a busca |
| `alternative_roles`, `locations` | até 5 itens, aparados e sem repetições |
| `seniority` | `internship`, `entry`, `associate`, `mid-senior`, `director`, `executive` |
| `work_models` | `remote`, `hybrid`, `on-site` |
| `salary_min` | 0–10.000.000, em unidades inteiras da moeda |
| `priority_technologies`, `excluded_terms` | até 40 itens |

Um valor fora do vocabulário é recusado com 422 em vez de virar uma busca que não casa com nada.

**Salvar também mantém uma busca gerenciada em dia.** Informar o cargo cria (ou reescreve) a busca salva
`Minhas vagas`, para que uma conta nova tenha algo a rodar sem abrir o formulário de busca. Sem cargo, nenhuma
busca é criada — palavras-chave vazias varreriam tudo. Ela é reescrita a cada salvamento, então não é lugar
para edições à mão; renomeá-la é como o usuário a assume.

**A triagem roda antes da pontuação.** Um anúncio que bate num termo excluído vai para `SKIPPED` com um
`skip_reason` que cita a palavra do próprio usuário, **sem gastar uma chamada de modelo**. A comparação é
com o título, o local e o modelo de trabalho — nunca com a descrição, porque "call center" num parágrafo
sobre os clientes da empresa não faz de uma vaga backend um call center. Um anúncio que não declara o modelo
de trabalho nunca conta como incompatível.

---

## Currículo por candidatura

Um currículo principal, e uma cópia própria por candidatura. A derivação é **determinística e offline**
(`app.domain.resume`) — estes endpoints se comportam igual num deploy sem chave de IA.

### `GET /api/resumes/master`

→ `MasterResumeRead` — o texto e as competências do perfil mais as posições estruturadas, com o
`fingerprint` contra o qual toda cópia decide se está desatualizada.

### `GET /api/resumes/versions`

→ `ResumeVersionSummary[]`, mais recente primeiro. Só metadados: a vaga a que cada cópia foi adaptada, a
aderência e se foi editada à mão. Ler uma versão é abrir a candidatura dela.

### `POST /api/resumes/applications/{application_id}`

Adapta (ou readapta) o currículo desta candidatura. Substitui **só** a cópia desta candidatura e
incrementa a `version`. Nenhuma outra cópia e nenhuma parte do currículo principal é tocada — é isso que
torna "adaptar de novo" seguro de apertar.

`412` quando o currículo principal está vazio: não há nada a reorganizar, e um documento vazio seria uma
resposta pior do que pedir que você preencha a sua experiência primeiro.

### `GET /api/resumes/applications/{application_id}`

→ `ApplicationResumeRead`, ou `404` quando nenhuma cópia foi derivada ainda — que é um estado normal, não
uma falha: candidaturas criadas antes desta funcionalidade não têm um snapshot honesto, e a tela de
revisão oferece a ação.

Além do documento e do relatório de mudanças, traz a **comparação com o currículo principal**:

```json
{
  "comparison": {
    "moves": [
      { "experience_id": 3, "company": "Initech", "role": "Backend Developer",
        "from_position": 3, "to_position": 1,
        "promoted_bullets": 2, "matched_terms": [".NET", "React"] }
    ],
    "highlighted_technologies": [".NET", "React"],
    "promoted_bullets": 2,
    "invented": [],
    "experiences_reordered": 2,
    "sections_adjusted": 1,
    "changes_total": 5,
    "is_clean": true,
    "is_comparable": true
  }
}
```

O que vale ler aqui é **o tamanho** das mudanças, não o fato de haver mudanças: uma cópia que se lê como
outro documento é uma cópia que o candidato não consegue defender numa entrevista.

- Posições são 1-based — "3ª → 1ª" é como se lê, e ninguém conta o próprio currículo a partir de zero
- `invented` é **medido**, não prometido: o guarda contra invenção roda sobre o documento inteiro, não só
  sobre a lista de tecnologias, porque uma ferramenta inventada dentro de um item é a que um empregador
  de fato lê. Lista vazia é um resultado; qualquer coisa nela é motivo para parar e conferir
- `is_comparable: false` quando a cópia está desatualizada: o principal mudou depois, e o diff atribuiria
  as edições do próprio usuário à adaptação

### `GET /api/resumes/applications/{application_id}/pdf`

→ `application/pdf`, como anexo. **São exatamente os bytes que o formulário envia.**

Desenhado a partir da cópia armazenada a cada chamada, não servido de um arquivo em cache: a cópia é a
fonte de verdade, e um PDF gravado antes da sua última edição entregaria um documento que não é o que
está na sua tela.

`412` quando não há nada honesto a desenhar — a candidatura ainda não tem cópia, ou o desenho falhou. É
a mesma condição em que a automação volta a anexar o PDF do perfil: **uma candidatura nunca é bloqueada
por um gerador de PDF.**

Importa mais no canal externo, onde o app não envia nada por você e o documento precisa conseguir sair
daqui.

### `PATCH /api/resumes/applications/{application_id}`

Edita esta cópia, e só esta. Cargo, empresa e período **não** estão no corpo aceito: esta tela adapta um
currículo, não inventa um histórico. `experiences` é posicional e precisa bater com o tamanho
armazenado — um editor construído contra uma derivação antiga moveria os itens de um emprego para outro.

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
  "ai_provider": null, "ai_key_set": false,
  "ai_model": null, "cover_letter_tone": "profissional",
  "content_language": "job", "generate_cover_letter": true
}
```

`ai_key_set` é tudo o que se pode saber sobre a chave guardada. Ela nunca é devolvida, nem mascarada — um
prefixo e um comprimento também vazam.

### `PUT /api/settings`

`UserSettingsUpdate` — todos os campos opcionais. Regras entre campos são impostas e retornam `422` quando quebradas:
`action_delay_min ≤ action_delay_max`, `apply_delay_min ≤ apply_delay_max` e
`working_hour_start < working_hour_end`.

`ai_api_key` é só de escrita: enviar guarda (criptografada), enviar `""` apaga, omitir mantém. `ai_provider`
aceita apenas os nomes de `GET /api/settings/ai/providers`; limpá-lo apaga a chave junto. Escolher um provedor
sem chave, ou trocar de provedor sem mandar a chave nova na mesma requisição, retorna `422` dizendo qual é o
problema.

→ `UserSettingsRead`.

### `GET /api/settings/ai/providers`

Os provedores que uma conta pode escolher, e onde tirar chave de cada um.

```json
[{ "name": "groq", "key_url": "Create a free key at https://console.groq.com/keys" }]
```

Provedores locais (`ollama`, `llamacpp`) e endpoints customizados não aparecem: numa instalação hospedada
`localhost` é o servidor, e uma URL escolhida pelo usuário é uma requisição que o servidor faria por ele.

### `POST /api/settings/ai/test`

Manda uma chamada mínima com essas credenciais e conta o que aconteceu. **Nada é gravado** — testar e salvar são
atos separados. Limitado à mesma taxa das rotas de autenticação.

```json
{ "provider": "groq", "api_key": "gsk-..." }
```

`api_key` vazia testa a que já está guardada (a UI não consegue relê-la para reenviar).

→ `AICredentialResult`:

```json
{ "ok": true, "provider": "groq", "model": "llama-3.3-70b-versatile", "detail": "" }
```

Uma chave recusada é `200` com `ok: false` e `detail` nas palavras do próprio provedor — "invalid api key",
"model not found" e "quota exceeded" são três correções diferentes.

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

#### `recommendation`

Cada item desta listagem — e só desta e da página de uma vaga, que são as duas telas onde a pergunta
é "vale a pena me candidatar?" — carrega também:

```json
{
  "verdict": "strong",
  "score": 87,
  "covered": ["PostgreSQL", "Python", "FastAPI"],
  "missing": ["Kubernetes"],
  "prioritized": ["PostgreSQL"],
  "covered_total": 3, "asked_total": 4, "coverage_pct": 75,
  "has_evidence": true
}
```

Diferente de `score_reasons`, **nada aqui vem do modelo**: as duas listas são a interseção do título e
da descrição do anúncio com o texto do seu currículo, que é exatamente a mesma interseção que monta o
currículo adaptado — um termo que aparece em `covered` é um termo que ganha destaque lá.

- `covered` usa a **sua** grafia; `missing` usa a **do anúncio**, porque uma tecnologia que você nunca
  escreveu não tem grafia sua
- Grafias equivalentes contam como a mesma coisa: um anúncio pedindo `postgres` contra um currículo
  dizendo `PostgreSQL` **não** é uma lacuna. Só sinônimos exatos — `java` e `javascript` continuam
  sendo duas tecnologias, e esconder uma lacuna real para parecer generoso seria pior que apontá-la
- `prioritized` é o subconjunto de `covered` que você marcou como prioridade. Nunca um acréscimo:
  uma prioridade que o anúncio não pede não aparece
- `has_evidence: false` quer dizer que o anúncio não citou nada comparável — não que você não atende
  a nada
- Nulo para um anúncio cuja descrição ainda não foi buscada

Nenhuma frase vem daqui: a API manda termos e contagens, e o texto é montado no frontend.

### `GET /api/jobs/{id}`

→ `JobDetail` — `JobRead` mais a `description` completa. Também traz `recommendation`.

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

### `GET /api/applications/{id}/resume`

O currículo que **esta candidatura** apresenta, junto com o principal de onde ele saiu.

→ `ApplicationResumeRead`:

```json
{
  "application_id": 12,
  "job_id": 34,
  "job_title": "Desenvolvedor Backend .NET Sênior",
  "job_company": "Contoso",
  "document":      { "...": "o currículo desta candidatura" },
  "base_document": { "...": "o principal como estava quando esta versão foi gerada" },
  "focus": [".NET 8", "APIs REST", "SQL Server"],
  "changes": [
    { "section": "Experiência — Globalthings", "action": "rephrased",
      "detail": "Descrição reescrita para destacar .NET 8 e APIs REST." }
  ],
  "invention_flags": [],
  "source": "rules",
  "is_stale": false,
  "markdown": "# Tech Lead\n\n…",
  "created_at": "2026-09-07T10:00:00+00:00",
  "updated_at": "2026-09-07T10:05:00+00:00"
}
```

`404` quando a candidatura ainda não tem versão própria — conta nova com currículo principal vazio, ou candidatura
preparada antes desta funcionalidade existir. Nos dois casos, um `POST` resolve.

`focus` são os **seus próprios** termos que esta vaga pediu, do mais forte para o mais fraco. A interseção é sempre
com o seu vocabulário: uma vaga que exige Rust de quem nunca escreveu Rust não produz Rust em lugar nenhum.

`base_document` é o instantâneo do principal no momento da geração. Ele viaja junto para a interface conseguir
mostrar a diferença sem uma segunda chamada — e é o que prova que editar o principal depois não alcança esta
candidatura. `is_stale` fica `true` quando o principal mudou desde então; a versão em si não muda.

### `POST /api/applications/{id}/resume`

Gera (ou regera) a versão desta candidatura a partir do currículo principal como ele está agora. Determinístico,
sem chamada de modelo: só reordena, recolhe e reescreve o que já está no principal.

Regerar é também o caminho de volta ao principal — descarta as edições **desta** versão e recomeça. Não toca em
nenhuma outra candidatura e nunca toca no principal.

`412` quando o currículo principal não tem experiências, competências nem tecnologias: não há o que priorizar.

### `PATCH /api/applications/{id}/resume`

`ApplicationResumeUpdate` — o documento inteiro:

```json
{ "document": { "...": "o currículo desta candidatura, editado" } }
```

Salva as suas edições nesta candidatura. O principal fica intocado, e nenhuma outra candidatura muda.

`422` quando a edição muda a identidade de uma experiência (empresa, cargo ou período) ou introduz uma que o
principal não tem: uma versão reenfatiza o passado, não o reescreve. Corrija o fato no principal e regere.

Toda edição salva passa pelo guarda de invenção: tecnologia presente na versão e ausente do principal volta em
`invention_flags` — sinalizada, nunca removida. Registra um evento `resume_tailored`.

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
`form_step_completed`, `form_changed`, `question_answered`, `resume_uploaded`, `resume_tailored`,
`awaiting_review`, `user_edited`, `user_approved`, `submitted`, `outcome_changed`, `discarded`, `error`.

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
{
  "configured": true, "model": "llama-3.3-70b-versatile",
  "provider": "groq", "source": "account", "detail": ""
}
```

Responde **por conta**, não por deployment: uma conta com chave própria tem IA num servidor que não configurou
nenhuma, e uma conta cuja chave parou de descriptografar não tem num servidor onde todo mundo tem. `source` diz
com a chave de quem — `account` ou `deployment`.

`configured: false` traz o motivo em `detail`. A busca e o preenchimento de formulários continuam funcionando;
pontuação, cartas de apresentação e sugestões de resposta não.

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

## Administração

Toda a área abaixo exige uma conta com `is_admin`. A autorização está no router
(`get_current_admin`), não em cada endpoint: uma conta comum recebe **403** em qualquer
caminho `/api/admin/*`, venha o pedido do painel ou de um `curl`. O papel só é concedido
por `python scripts/create_admin.py` — nenhuma requisição escreve `users.is_admin`.

Nada aqui devolve currículo, carta de apresentação, resposta de triagem, sessão do
LinkedIn ou hash de senha: os schemas em `backend/app/schemas/admin.py` não têm campo
para isso. São agregados e contadores.

### Período

Cinco endpoints aceitam o mesmo filtro:

| Parâmetro | Valores |
| --- | --- |
| `period` | `today`, `7d`, `30d`, `90d`, `custom` (padrão: `7d`) |
| `start`, `end` | obrigatórios com `custom`, datas ISO (`YYYY-MM-DD`), `end` inclusivo |

A comparação ("vs. período anterior") é sempre uma janela de **igual duração imediatamente
anterior**, nunca o mês ou a semana do calendário — em `today`, ontem até a mesma hora.
`custom` sem as duas datas, invertido ou maior que 366 dias responde **422**.

### `GET /api/admin/overview`

A tela inteira do painel em uma resposta: um pedido em vez de nove, para que todos os
números venham do mesmo instante. O resultado é memoizado por ~30 s por janela;
`refresh=true` recalcula (é o que o botão "Atualizar dados" envia).

→ `AdminOverview` (abreviado):

```json
{
  "period": { "period": "7d", "start": "...", "end": "...", "previous_start": "...", "days": 7 },
  "generated_at": "2026-09-12T14:30:00Z",
  "headline": [
    { "key": "users", "value": 1248, "unit": "count", "previous": 1093,
      "delta_pct": 0.142, "trend": "up", "has_data": true }
  ],
  "operational": [{ "key": "awaiting_review", "value": 2, "unit": "count" }],
  "product": [{ "key": "submit_rate", "value": 0.62, "unit": "percent" }],
  "funnel": [{ "key": "jobs_found", "count": 128, "conversion_from_previous": null }],
  "growth": [{ "date": "2026-09-12", "users": 1, "jobs": 14, "applications": 3 }],
  "automation": { "status": "healthy", "next_run_at": null, "scheduling": "on_demand" },
  "ai": { "status": "healthy", "provider": "anthropic", "cost_usd": null },
  "health": { "status": "healthy", "services": [{ "service": "database", "status": "online" }] },
  "alerts": [],
  "usage": [{ "user_id": 3, "applications": 12 }],
  "errors": [{ "id": "automation:12", "source": "automation", "summary": "..." }],
  "activity": [{ "id": "user:9", "kind": "user_registered", "summary": "Novo usuário (a***@x.com)" }]
}
```

Três detalhes que são decisões, não lacunas:

- **`delta_pct` muda de significado com `unit`.** Para `count` é variação relativa
  (`(novo - antigo) / antigo`); para `percent` é a diferença em **pontos percentuais**.
  Reportar a variação relativa de uma taxa transforma "de 54% para 62%" num elogioso
  "+14,8%".
- **`has_data: false`** significa "nada registrado", não zero. Uma instalação nova mostra
  "sem dados" em vez de uma taxa de sucesso de 0%.
- **`automation.next_run_at` é sempre `null`.** Nada agenda execuções — cada uma é
  iniciada por um usuário, que é a garantia do modo assistido. `scheduling` diz isso.

O primeiro acesso de cada administrador no dia grava um `AuditEvent` com ação
`admin_access`; recarregar a página não grava outro.

### `GET /api/admin/users`

Parâmetros: o filtro de período, mais `search` (e-mail ou nome), `filter`
(`all` | `active` | `inactive` | `new` | `with_applications` | `without_applications`),
`limit` (≤ 100) e `offset`.

→ `Page<AdminUserRow>` — contato, status, datas e os contadores vitalícios de vagas,
candidaturas e envios. O período só afeta o filtro `new`.

### `GET /api/admin/jobs`

→ `JobInsights`: volumes, nota média, parcela com candidatura simplificada e os
principais cargos, empresas, localidades, origens e tecnologias.

`top_technologies` é o único campo que lê texto em vez de agregar: é extraído das vagas
com o vocabulário de `app/domain/technologies.py`, limitado às 300 mais recentes da
janela. `technologies_sampled` informa quantas foram lidas — é amostra, não censo.

### `GET /api/admin/errors`

Falhas recentes das três fontes (execuções da automação, chamadas de IA e o histórico das
candidaturas), mescladas e ordenadas da mais recente. `limit` ≤ 100.

`summary` é a primeira linha da mensagem, truncada. Stack traces vão para os logs com
`exc_info` e nunca chegam a uma coluna, então não há nenhum aqui para vazar.

### `GET /api/admin/activity`

Linha do tempo dos eventos relevantes: cadastros, execuções encerradas e marcos das
candidaturas. E-mails de cadastros aparecem mascarados (`a***@exemplo.com`).

### `GET /api/admin/health`

Status por serviço (`api`, `database`, `ai`, `automation`, `queue`, `frontend`) para o
operador. Distinto de `GET /api/health`, que continua sendo a sonda pública de liveness —
esta consulta o banco e reporta o provider de IA, o que um endpoint aberto não deveria
carregar.

### `GET /api/admin/audit`

Os acessos administrativos registrados, do mais recente. Mesmo formato de
`GET /api/users/me/audit`.

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
