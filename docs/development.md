# Desenvolvimento

Como trabalhar neste código. Para colocá-lo para rodar, veja [installation.md](installation.md); para o
raciocínio por trás da estrutura, [architecture.md](architecture.md).

## Layout do projeto

```text
.
├── backend/
│   ├── alembic.ini             # Alembic config — migration commands run from backend/
│   ├── app/
│   │   ├── ai/
│   │   │   ├── client.py       # the Anthropic client wrapper
│   │   │   ├── scoring.py      # scoring orchestration
│   │   │   ├── prompts/        # scoring.py, cover_letter.py, screening.py
│   │   │   └── schemas.py      # JobScore, ScreeningAnswer, CoverLetter, JobAnalysis, AIUsage
│   │   ├── api/
│   │   │   ├── deps.py         # SessionDep, CurrentUser, LimitDep, OffsetDep, limiter
│   │   │   ├── errors.py       # exception handlers
│   │   │   └── routes/         # one module per resource, mounted under /api
│   │   ├── auth/
│   │   │   ├── crypto.py       # Fernet encrypt/decrypt for data at rest
│   │   │   ├── dependencies.py # get_current_user, get_current_user_ws
│   │   │   └── security.py     # bcrypt hashing, JWT issue/decode
│   │   ├── automation/
│   │   │   ├── contracts.py    # SearchFilters, JobPosting, ..., LinkedInService protocol
│   │   │   ├── errors.py       # the error hierarchy
│   │   │   ├── engine.py       # orchestration — imports no Playwright
│   │   │   ├── throttle.py     # delays, daily cap, working hours
│   │   │   ├── browser.py      # Playwright launch and lifecycle
│   │   │   ├── selectors.py    # EVERY CSS selector, in one file
│   │   │   └── linkedin/       # service.py, search.py, job.py, apply.py
│   │   ├── services/           # application, automation, job, search, stats, user
│   │   ├── database/
│   │   │   ├── base.py         # Base, TimestampMixin, UtcDateTime, utcnow()
│   │   │   └── session.py      # engine, get_session, session_scope, init_models
│   │   ├── models/             # SQLAlchemy ORM + lifecycle enums
│   │   ├── observability/
│   │   │   ├── audit.py        # record_event(), to_live_event()
│   │   │   ├── events.py       # EventName, Event, make_event
│   │   │   └── logger.py       # get_logger, bind_context, configure_logging
│   │   ├── schemas/            # Pydantic request/response models
│   │   ├── websocket/manager.py# the per-user broadcast singleton
│   │   ├── config.py           # Settings, get_settings()
│   │   └── main.py             # the FastAPI app
│   ├── migrations/             # env.py + versions/
│   ├── tests/                  # unit/ api/ automation/ integration/ fixtures/
│   └── data/                   # runtime state — gitignored
├── frontend/
│   └── src/
│       ├── components/         # AppShell, CheckpointBanner, KillSwitchButton, ...
│       ├── hooks/              # useApi, useAuth, useEvents
│       ├── lib/                # format, theme, utils
│       ├── pages/
│       ├── services/           # typed HTTP client — client.ts + one module per resource
│       └── types/              # api.ts, events.ts (mirrors the backend)
├── docker/                     # Dockerfile, entrypoint.sh, supervisord.conf
├── docs/
├── scripts/                    # setup.sh, setup.ps1, dev.sh, create_user.py
├── Makefile
├── docker-compose.yml
└── pyproject.toml
```

## Comandos

`make help` lista todos os alvos, e o cabeçalho do Makefile dá o equivalente em PowerShell de cada um para
Windows sem WSL. O comando bruto está na terceira coluna quando você precisar.

