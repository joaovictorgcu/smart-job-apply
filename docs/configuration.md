# Configuração

Há duas camadas de configuração, e elas respondem perguntas diferentes.

| Camada | Onde vive | Escopo | Alterada por |
|---|---|---|---|
| **Settings** | arquivo `.env` ou variáveis de ambiente | Por processo | Editando `.env` e reiniciando |
| **UserSettings** | tabela `user_settings` no banco de dados | Por usuário | A página de Configurações, ou `PUT /api/settings` |

Settings são preocupações de implantação: chaves, URL do banco, se o navegador é visível. UserSettings são
preocupações de operação: quantas candidaturas por dia, quanto esperar entre ações, se o modo de teste está ligado.
Várias configurações `DEFAULT_*` semeiam a linha de UserSettings de um novo usuário; depois disso, os valores por usuário vencem.

---

## Variáveis de ambiente (`Settings`)

Definidas em [`backend/app/config.py`](../backend/app/config.py). O nome da variável de ambiente é o nome do campo em
maiúsculas — não há prefixo. Tanto `<raiz do repo>/.env` quanto `backend/.env` são lidos, e variáveis de
ambiente reais têm precedência sobre ambos.

### Aplicação

| Variável | Tipo | Padrão | O que faz |
|---|---|---|---|
| `APP_NAME` | string | `Smart Job Apply` | Nome de exibição usado no título da API. |
| `ENVIRONMENT` | string | `development` | Rótulo livre para a implantação (`development`, `production`). |
| `DEBUG` | bool | `false` | Liga o echo de statements do SQLAlchemy. Deixe desligado fora de depuração local — statements podem conter os seus dados. |

### Segurança

| Variável | Tipo | Padrão | O que faz |
|---|---|---|---|
| `SECRET_KEY` | string | aleatório por processo | Assina os JWTs. **Defina isto explicitamente.** Com o padrão, uma nova chave aleatória é gerada a cada início, então todo login é invalidado por um reinício. |
| `ENCRYPTION_KEY` | string | recorre a `SECRET_KEY` | Material de origem para a chave Fernet derivada por HKDF que criptografa os cookies de sessão do LinkedIn em repouso. **Mudá-la torna as sessões já armazenadas permanentemente ilegíveis** — a correção é reconectar o LinkedIn, mas você terá que fazer. |
| `JWT_ALGORITHM` | string | `HS256` | Algoritmo de assinatura dos JWTs. Não há motivo para mudar. |
| `ACCESS_TOKEN_TTL_MINUTES` | int | `720` (12 h) | Tempo de vida do access token. Mais curto significa mais relogins; mais longo significa que um token roubado é útil por mais tempo. |

Gere ambas as chaves com:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### IA

| Variável | Tipo | Padrão | O que faz |
|---|---|---|---|
| `AI_PROVIDER` | string | `""` | Quem responde. Vazio decide sozinho: `anthropic` quando `ANTHROPIC_API_KEY` está definida, senão `stub`. Valores: `ollama`, `llamacpp`, `groq`, `gemini`, `openrouter`, `cerebras`, `openai_compat`, `anthropic`, `stub`. Um nome desconhecido levanta `ProviderNotConfiguredError` nomeando as alternativas — nunca é lido como "IA desligada". |
| `AI_API_KEY` | string | `""` | Credencial dos provedores compatíveis com OpenAI. Não usada por `ollama`, `llamacpp`, `stub` nem `anthropic`. |
| `AI_BASE_URL` | string | do provedor | Sobrescreve o endpoint do provedor. Obrigatório para `openai_compat`. |
| `AI_MODEL` | string | do provedor | Sobrescreve o modelo. Obrigatório para `openai_compat`. |
| `AI_STUB_SCORE` | int \| null | `null` | Fixa a nota do provedor offline, para testes que precisam de um lado específico de um limiar. Ignorado pelos outros. |
| `ANTHROPIC_API_KEY` | string | `""` | Chave da Anthropic, usada por `AI_PROVIDER=anthropic`. |
| `ANTHROPIC_MODEL` | string | `claude-opus-5` | O modelo usado quando o provedor é `anthropic`. |
| `SCORING_EFFORT` | string | `low` | Esforço de raciocínio para pontuação em massa, em que muitas vagas são avaliadas e o custo domina. A geração de cartas de apresentação usa `high` de qualquer forma. Valores válidos são `low`, `medium`, `high`, `xhigh`, `max`. Nos provedores compatíveis com OpenAI é mapeado para a temperatura de amostragem. |

