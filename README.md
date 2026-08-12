# LinkedIn Auto Apply

Um agente assistido de candidatura a vagas para o LinkedIn Easy Apply (Candidatura Simplificada). Ele encontra vagas, pontua cada uma em relação ao seu currículo com a
Claude, redige as respostas de triagem e a carta de apresentação, preenche o formulário — e então **para e espera
você ler e aprovar** antes de qualquer coisa ser enviada.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/react-vite-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/fastapi-async-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

> ## ⚠️ Leia isto antes de instalar qualquer coisa
>
> **Esta ferramenta automatiza a interface web do LinkedIn dirigindo um navegador real.**
>
> **O Contrato de Usuário do LinkedIn proíbe o acesso automatizado.** Scrapers, bots e automação de navegador estão
> todos citados. Não existe leitura do Contrato sob a qual isto seja permitido.
>
> **Usá-la pode fazer a sua conta ser restringida ou banida permanentemente.** A critério do LinkedIn, sem
> recurso a que você tenha direito. A sua rede, as suas mensagens e o seu perfil estão nessa conta.
>
> **O LinkedIn não oferece nenhuma API oficial para buscar ou se candidatar a vagas.** É *por isso* que isto dirige um
> navegador. Não é uma justificativa — é o motivo de o risco existir e não poder ser eliminado por engenharia.
>
> **As salvaguardas reduzem esse risco. Elas não o eliminam.** Atrasos aleatórios, um limite diário, uma
> janela de horário e a aprovação humana obrigatória mantêm a ferramenta operando de forma conservadora — um volume
> modesto que você consegue de fato ler, num ritmo sem pressa, com uma pessoa aprovando cada envio. Elas não
> fazem nada quanto ao fingerprinting do navegador, e não há limiar seguro — uma sessão azarada pode disparar uma
> verificação.
>
> **Você é responsável pela sua própria conta.** Ninguém aqui consegue reverter uma restrição para você. Pese
> o tempo economizado contra o que perder a conta custaria a você. Para muita gente a resposta honesta é
> fechar esta aba e se candidatar à mão.
>
> **O projeto nunca pede nem armazena a sua senha do LinkedIn.** Não há campo para ela no schema,
> nem parâmetro para ela na API, nem prompt para ela na UI. Você faz login você mesmo, numa janela de navegador
> visível. Apenas os cookies da sessão são guardados, criptografados em repouso.
>
> O modelo de risco completo está em **[docs/safety.md](docs/safety.md)**. Por favor, leia de verdade.

---

## Por que existe

Candidatar-se a vagas no LinkedIn é um ciclo de tédio com alguns minutos de reflexão real escondidos dentro: ler
o anúncio, decidir se você combina, redigitar a mesma pretensão salarial e aviso prévio, escrever uma carta de
apresentação que diga algo específico sobre a empresa. O tédio é automatizável. O julgamento não é.

Então isto automatiza o tédio e devolve a você o julgamento, no ponto em que ele importa:

```text
   ┌──────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌────────┐
   │  Busca   │──▶ │ IA pontua │──▶ │VOCÊ revisa│──▶ │ Preenche  │──▶ │ VOCÊ      │──▶ │ Envia  │
   │ LinkedIn │    │  0–100    │    │ as vagas  │    │formulário │    │ aprova    │    │        │
   └──────────┘    └───────────┘    └───────────┘    └───────────┘    └───────────┘    └────────┘
                          │                                │                 ▲
                    abaixo da nota mín.          para na etapa de       nada passa
                      → pulada                   revisão. nunca envia.  daqui sozinho
```

**O envio é sempre um passo separado e confirmado por um humano.** Buscar, pontuar e preencher são três
operações diferentes que você invoca separadamente, e o endpoint que envia recebe um id de candidatura e um
`confirm: true` explícito. Não há envio em massa nem modo autônomo. Isso não é uma opção que você pode ligar
— é imposto em quatro lugares independentes, e um pull request que o enfraqueça não será aceito.