| Tarefa | Alvo | Comando bruto |
|---|---|---|
| Setup inicial | `make install` | `bash scripts/setup.sh` |
| Rodar os dois processos | `make dev` | `bash scripts/dev.sh` |
| Só o backend | `make dev-backend` | `.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend --port 8000` |
| Só o frontend | `make dev-frontend` | `cd frontend && npm run dev` |
| Testes | `make test` | `pytest` |
| Lint | `make lint` | `ruff check .` |
| Format + correções seguras | `make format` | `ruff format . && ruff check . --fix` |
| Tipos (backend) | `make typecheck` | `mypy backend/app` |
| Tipos (frontend) | — | `cd frontend && npm run typecheck` |
| Lint do frontend | — | `cd frontend && npm run lint` |
| Build de produção | `make build` | `cd frontend && npm run build` |
| Aplicar migrations | `make migrate` | `cd backend && alembic upgrade head` |
| Nova migration | `make migration m="add x"` | `cd backend && alembic revision --autogenerate -m "add x"` |
| Criar uma conta | `make user` | `python scripts/create_user.py` |
| Docker up / down / logs | `make docker-up` / `-down` / `-logs` | os mesmos comandos `docker compose` |
| Limpar caches e venv | `make clean` | — |

Seleções de teste mais estreitas:

```bash
pytest backend/tests/automation/test_kill_switch.py -v
pytest backend/tests/automation/test_engine_dry_run.py::test_dry_run_never_submits -v
pytest -k "checkpoint or kill_switch"
```

`make dev` respeita `BACKEND_PORT` e `FRONTEND_PORT`, e para os dois processos se qualquer um morrer — então um
backend que travou não fica escondido atrás de um servidor Vite ainda rodando.

## Estilo de código

Configurado em [`pyproject.toml`](../pyproject.toml) — leia em vez de adivinhar.

- **Ruff**, comprimento de linha 100, alvo `py311`, regras `E, F, I, UP, B, SIM, ASYNC`. `B008` é ignorada porque
  `Depends()` num argumento padrão é FastAPI idiomático. `src = ["backend"]` é o que faz o isort reconhecer
  `app` como first-party; sem isso todo import `from app...` é ordenado para o bloco third-party.
- **mypy** com o plugin do Pydantic, `ignore_missing_imports = true`. Não bloqueante na CI, porque a tipagem do Playwright
  e do SQLAlchemy produz ruído que não vale falhar um build. Não deixe isso virar uma
  desculpa para código sem tipos.
- **Código em inglês** — identificadores, comentários, docstrings, mensagens de log e mensagens de erro ficam em inglês. A
  **interface (UI) e a documentação são em português.** Não misture idiomas dentro de uma mesma camada.
- **Nunca `print()`.** Use o logger estruturado:

  ```python
  from app.observability import get_logger

  logger = get_logger(__name__)
  logger.info("Job scored", extra={"job_id": job.id, "action": "score", "status": "ok"})
  ```

  As chaves de `extra` viram campos JSON de nível superior. `bind_context(user_id=..., run_id=...)` anexa campos a cada
  linha emitida pela task atual, que é o que torna os logs de uma execução pesquisáveis com grep.
- **Comente o "porquê", não o "o quê".** Um comentário que reafirma a próxima linha é ruído; um comentário
  explicando por que `check_same_thread=False` é necessário, ou por que um validator é um model validator em vez de um
  field validator, ganha o seu lugar. O código existente é a referência para o registro.
- **Tipe tudo nas fronteiras.** Handlers de rota, funções de serviço e as dataclasses em
  `contracts.py` são totalmente tipadas. Helpers internos podem ser mais soltos.

## Adicionando uma rota

1. **Schema primeiro**, em `app/schemas/`. Os modelos de requisição e resposta são o contrato; escreva-os antes do
   handler. Reutilize `ORMModel` para qualquer coisa lida do ORM e `Page[T]` para listas.