Um usuário pode sobrescrever o modelo para a própria conta com `UserSettings.ai_model`; quando isso é nulo, o modelo do provedor se aplica.

**`Settings.ai_enabled` agora depende do provedor resolvido**, não só da chave da Anthropic: `stub`, `ollama` e
`llamacpp` não precisam de nada, os hospedados precisam de `AI_API_KEY`, e `anthropic` precisa de
`ANTHROPIC_API_KEY`. Um clone novo sem nenhuma configuração resolve para `stub` e roda de ponta a ponta — o
provedor offline rotula a própria saída como um placeholder, então ninguém confunde com uma avaliação real.

**Saída estruturada.** Cada capacidade valida a resposta contra um schema Pydantic. Os servidores compatíveis com
OpenAI param de suportar isso em pontos diferentes, então
[`openai_compat.py`](../backend/app/ai/providers/openai_compat.py) desce por três modos e lembra até onde aquele
servidor chegou: `response_format: json_schema` (estrito), depois `json_object` com o schema no prompt do
sistema, depois texto puro com o JSON extraído da resposta. Uma resposta que ainda não valida é reportada como
recusa, não levantada — é essa invariante que faz o usuário receber o fallback manual em vez de uma tela de erro.

**Privacidade.** Currículos e respostas de triagem são dados pessoais. `ollama` é a recomendação por isso: um
modelo local não manda nada para fora. Os tiers grátis hospedados são uma conveniência, e os termos deles —
inclusive se os prompts são usados para treinamento — são uma decisão sua.

### Banco de dados

| Variável | Tipo | Padrão | O que faz |
|---|---|---|---|
| `DATABASE_URL` | string | `""` | Vazio significa SQLite em `<DATA_DIR>/app.db` (modo WAL). Defina como uma URL async completa para trocar de backend — para PostgreSQL, `postgresql+asyncpg://user:pass@host:5432/dbname`, que precisa do extra `postgres` instalado. |

O driver precisa ser async: `sqlite+aiosqlite://…` ou `postgresql+asyncpg://…`. Uma URL síncrona como
`postgresql://…` vai falhar na criação do engine.

### Automação

| Variável | Tipo | Padrão | O que faz |
|---|---|---|---|
| `HEADLESS` | bool | `false` | Se o Chromium roda sem janela. Mantenha `false`: você precisa ver o navegador para fazer login no LinkedIn, e um navegador visível é como você percebe que algo está dando errado. No Docker o navegador roda dentro de um display virtual que você acessa por noVNC, então `false` ainda é o correto lá. |
| `DEMO_PORTAL` | bool | `false` | Serve o portal de vagas falso embutido ([`demo_portal.py`](../backend/app/automation/demo_portal.py)) em vez do site real, para que o fluxo inteiro seja demonstrável sem uma conta do LinkedIn e sem candidatura nenhuma sair da máquina. Ligado, o app é uma demo de si mesmo e não se candidata a nada real; a sessão do navegador registra um `WARNING` dizendo exatamente isso. `make demo` liga por você junto com o provedor offline. |
| `MAX_CONCURRENT_SESSIONS` | int | `1` | Sessões de navegador permitidas ao mesmo tempo. |
| `ASSISTED_MODE_ONLY` | bool | `true` | A garantia rígida de que nada é enviado sem uma ação explícita, separada e confirmada pelo usuário. |
| `DEFAULT_DAILY_CAP` | int | `15` | Semeia `UserSettings.daily_cap`. |
| `DEFAULT_MIN_SCORE` | int | `70` | Semeia `UserSettings.min_score`. |
| `DEFAULT_ACTION_DELAY_RANGE` | JSON `[float, float]` | `[2.5, 7.0]` | Semeia a faixa de atraso por ação, em segundos. |
| `DEFAULT_APPLY_DELAY_RANGE` | JSON `[float, float]` | `[45.0, 120.0]` | Semeia a faixa de atraso entre candidaturas, em segundos. |
| `DEFAULT_WORKING_HOURS` | JSON `[int, int]` | `[8, 20]` | Semeia a janela de horário, como horas locais. |