O modo de teste (dry run) está ligado por padrão: o fluxo inteiro roda, até o clique final, e não envia nada.

## Funcionalidades

**Busca e pontuação**

- Buscas salvas e reutilizáveis — palavras-chave, localização, remoto/híbrido/presencial, data de publicação, senioridade, apenas Candidatura
  Simplificada, com um limite de resultados por execução para que as varreduras fiquem curtas
- Pontuação de aderência por IA, 0–100, com os **motivos** da nota e uma lista explícita de **requisitos
  faltantes** — a segunda lista é a mais útil, porque diz o que um recrutador vai perguntar
- Um limiar de nota mínima, para que combinações fracas sejam puladas em vez de recebermos candidatura
- Deduplicação por `(usuário, id externo da vaga)`: rodar uma busca de novo nunca reprocessa um anúncio

**Geração de texto**

- Cartas de apresentação escritas **no idioma do anúncio** — detectado por vaga, ou fixado em um idioma se
  você preferir
- Sugestões de respostas de triagem tiradas do seu currículo e de um banco de respostas reutilizável (pretensão salarial, aviso
  prévio, autorização de trabalho), cada uma com um nível de confiança
- **Respostas de baixa confiança são sinalizadas para revisão**, nunca adivinhadas em silêncio. Um valor de confiança `low` marca
  `needs_review` automaticamente, então uma resposta duvidosa não chega até você sem marcação
- Campos que a IA não consegue preencher com confiança marcam a candidatura como precisando de intervenção humana em vez de serem
  inventados
- Recusas do modelo são registradas e recorrem ao preenchimento manual — o que é o sistema funcionando, não falhando

**Revisão e controle**

- Toda candidatura espera em `awaiting_review` com a carta e cada resposta editáveis antes de você aprovar
- Uma **linha do tempo de auditoria por vaga**: cada passo do formulário, cada pergunta respondida, cada erro, com data e um
  payload JSON. É o que transforma "a candidatura falhou" num evento diagnosticável
- **Atividade ao vivo via WebSocket** — vagas encontradas, notas conforme chegam, o momento em que uma candidatura está pronta para
  você, com os últimos 200 eventos reproduzidos na reconexão para que um recarregamento de página reconstrua o feed
- Um **botão de parada** que interrompe uma execução de forma limpa entre passos, e não no meio de um clique, para que nada fique
  parcialmente enviado
- **Modo de teste (dry run)**, ligado por padrão, que ensaia tudo e não envia nada
- Salvaguardas conservadoras: atrasos aleatórios, um limite diário, uma janela de horário, uma única sessão de navegador

**Segurança e operação**

- **Uma verificação de segurança para tudo.** CAPTCHA ou "atividade incomum" move a execução para `blocked` e
  para. Sem repetição, sem contorno, sem opção para pular — você resolve você mesmo
- **Sessão do LinkedIn criptografada em repouso** com Fernet, com chave derivada via HKDF-SHA256. Nenhuma senha é armazenada, e
  nenhum cookie jamais é retornado pela API
- Log estruturado em JSON com contexto por execução, para que as linhas de log de uma execução sejam pesquisáveis com grep
- Contabilidade de tokens e custo em cada chamada de IA
- Um **modelo de dados multiusuário** — o isolamento que mantém os cookies e o feed de eventos de uma pessoa longe dos de
  outra, mesmo quando você é o único usuário
- **SQLite por padrão**, nenhum servidor de banco para instalar; **PostgreSQL** suportado trocando uma variável de
  ambiente

## Capturas de tela

**Currículo adaptado com um guarda contra invenção.** A IA reorganiza e reenfatiza o seu currículo para um anúncio —
nunca adiciona experiência que você não tem — e um guarda sinaliza qualquer tecnologia que apareça no texto adaptado
mas não no seu perfil, para que uma invenção não passe despercebida.

![Painel de adaptação de currículo — a lista de mudanças, requisitos que o currículo não cobre e um alerta sinalizando "Kubernetes" como presente no CV adaptado mas não no perfil](docs/images/cv-tailoring.png)