2. **O handler**, em `app/api/routes/<resource>.py`. Use os aliases anotados de `app.api.deps` em vez
   de escrever `Depends(...)`; toda rota existente faz assim:

   ```python
   from app.api.deps import CurrentUser, LimitDep, OffsetDep, SessionDep
   from app.schemas.common import Page
   from app.schemas.widget import WidgetRead
   from app.services import widget_service

   router = APIRouter(prefix="/widgets", tags=["widgets"])


   @router.get("", response_model=Page[WidgetRead])
   async def list_widgets(
       user: CurrentUser,
       session: SessionDep,
       limit: LimitDep = 50,
       offset: OffsetDep = 0,
   ) -> Page[WidgetRead]:
       """One-line docstring — it becomes the OpenAPI summary."""
       widgets, total = await widget_service.list_widgets(
           session, user_id=user.id, limit=limit, offset=offset
       )
       return Page(
           items=[WidgetRead.model_validate(w) for w in widgets],
           total=total,
           limit=limit,
           offset=offset,
       )
   ```

   `LimitDep` e `OffsetDep` carregam os limites de paginação (1–200 e ≥ 0), então todo endpoint de lista os valida
   da mesma forma. Rotas com limite de taxa recebem `request: Request` e o decorador `@limiter.limit(...)` —
   veja `routes/auth.py`.

3. **Escope toda query ao usuário.** Filtre por `user_id` na própria query, e retorne `404` — não `403` —
   quando uma linha existe mas pertence a outra pessoa, para que os ids fiquem não enumeráveis.

4. **Registre o router** em `app/main.py` sob o prefixo `/api`.

5. **Documente** em [api.md](api.md) e, se o frontend a chamar, adicione a função do client e os tipos dela.

6. **Teste** — o caminho feliz, o caso não autenticado e o caso de usuário errado.

Lógica de negócio não pertence a handlers. Um handler valida a entrada, chama um serviço e molda a
resposta.

## Adicionando um serviço

Os serviços são donos da orquestração. Eles recebem uma sessão e entradas tipadas, e nunca tocam em tipos do FastAPI ou
do Playwright.

```python
async def prepare_application(
    session: AsyncSession,
    *,
    user: User,
    job: Job,
    linkedin: LinkedInService,
    ai: AIClient,
) -> Application: ...
```

Passar `LinkedInService` e `AIClient` como parâmetros — em vez de construí-los dentro — é o que
torna a função testável com fakes. Mantenha assim.

Todo passo significativo chama `record_event()` e publica o evento ao vivo:

```python
from app.observability.audit import record_event, to_live_event
from app.websocket.manager import manager

event = await record_event(
    session,
    application_id=application.id,
    event_type=ApplicationEventType.FORM_STEP_COMPLETED,
    message="Step 2 of 4 completed",
    payload={"step": 2, "total": 4},
    run_id=run.id,
    job_id=job.id,
    user_id=user.id,
)
if (live := to_live_event(event, job_id=job.id)) is not None:
    await manager.publish(user.id, live)
```

A trilha durável e o feed ao vivo vêm de um só lugar, então não podem divergir.

## Adicionando uma página no frontend

1. Tipos em `src/types/api.ts`, espelhando o schema do backend. `src/types/events.ts` precisa ficar idêntico a
   `app/observability/events.py` — uma divergência ali quebra o feed de atividade silenciosamente.
2. Uma função de serviço em `src/services/<resource>.ts`, construída sobre o `client.ts` compartilhado, retornando a resposta
   tipada.
3. Um hook em `src/hooks/` para o fetching e as mutações (o React Query já está conectado).
4. O componente da página em `src/pages/`, mais uma entrada de rota em `App.tsx` atrás de `ProtectedRoute`.
5. Trate os estados que de fato acontecem: carregando (`Spinner`), vazio (`EmptyState`), erro (`Toast`) e —
   para qualquer coisa que toque a automação — `blocked` (`CheckpointBanner`).

**Qualquer UI que possa enviar uma candidatura precisa exigir um clique distinto e deliberado**, com a carta e as
respostas visíveis na tela naquele momento. Não adicione um botão de "enviar tudo", e não faça o envio ser a
ação padrão de um formulário.

## Mexendo na camada do LinkedIn

O Playwright vive em exatamente dois lugares: `app/automation/browser.py` (launch e ciclo de vida) e
`app/automation/linkedin/` (`service.py` implementa o protocolo; `search.py`, `job.py` e `apply.py` fazem
o trabalho). Todo seletor vive em `app/automation/selectors.py`. Mais nada importa o Playwright.

Quando o LinkedIn muda a marcação:

1. Reproduza com um navegador com interface (abaixo) e descubra o que mudou.
2. Corrija o seletor em `app/automation/selectors.py`. Prefira atributos estáveis — `aria-label`, `data-*`,
   `role` — a nomes de classe gerados, que mudam constantemente.
3. Se um *passo* mudou em vez de um seletor, a correção pertence à implementação do `LinkedInService`.
   `contracts.py` não deveria precisar mudar; se precisar, isso é uma mudança de interface e requer uma olhada em
   cada chamador.
4. Adicione ou atualize o fake para que os testes cubram o novo formato.

Duas regras que não são negociáveis:

- **`fill_and_advance()` nunca pode enviar.** Ela avança o formulário e para na revisão. O envio vive
  só em `submit()`.
- **`SecurityCheckpointError` nunca pode ser capturado e contornado.** Detecte, levante, pare. Sem loop de repetição,
  sem seletor alternativo, sem tentativa de ler ou resolver um desafio.

## Testes

A suíte inteira roda offline e impõe isso: uma fixture autouse bloqueia o acesso a sockets, então um teste que
alcança a rede falha em vez de depender silenciosamente dela. Nenhuma conta do LinkedIn, nenhuma chave da Anthropic, nenhum
navegador.

```bash
pytest                     # tudo
pytest -x                  # para na primeira falha
pytest --lf                # reroda as últimas falhas
pytest -k "checkpoint"     # por nome
```

Os testes são agrupados pelo que exercitam: `tests/unit/` (schemas, crypto, security, throttle, scoring),
`tests/api/` (rotas, auth, isolamento entre usuários), `tests/automation/` (dry run, botão de parada, detecção de
verificação) e `tests/integration/` (o fluxo inteiro da aplicação, dedup, stats).

### Fixtures

`backend/tests/conftest.py` faz o trabalho pesado, e várias fixtures são `autouse` — você as recebe
querendo ou não:

| Fixture | Escopo | O que faz |
|---|---|---|
| `test_settings` | session, autouse | Aponta `Settings` para um `DATA_DIR` temporário e chaves determinísticas, e limpa o cache de `get_settings`. `get_settings` tem `lru_cache`, então qualquer coisa que mude o ambiente precisa invalidá-lo |
| `block_network` | autouse | Falha o teste se ele tentar abrir um socket. É o que mantém a suíte honesta sobre ser offline |
| `cap_sleep` | autouse | Limita `asyncio.sleep`, para que os atrasos aleatórios de 45–120 s de candidatura não façam a suíte levar uma hora |
| `sleep_spy` | — | Registra as durações que *teriam* sido dormidas, para que a temporização das salvaguardas seja assertável |
| `wire_fakes` | autouse | Injeta `FakeLinkedInService` e `FakeAIClient` no lugar dos adaptadores reais |
| `fake_linkedin` / `fake_ai` | — | As instâncias falsas, para configurar e fazer asserts |
| `engine` / `sessionmaker` / `session` | — | SQLite em memória com o schema criado, descartado no teardown para que o engine de nível de módulo não vaze |
| `user` / `other_user` | — | Duas contas — `other_user` é como o isolamento entre usuários é testado |
| `auth_headers` / `other_auth_headers` | — | Cabeçalhos `Authorization` prontos para cada uma |
| `app` / `client` | — | O app FastAPI com o sessionmaker de teste conectado, e um `httpx.AsyncClient` contra ele |

`pyproject.toml` define `asyncio_mode = "auto"`, então `async def test_...` não precisa de decorador, e
`pythonpath = ["backend"]`, então `from app...` resolve.

Construa linhas com as factories em `backend/tests/fixtures/factories.py` — `create_user`, `create_search`,
`create_job`, `create_application`, `create_run`, `create_analysis`, mais `make_job_posting`,
`make_form_question`, `make_profile_context` e `days_ago` para dados relativos ao tempo.

### O fake do LinkedIn

`LinkedInService` é um `Protocol` `runtime_checkable`, então
[`FakeLinkedInService`](../backend/tests/fixtures/fake_linkedin.py) apenas satisfaz as assinaturas — sem
herança, sem biblioteca de mocking, sem navegador. É uma dataclass que você configura por campo e depois faz assert
contra.