> **As três configurações de faixa precisam ser escritas como arrays JSON no `.env`.** `DEFAULT_ACTION_DELAY_RANGE=[3, 9]`
> funciona; `DEFAULT_ACTION_DELAY_RANGE=3,9` dispara `SettingsError: error parsing value for field
> "default_action_delay_range"` em tempo de import. O pydantic-settings decodifica campos complexos por JSON antes de qualquer
> validator rodar, então o helper de split por vírgula em `config.py` só se aplica a valores passados em código e
> testes. O mesmo vale para `CORS_ORIGINS`.

### Rede

| Variável | Tipo | Padrão | O que faz |
|---|---|---|---|
| `CORS_ORIGINS` | JSON `[string]` | `["http://localhost:5173", "http://127.0.0.1:5173"]` | Origens permitidas a chamar a API. Precisa ser um array JSON no `.env` — por exemplo `CORS_ORIGINS=["http://localhost:5173"]`. Adicione o seu endereço de LAN aqui se você abrir o painel de outra máquina. |
| `RATE_LIMIT_DEFAULT` | string | `120/minute` | Limite de taxa do slowapi para endpoints gerais. |
| `RATE_LIMIT_AUTH` | string | `10/minute` | Limite mais apertado nos endpoints de autenticação, para que `/api/auth/login` não possa sofrer força bruta. |

### Caminhos

| Variável | Tipo | Padrão | O que faz |
|---|---|---|---|
| `DATA_DIR` | path | `backend/data` | Raiz de tudo que o app escreve: `app.db`, `browser_profiles/`, `resumes/`, capturas de tela. Está no gitignore, e contém cookies de sessão vivos mais o seu currículo — trate como secreto e faça backup. |

### Um `.env` funcional

```dotenv
# --- Required ---
SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(48))">
ENCRYPTION_KEY=<a second, different value from the same command>

# --- AI: pick one ---
AI_PROVIDER=ollama                  # local, no key, nothing leaves the machine
# AI_PROVIDER=groq
# AI_API_KEY=gsk_...
# AI_PROVIDER=anthropic
# ANTHROPIC_API_KEY=sk-ant-...

# --- Common ---
SCORING_EFFORT=low
DATABASE_URL=
HEADLESS=false
DEMO_PORTAL=false
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]

# --- Guard-rail seeds (per-user values override these once a user exists) ---
DEFAULT_DAILY_CAP=15
DEFAULT_MIN_SCORE=70
DEFAULT_ACTION_DELAY_RANGE=[2.5, 7.0]
DEFAULT_APPLY_DELAY_RANGE=[45.0, 120.0]
DEFAULT_WORKING_HOURS=[8, 20]
```

---

## Configurações por usuário (`UserSettings`)

Lidas com `GET /api/settings`, alteradas com `PUT /api/settings`. Os limites abaixo são impostos por
[`UserSettingsUpdate`](../backend/app/schemas/user.py); um valor fora deles é um `422`, não um recorte silencioso.

### Salvaguardas

Afrouxar estas é a única parte da configuração que carrega risco real, então cada linha diz o que você está
abrindo mão.