**Funil — uma nota maior leva mesmo a uma entrevista?** As candidaturas que você enviou se movem
por colunas de desfecho (Enviada → Entrevista → Proposta → Rejeitada → Sem resposta), e o quadro mede a
taxa de entrevista para cada faixa de nota de aderência, para que a nota da IA seja confrontada com resultados reais em vez de
aceita por fé.

![Funil — colunas Kanban de candidaturas enviadas por desfecho e um gráfico da taxa de entrevista por faixa de nota de aderência, mostrando que faixas mais altas entrevistam com mais frequência](docs/images/pipeline.png)

| | |
|---|---|
| ![Painel — contadores de enviadas-hoje e aguardando-revisão, nota média, feed de atividade ao vivo](docs/images/dashboard.png) | ![Lista de vagas — notas, motivos, requisitos faltantes](docs/images/jobs.png) |
| **Painel** — contadores, nota média, o que está esperando por você | **Vagas** — pontuadas, com motivos e lacunas |
| ![Revisão de candidatura — o portão de aprovação: carta editável, respostas de triagem com uma de baixa confiança sinalizada e a linha do tempo de eventos completa](docs/images/review.png) | ![Configurações — salvaguardas e preferências de IA](docs/images/settings.png) |
| **Revisão** — o portão de aprovação, uma resposta sinalizada e a linha do tempo de auditoria | **Configurações** — salvaguardas, chave do modo de teste |

Para capturar as suas próprias: rode o app, popule-o com uma busca em modo de teste para que as telas tenham conteúdo real, então
tire uma captura da viewport em 1440×900 (`Ctrl/Cmd+Shift+P` → "Capture screenshot" no Chrome DevTools) e
salve em `docs/images/` com o nome de arquivo acima. **Borre ou recorte qualquer coisa identificável** antes de commitar —
o seu e-mail, o seu telefone e o conteúdo do seu currículo aparecem nessas telas.

---

## Início rápido

Dois caminhos. Escolha um.

### Pré-requisitos (ambos os caminhos)