Configure o cenário:

| Campo | Efeito |
|---|---|
| `postings` / `job_count` | Os anúncios que `search_jobs()` retorna |
| `questions` / `unanswered` / `total_steps` | O formato do formulário de Candidatura Simplificada |
| `checkpoint_on` / `checkpoint_after` / `checkpoint_reason` | Levantar `SecurityCheckpointError` de uma chamada escolhida, opcionalmente após N sucessos |
| `error_on` / `error` | Levantar qualquer outro erro de uma chamada escolhida |
| `logged_in` / `browser_open` | Estado da sessão |
| `already_applied_ids` / `no_easy_apply_ids` | Disparar `AlreadyAppliedError` / `EasyApplyUnavailableError` |

Depois faça assert sobre o que aconteceu:

| Campo | Registra |
|---|---|
| **`submitted`** | **Ids de vaga que chegaram a `submit()`. Este é o assert que guarda o modo assistido** |
| `calls` | Todo método chamado, em ordem |
| `opened` | Vagas cujo modal de Candidatura Simplificada foi aberto |
| `filled` / `cover_letters` | As respostas e cartas passadas a `fill_and_advance()` |
| `screenshots` | Requisições de captura |

O módulo também traz `FakePage`, `FakeLocator` e `FakeBrowser` — incluindo um helper `checkpoint()` que
serve o texto real do desafio em inglês e em português — para que o próprio *detector* possa ser testado
sem um navegador. `make_postings(count)` gera anúncios em massa.

Uma guarda útil, caso o fake divirja do protocolo:

```python
assert isinstance(FakeLinkedInService(), LinkedInService)
```

### O fake de IA

[`FakeAIClient`](../backend/tests/fixtures/fake_ai.py) retorna os modelos Pydantic reais de
`app/ai/schemas.py` — `JobScore`, `CoverLetter`, `ScreeningAnswer`, `AIUsage` — deterministicamente. Ele
expõe `score_job()`, `write_cover_letter()` e `answer_questions()`, mais `is_configured()`,
`call_count(name)` e `usage()` para verificar com que frequência o modelo foi chamado e o que ele reportou. Pode
ser configurado para retornar uma nota escolhida, uma `AnswerConfidence` escolhida, ou levantar `FakeAIError` para que o
caminho de recusa-para-preenchimento-manual seja exercitado.

Definir a confiança como `LOW` é como você testa o invariante de sinalização: o model validator de `ScreeningAnswer`
seta `needs_review = True` para uma resposta de baixa confiança mesmo quando o campo foi deixado no padrão.

### O que testar

| Camada | Cobrir |
|---|---|
| Schemas | Valores de fronteira, validators entre campos, o auto-flag de `needs_review` |
| Models | Round-trips de enum, datetimes com timezone em ambos os backends |
| Auth | Hash/verificação, emissão/decodificação de token, expiração, o limite de 72 bytes do bcrypt |
| Crypto | Round-trip, e que uma chave alterada levanta `DecryptionError` |
| Throttle | Limite diário, horário, faixas de atraso (verifique via `sleep_spy`) |
| Engine | Parada por verificação, botão de parada, retomada a partir de `checkpoint`, dedup |
| **Invariante de aprovação** | **Que preparar nunca envia, e que enviar exige `confirm: true`** |
| Rotas | Caminho feliz, `401`, e `404` entre usuários (é para isso que `other_auth_headers` existe) |
| WebSocket | Isolamento por usuário, replay de histórico, que um socket morto não levanta exceção |

Os testes do invariante de aprovação são os que mais importam, e são o motivo de `FakeLinkedInService.submitted` existir.
`backend/tests/automation/test_engine_dry_run.py` e
`backend/tests/integration/test_application_flow.py` são os primeiros a ler — e se qualquer um falhar,
pare e corrija antes de qualquer outra coisa.

## Depurando a automação com um navegador com interface

O padrão já é um navegador visível (`HEADLESS=false`), que é a maior parte da batalha. Além disso:

**Desacelere** para conseguir ver o que acontece. O `slow_mo` do Playwright adiciona um atraso a cada ação:

```python
browser = await playwright.chromium.launch(headless=False, slow_mo=500)
```

**Use o Playwright Inspector** para passar pelas ações e testar seletores ao vivo:

```bash
PWDEBUG=1 pytest backend/tests/test_linkedin.py -k easy_apply -s
```

```powershell
$env:PWDEBUG=1; pytest backend/tests/test_linkedin.py -k easy_apply -s
```

O playground de seletores do Inspector é a forma mais rápida de encontrar um substituto para um seletor quebrado.

**Capture um trace** e inspecione-o depois do fato — snapshots de DOM, rede, capturas de tela por ação:

```python
await context.tracing.start(screenshots=True, snapshots=True, sources=True)
# ... run the flow ...
await context.tracing.stop(path="trace.zip")
```

```bash
playwright show-trace trace.zip
```

**Leia a trilha de auditoria primeiro.** Antes de recorrer ao navegador, verifique
`GET /api/applications/{id}/events` — o `payload` de cada evento geralmente nomeia o campo, as opções e
o passo em que as coisas deram errado. `application_events` existe para tornar isto o primeiro passo em vez do
último.

**Desligue os logs JSON** enquanto depura localmente; o formatador humano é mais fácil de ler:

```python
configure_logging(level="DEBUG", as_json=False)
```

**No Docker**, o navegador está no display virtual: abra <http://localhost:6080> e acompanhe por lá.
`docker compose logs -f` dá o log estruturado ao lado.

## Migrations

`alembic.ini` vive em `backend/`, então rode estes a partir desse diretório — ou use `make migrate` e
`make migration m="..."` a partir da raiz do repositório, que fazem o `cd` por você.

```bash
cd backend

alembic revision --autogenerate -m "add widget table"   # generate
alembic upgrade head                                     # apply
alembic downgrade -1                                     # roll back one
alembic current                                          # where am I
alembic history --verbose                                # what exists
```

No Docker não há nada a rodar: o entrypoint aplica `alembic upgrade head` em todo boot.

**Sempre leia a migration gerada antes de commitá-la.** O autogenerate é bom com tabelas e colunas
adicionadas e ruim com renomeações — ele vai alegremente emitir um drop-and-create que destrói dados. Reescreva essas como
`op.alter_column(..., new_column_name=...)` à mão.

`backend/migrations/versions` é excluído do ruff, então arquivos gerados não são reformatados para uma
inconsistência.

O fluxo para uma mudança de schema:

1. Edite o model em `app/models/`.
2. `make migration m="..."`.
3. Leia o arquivo. Corrija as renomeações. Verifique que o downgrade de fato reverte o upgrade.
4. `alembic upgrade head`, depois `alembic downgrade -1`, depois `alembic upgrade head` de novo — uma migration que
   não consegue fazer round-trip é uma migration da qual você não consegue voltar atrás.
5. Atualize a seção de schema de [architecture.md](architecture.md) se o propósito de uma tabela mudou.
6. Commite a mudança do model e a migration juntas.

`init_models()` cria tabelas faltantes na inicialização como conveniência para quem roda sem o Alembic. Ele
não altera tabelas existentes, então não é substituto de uma migration.

## CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) roda no push e no pull request:

- **backend**, em matriz sobre Python 3.11 e 3.12 — `ruff check`, `mypy` (`continue-on-error`), `pytest`.
- **frontend** — `npm ci`, `npm run typecheck`, `npm run build`.

Os caches de pip e npm são chaveados nos lockfiles, e `concurrency` cancela execuções substituídas numa branch.
O Chromium deliberadamente **não** é instalado na CI: a suíte roda contra os fakes, então baixar um navegador
adicionaria minutos por nada.

Nenhum segredo é configurado e nenhum é necessário, porque os testes são offline. Se um teste seu precisar de uma
chamada de rede ou uma chave de API, ele pertence atrás de um marker e fora da CI.

Rode as mesmas verificações localmente antes de fazer push:

```bash
make lint && make typecheck && make test
cd frontend && npm run typecheck && npm run build
```