| Campo | Tipo | Padrão | Faixa | O que faz — e o risco de afrouxar |
|---|---|---|---|---|
| `daily_cap` | int | `15` | 1–50 | Máximo de candidaturas enviadas por dia. O teto rígido é 50 porque acima disso o volume deixa de parecer uma pessoa procurando emprego e passa a parecer um script. Aumentá-lo é a mudança mais propensa a chamar atenção para a sua conta. |
| `min_score` | int | `70` | 0–100 | Nota mínima de aderência da IA antes de uma vaga ficar elegível para candidatura. Baixá-la significa se candidatar a vagas com que você combina menos: mais ruído do lado do empregador, mais perguntas de triagem que a IA não consegue responder com confiança, e uma taxa de resposta pior. |
| `action_delay_min` | float | `2.5` | 0.5–60 | Limite inferior da pausa aleatória entre ações individuais de página. Abaixo de cerca de dois segundos, a temporização clique-a-clique é mais rápida que um humano lendo a página. |
| `action_delay_max` | float | `7.0` | 0.5–120 | Limite superior dessa pausa. Precisa ser ≥ `action_delay_min`. A *faixa* importa tanto quanto os valores: um atraso fixo é um fingerprint, um aleatório não é. |
| `apply_delay_min` | float | `45.0` | 5–600 | Limite inferior da pausa entre candidaturas inteiras. Defina como 5 s e quinze candidaturas caem em dois minutos — o padrão automatizado mais claro possível. |
| `apply_delay_max` | float | `120.0` | 5–1800 | Limite superior dessa pausa. Precisa ser ≥ `apply_delay_min`. |
| `working_hour_start` | int | `8` | 0–23 | Primeira hora local em que a automação vai agir. |
| `working_hour_end` | int | `20` | 1–24 | Última hora local. Precisa ser maior que `working_hour_start`. Abrir a janela para 0–24 produz atividade às 3 da manhã todo dia, o que nenhuma busca real de emprego parece. |
| `require_manual_approval` | bool | `true` | — | Exige aprovação explícita antes do envio. Junto com `ASSISTED_MODE_ONLY`, esta é a garantia de humano-no-circuito. Não desligue; nada no projeto precisa dela desligada. |
| `dry_run` | bool | `true` | — | Enquanto true, o engine executa o fluxo inteiro — buscar, pontuar, abrir o formulário, preencher, parar na revisão — e **nunca envia**. O único motivo para desligar é que você acompanhou alguns dry runs e está pronto para enviar candidaturas reais. Desligue deliberadamente, e ligue de novo quando terminar. |

### Preferências de IA

| Campo | Tipo | Padrão | O que faz |
|---|---|---|---|
| `ai_model` | string \| null | `null` | Sobrescreve `ANTHROPIC_MODEL` para este usuário. Nulo usa o valor do ambiente. Máx. 100 caracteres. |
| `cover_letter_tone` | string | `profissional` | Dica de tom passada ao prompt da carta de apresentação. Qualquer descritor curto funciona — `professional`, `direct`, `warm`. Máx. 50 caracteres. |
| `content_language` | string | `job` | `job` escreve a carta e as respostas no idioma detectado do anúncio. Fixe numa tag como `en` ou `pt-BR` para sempre usar aquele idioma. Máx. 20 caracteres. |
| `generate_cover_letter` | bool | `true` | Se deve gerar uma carta de apresentação durante a preparação. Desligue se preferir escrever a sua, ou para economizar tokens. |

> `cover_letter_tone` e `content_language` têm padrões que se leem como português
> (`profissional`, `pt-BR` dentro de `CoverLetter`). São strings livres passadas ao modelo, não
> enumerações — defina-os como quiser.

### Exemplo

```bash
curl -X PUT http://localhost:8000/api/settings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"daily_cap": 10, "min_score": 75, "content_language": "en", "dry_run": true}'
```

---

## Qual botão eu realmente quero?

| Objetivo | Mudança |
|---|---|
| Acompanhar o fluxo inteiro sem enviar nada | `dry_run: true` (o padrão) |
| Enviar candidaturas de verdade | `dry_run: false`, depois aprovar cada uma individualmente |
| Menos candidaturas, mais bem combinadas | Aumente `min_score`, baixe `daily_cap` |
| Parecer menos com um script | Alargue `action_delay_*` e `apply_delay_*`; estreite a janela de horário |
| Gastar menos com a API | `SCORING_EFFORT=low`, `generate_cover_letter: false`, baixe `Search.max_results` |
| Escrever candidaturas em inglês independentemente do anúncio | `content_language: "en"` |
| Sair do SQLite | `DATABASE_URL=postgresql+asyncpg://…` mais `pip install -e ".[postgres]"` |
| Parar de perder logins no reinício | Defina `SECRET_KEY` explicitamente |