Uma **chave de API da Anthropic** em [console.anthropic.com](https://console.anthropic.com/) → API keys. O app
funciona sem uma — você só preenche os formulários você mesmo, sem pontuação e sem cartas geradas.

Dois segredos importam, e o caminho do Docker os gera para você:

- `SECRET_KEY` assina os seus tokens de login. Deixado vazio numa instalação local, um aleatório é gerado por
  processo, o que desloga você a cada reinício.
- `ENCRYPTION_KEY` deriva a chave que criptografa a sua sessão do LinkedIn. **Mudá-la depois torna as sessões
  armazenadas permanentemente ilegíveis** — recuperável reconectando, mas um baita incômodo.

Gere uma com qualquer um destes, duas vezes, mantendo os valores distintos:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
openssl rand -base64 48
```

### Caminho A — Docker (recomendado)

Um contêiner roda tudo: a API, o frontend compilado, o Chromium e uma ponte noVNC para que você possa ver o
navegador. O Docker também fixa o Chromium e as bibliotecas de sistema dele, que é a parte de uma instalação local mais
propensa a quebrar.

```bash
git clone https://github.com/joaovictorgcu/smart-job-apply.git
cd smart-job-apply
cp .env.example .env
```

Abra `.env` e defina a sua chave de API:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
```

Você pode deixar `SECRET_KEY` e `ENCRYPTION_KEY` vazios aqui — o entrypoint do contêiner os gera no
primeiro boot e os guarda no volume de dados, para que os seus logins e a sua sessão salva do LinkedIn sobrevivam a
reinícios. Defina-os você mesmo se preferir gerenciá-los.

Compile e inicie:

```bash
docker compose up -d --build      # ou: make docker-up
docker compose logs -f            # ou: make docker-logs
```

Depois abra **ambos** estes:

| URL | O que é |
|---|---|
| <http://localhost:8000> | O app inteiro — UI e API. Docs em [`/docs`](http://localhost:8000/docs), saúde em `/api/health` |
| **<http://localhost:6080>** | **noVNC — a tela do navegador. É aqui que você faz login no LinkedIn.** |

Essa segunda URL não é opcional. O Chromium roda num display virtual dentro do contêiner, e o noVNC é a
única forma de vê-lo — para logar, para resolver um desafio de segurança, para acompanhar um formulário sendo preenchido. Abra-a antes
de iniciar uma sessão de navegador. O VNC bruto na 5900 é deliberadamente não publicado; ele fica vinculado ao localhost dentro
do contêiner e acessível somente por essa ponte.

Não há porta 5173 no Docker: o backend serve o frontend compilado na 8000, e é por isso que `CORS_ORIGINS`
é definido como a própria origem do app no `docker-compose.yml`.

Crie a sua conta em <http://localhost:8000>, ou pela linha de comando:

```bash
docker compose exec app python scripts/create_user.py --email you@example.com --name "Your Name"
```

As senhas têm 10–72 caracteres (72 bytes é um limite do bcrypt). Omita `--password` e você será solicitado por ela,
para que fique fora do histórico do seu shell e da lista de processos.

### Caminho B — Local

Precisa de **Python 3.11+**, **Node.js 20+** e uma sessão de desktop — o navegador precisa estar visível para você
logar.

```bash
git clone https://github.com/joaovictorgcu/smart-job-apply.git
cd smart-job-apply
```

Com `make` disponível (Linux, macOS ou WSL), tudo são quatro comandos:

```bash
make install      # venv + deps do backend + deps do frontend + Chromium + um .env inicial
make migrate      # cria o schema do banco
make user         # cria a sua conta (solicita a senha)
make dev          # backend na :8000, frontend na :5173, Ctrl-C para ambos
```

`make help` lista todos os alvos. No Windows sem WSL, rode o script de setup diretamente e use os
equivalentes em PowerShell impressos no cabeçalho do Makefile:

```powershell
.\scripts\setup.ps1
```

<details>
<summary>Se o PowerShell bloquear o script</summary>

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup.ps1
```

Isto permite scripts não assinados apenas para a sessão atual.
</details>

<details>
<summary>Ou faça tudo à mão</summary>

```bash
python -m venv .venv
source .venv/bin/activate                    # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
playwright install chromium                  # Debian/Ubuntu: adicione --with-deps
cd frontend && npm ci && cd ..
cp .env.example .env                         # depois defina ANTHROPIC_API_KEY, SECRET_KEY, ENCRYPTION_KEY
cd backend && alembic upgrade head && cd ..
python scripts/create_user.py --email you@example.com --name "Your Name"
```
</details>

Depois edite `.env` para adicionar a sua chave de API e os dois segredos, e inicie os dois processos. `make dev` roda ambos;
o equivalente manual são dois terminais:

```bash
# Terminal 1 — API
.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend --port 8000

# Terminal 2 — painel
cd frontend && npm run dev
```

PowerShell:

```powershell
# Terminal 1 — API
.venv\Scripts\python -m uvicorn app.main:app --reload --app-dir backend --port 8000
```

```powershell
# Terminal 2 — painel
cd frontend
npm run dev
```

`--app-dir backend` é o que coloca o pacote `app` no caminho de import, então isto funciona com ou sem o
install editável ter dado certo.

| URL | O que é |
|---|---|
| <http://localhost:5173> | O painel (servidor de dev do Vite, hot reload) |
| <http://localhost:8000/docs> | Docs OpenAPI ao vivo |

No modo local o navegador abre como uma janela real no seu desktop — sem noVNC, sem porta 6080. Faça login em
<http://localhost:5173> com a conta que o `make user` criou.

Instruções exaustivas por plataforma, a troca para PostgreSQL, atualização e backups:
**[docs/installation.md](docs/installation.md)**.

---

## Primeira execução, passo a passo

O modo de teste (dry run) está **ligado por padrão**. Tudo abaixo acontece sem uma única candidatura ser enviada, até
você deliberadamente desligá-lo. Faça pelo menos uma passagem completa desse jeito.

1. **Crie a sua conta.** Registre-se na UI, ou rode `make user` / `python scripts/create_user.py`. Este é
   o login do próprio app e não tem nada a ver com o LinkedIn. Contas novas começam em modo de teste com aprovação
   manual obrigatória, então uma instalação nova não consegue enviar nada antes de você configurá-la.

2. **Preencha o seu perfil e envie o seu currículo.** Título, localização, telefone, anos de experiência, habilidades e
   um resumo. Envie o PDF que você realmente quer que os empregadores recebam — ele é anexado aos formulários de Candidatura Simplificada,
   e o texto dele é o que a IA usa para pontuar as vagas. Um perfil raso produz notas fracas e cartas vagas.

3. **Preencha o banco de respostas.** Estes são os cinco minutos de maior valor que você vai gastar aqui. Pretensão
   salarial, aviso prévio, autorização de trabalho, anos com as suas principais tecnologias. Estas são as
   perguntas que todo formulário de Candidatura Simplificada faz, e um banco preenchido é a diferença entre respostas confiantes
   e palpites sinalizados.

4. **Conecte o LinkedIn.** Inicie uma sessão de navegador pelo painel, então **faça login manualmente na janela do
   navegador** — noVNC em <http://localhost:6080> no Docker, a janela do desktop localmente. Conclua a autenticação
   de dois fatores normalmente. O app observa até o login ter sucesso e então criptografa e armazena a
   sessão. Ele nunca vê a sua senha.

5. **Salve uma busca.** Palavras-chave, localização, preferência de trabalho remoto, data de publicação. Deixe "Apenas Candidatura Simplificada" ligado — só
   formulários de Candidatura Simplificada podem ser preenchidos. Comece com `max_results` em 25.

6. **Rode.** A busca encontra vagas e as pontua. Acompanhe o feed de atividade: `job.found` conforme cada anúncio
   aparece, `job.analyzed` conforme cada nota chega. Nada recebe candidatura.

7. **Revise as vagas pontuadas.** Ordene por nota. Leia os motivos e — mais importante — os requisitos
   faltantes. É aqui que você decide, não o modelo. Pule as que você não quer de verdade.

8. **Pré-visualize, depois prepare.** A pré-visualização informa quantas vagas seriam processadas, quantas já foram
   candidatadas e quanto do seu limite diário resta. Confirme, e a automação abre cada formulário de Candidatura
   Simplificada, preenche, anexa o seu currículo e **para na etapa de revisão**.

9. **Leia o rascunho direito.** A carta de apresentação e cada resposta de triagem, com as de baixa confiança
   destacadas. Corrija o que estiver errado. **Não pule isto** — a carta sai em seu nome, e as
   respostas são declarações sobre você. Se diz oito anos de Python e você tem quatro, mude
   antes de aprovar.

10. **Aprove.** Uma candidatura, um clique deliberado. Ela é enviada, a trilha de auditoria registra quem aprovou
    o quê e quando, e a vaga passa para `applied`.

11. **Quando estiver pronto para envios de verdade**, desligue `dry_run` em Configurações — deliberadamente, tendo
    acompanhado o fluxo pelo menos uma vez. Ligue de novo quando terminar por hoje.

Se um desafio de segurança aparecer em qualquer ponto, a execução para e o painel diz `blocked`. **Resolva
você mesmo no navegador.** Se continuar acontecendo, é o LinkedIn dizendo que a atividade parece
automatizada — pare, em vez de ajustar atrasos até os avisos sumirem.

---

## Configuração

Duas camadas: variáveis de ambiente (implantação) e configurações por usuário (operação). As variáveis `DEFAULT_*`
semeiam as configurações de um novo usuário; depois disso os valores por usuário vencem.

### As variáveis de ambiente que importam

| Variável | Padrão | O que faz |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Habilita pontuação, cartas e sugestões de respostas. Vazio é válido; você preenche os formulários |
| `SECRET_KEY` | aleatório por processo | Assina os JWTs. **Defina**, ou reinícios deslogam você |
| `ENCRYPTION_KEY` | recorre a `SECRET_KEY` | Criptografa a sessão do LinkedIn. Mudá-la torna as sessões armazenadas ilegíveis |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Modelo usado para pontuação e geração de texto |
| `SCORING_EFFORT` | `low` | Esforço de raciocínio para pontuação em massa. Cartas sempre usam `high` |
| `DATABASE_URL` | *(vazio → SQLite)* | `postgresql+asyncpg://…` para trocar de backend |
| `HEADLESS` | `false` | Mantenha false. Você precisa ver o navegador |
| `ASSISTED_MODE_ONLY` | `true` | A garantia de nenhum-envio-sem-confirmação |
| `CORS_ORIGINS` | `["http://localhost:5173", …]` | Array JSON. Adicione o seu endereço de LAN para usar o painel de outra máquina |
| `DATA_DIR` | `backend/data` | Onde ficam o banco, os perfis de navegador e o seu currículo |

> Configurações de lista e tupla precisam ser **JSON** no `.env`: `CORS_ORIGINS=["http://localhost:5173"]`,
> `DEFAULT_ACTION_DELAY_RANGE=[2.5, 7.0]`. Um valor separado por vírgulas puro dispara `SettingsError` na inicialização.

### As salvaguardas

Por usuário, editáveis em Configurações. **Afrouxá-las é a única parte da configuração que carrega risco real** —
cada linha em [docs/configuration.md](docs/configuration.md#guard-rails) diz exatamente o que você abre mão.

| Configuração | Padrão | Faixa |
|---|---|---|
| `dry_run` | `true` | Preenche tudo, não envia nada |
| `require_manual_approval` | `true` | Aprovação explícita antes de qualquer envio |
| `daily_cap` | 15 | 1–50 |
| `min_score` | 70 | 0–100 |
| `action_delay_min` / `max` | 2.5 / 7.0 s | aleatório por ação |
| `apply_delay_min` / `max` | 45 / 120 s | aleatório por candidatura |
| `working_hour_start` / `end` | 08:00–20:00 | horas locais |
| `generate_cover_letter` | `true` | — |
| `content_language` | `job` | `job` segue o anúncio; ou fixe `en`, `pt-BR` |

Cada configuração, cada campo, cada limite: **[docs/configuration.md](docs/configuration.md)**.

---

## Arquitetura

```mermaid
flowchart LR
    UI["React + Vite"] -->|"REST /api"| API["FastAPI"]
    UI <-->|"WebSocket"| API
    API --> ENG["Engine<br/>salvaguardas"]
    ENG --> SVC["LinkedInService<br/>(protocolo)"]
    ENG --> AI["Cliente Claude"]
    SVC --> PW["Playwright<br/>Chromium"]
    PW --> LI["linkedin.com"]
    API --> DB[("SQLite / PostgreSQL")]
    ENG --> DB
```

**A regra de camadas:**

```
Engine  ->  LinkedInService (protocolo)  ->  Playwright
```

O engine nunca importa o Playwright e nunca toca num `Page` ou num `Locator`. Ele fala apenas em dataclasses
simples — `SearchFilters`, `JobPosting`, `FormQuestion`, `ApplicationDraft`. Todo seletor CSS vive em
um arquivo, `app/automation/selectors.py`.

Isso compra duas coisas. Quando o LinkedIn lança um redesign, a correção fica confinada a um arquivo. E toda a
camada de orquestração — salvaguardas, limiares, transições de estado, o portão de aprovação — é coberta por testes
offline rápidos contra um `LinkedInService` falso, sem navegador e sem conta. A camada de IA segue o mesmo
padrão: `JobScore`, `ScreeningAnswer` e `CoverLetter` são o contrato, então trocar de modelo não vaza
para a API.

```text
backend/
├── app/
│   ├── ai/                 # client.py, scoring.py, prompts/, schemas.py
│   ├── api/                # deps.py, errors.py, routes/ (one module per resource)
│   ├── auth/               # JWT, bcrypt, at-rest encryption, dependencies
│   ├── automation/
│   │   ├── contracts.py    # the dataclasses and the LinkedInService protocol
│   │   ├── errors.py       # retryable vs stop-now
│   │   ├── engine.py       # orchestration — no Playwright imports
│   │   ├── throttle.py     # delays, daily cap, working hours
│   │   ├── browser.py      # Playwright launch and lifecycle
│   │   ├── selectors.py    # every CSS selector, in one file
│   │   └── linkedin/       # service.py, search.py, job.py, apply.py
│   ├── services/           # application, automation, job, search, stats, user
│   ├── database/           # async engine, session, UTC datetime handling
│   ├── models/             # SQLAlchemy ORM + lifecycle enums
│   ├── observability/      # structured logging, audit trail, events
│   ├── schemas/            # Pydantic request/response models
│   ├── websocket/          # per-user live broadcast
│   ├── config.py
│   └── main.py
├── migrations/             # Alembic (alembic.ini lives in backend/)
├── tests/                  # unit/ api/ automation/ integration/ fixtures/
└── data/                   # SQLite, browser profiles, résumés — gitignored
frontend/src/               # components/ hooks/ lib/ pages/ services/ types/
docker/                     # Dockerfile, entrypoint.sh, supervisord.conf
docs/  scripts/  Makefile  docker-compose.yml
```

As fronteiras de camadas, o modelo de dados completo e por que cada tabela existe, o fluxo de eventos do engine até a aba do navegador,
e os trade-offs de projeto: **[docs/architecture.md](docs/architecture.md)**.

**Stack** — Python 3.11+, FastAPI, SQLAlchemy 2 async, Alembic, Playwright, o SDK da Anthropic, JWT + bcrypt +
Fernet; React, Vite, Tailwind CSS.

---

## Desenvolvimento

```bash
make test                       # pytest — offline, sem conta ou chave de API
make lint                       # ruff check .
make format                     # ruff format + autofixes seguras
make typecheck                  # mypy backend/app (consultivo)
make migrate                    # alembic upgrade head
make migration m="add x"        # gera uma migration automaticamente
cd frontend && npm run typecheck && npm run lint && npm run build
```

A suíte de testes roda contra `FakeLinkedInService` e `FakeAIClient`, com o acesso à rede bloqueado e sleeps
limitados por fixtures autouse — então é rápida, determinística e não precisa de navegador. A asserção mais importante
do repositório é que preparar uma candidatura nunca chega a `submit()`.

Regras da casa: apenas inglês, nunca `print()` (use `app.observability.get_logger`), comente o *porquê* em vez
do *o quê*, e mantenha o Playwright dentro de `app/automation/browser.py` e `app/automation/linkedin/`.

Layout do projeto, como adicionar uma rota ou um serviço, como os fakes funcionam, o fluxo de migração e como
depurar a automação com um navegador com interface e traces do Playwright:
**[docs/development.md](docs/development.md)** · **[CONTRIBUTING.md](CONTRIBUTING.md)**

---

## Solução de problemas

| Sintoma | O que está acontecendo |
|---|---|
| **`ElementNotFoundError`, ou um passo que funcionava agora falha** | O LinkedIn mudou a marcação. Corrija o seletor em `backend/app/automation/selectors.py` — prefira `aria-label`, `data-*` e `role` a nomes de classe gerados. Este é o modo de falha mais comum e é uma correção de um arquivo. |
| **O status da execução é `blocked`, "verificação de segurança" na tela** | Uma verificação de segurança foi detectada e tudo parou, por design. **Resolva você mesmo na janela do navegador.** Não há contorno e não haverá. Se recorrer, pare de usar a ferramenta nessa conta. |
| **O Chromium trava ou morre na inicialização (Docker)** | `/dev/shm` é pequeno demais — o padrão do Chromium num contêiner é 64 MB. O `docker-compose.yml` já define `shm_size: 1gb`; aumente para `2gb` e recompile se ainda bater nisso. |
| **A IA recusou, ou não retornou nada** | Recusas são registradas em `AIAnalysis.was_refusal` e a candidatura recorre ao preenchimento manual. Preencha o campo você mesmo. Isto é o sistema funcionando. |
| **"Sessões perdidas" / "não foi possível descriptografar dados armazenados"** | `ENCRYPTION_KEY` mudou (ou `SECRET_KEY` mudou, quando a primeira não está definida). Sessões armazenadas são ilegíveis com uma chave diferente. Restaure o valor antigo, ou reconecte o LinkedIn e faça login mais uma vez. |
| **Deslogado do painel a cada reinício** | `SECRET_KEY` não está definida, então uma nova aleatória é gerada a cada início. Defina-a no `.env`. |
| **`SettingsError: error parsing value for field ...`** | Uma configuração de lista ou tupla no `.env` não é JSON. Use `[2.5, 7.0]` e `["http://localhost:5173"]`. |
| **`Executable doesn't exist at ...ms-playwright...`** | Rode `playwright install chromium` dentro do ambiente virtual ativo. |
| **O frontend carrega, toda requisição falha com erro de CORS** | A origem do seu painel não está em `CORS_ORIGINS`. Adicione-a e reinicie. |
| **Uma candidatura falhou e você quer saber por quê** | `GET /api/applications/{id}/events` — a trilha de auditoria nomeia o campo, as opções e o passo. Comece por aí, não pelo navegador. |

Mais, incluindo problemas por plataforma: [docs/installation.md](docs/installation.md#troubleshooting).

---

## Roteiro

Ordem aproximada, sem datas. Qualquer coisa que reduza a supervisão humana está permanentemente fora de escopo.

- Sugestões de adaptação de currículo por vaga — destacando qual da sua experiência existente colocar em primeiro plano, sem
  inventar nada
- Lembretes de acompanhamento de candidatura e rastreamento de desfecho (respondeu / entrevista / rejeitado), para que o modelo de nota
  tenha uma referência real para se conferir
- Melhor correspondência do banco de respostas, para que perguntas recorrentes parem de ser reperguntadas ao modelo
- Exportar o seu histórico para CSV
- Execuções retomáveis expostas na UI (o campo `checkpoint` já existe)
- Uma extensão de navegador para salvar uma vaga na fila direto do LinkedIn
- Testes contra fixtures de DOM gravadas do LinkedIn, para que a quebra de seletor seja pega antes de você esbarrar nela

**Explicitamente não planejado:** execuções autônomas ou noturnas, envio em massa, resolução de CAPTCHA, evasão de fingerprint,
armazenamento de credenciais do LinkedIn, ou qualquer coisa que remova a etapa de revisão.

## Como contribuir

Issues e pull requests são bem-vindos. Duas regras são absolutas: **nenhuma mudança pode enfraquecer a garantia de
aprovação humana**, e **nada pode contornar um desafio de segurança**. Detalhes, além de setup, convenções de branch e commit,
e o checklist pré-PR, em [CONTRIBUTING.md](CONTRIBUTING.md). Ao participar você concorda com o
[Código de Conduta](CODE_OF_CONDUCT.md).

Questões de segurança: envie e-mail para **jvgcu@cesar.school** em vez de abrir uma issue pública.

## Licença

[MIT](LICENSE) © 2026 João Victor Uchôa

---

## Aviso legal

Este projeto não é afiliado, endossado ou conectado ao LinkedIn de forma alguma. Ele automatiza a
interface web do LinkedIn, o que o Contrato de Usuário do LinkedIn proíbe; usá-lo pode resultar na sua conta ser
restringida ou banida permanentemente, e nenhuma salvaguarda neste código pode evitar esse desfecho — os atrasos,
limites e portões de aprovação reduzem o risco sem removê-lo. Você é o único responsável por como usa
este software e por qualquer coisa que aconteça à sua conta, e o autor não aceita nenhuma responsabilidade por acesso
perdido, dados perdidos ou candidaturas enviadas em seu nome. Use na sua própria conta, num volume humano, e
leia cada candidatura antes de aprovar.
