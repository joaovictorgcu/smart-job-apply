# Instalação

Dois caminhos suportados. **Docker** é recomendado — ele fixa o Chromium e as bibliotecas de sistema dele, que é a
parte de uma instalação local mais propensa a dar errado. **Local** é melhor se você quiser mexer no código.

Leia [safety.md](safety.md) antes de rodar qualquer coisa.

---

## Pré-requisitos

### Caminho Docker

| Requisito | Notas |
|---|---|
| Docker Engine 24+ com Compose v2 | `docker compose version` deve imprimir `v2.x`. O Docker Desktop no Windows e no macOS já inclui. |
| ~3 GB de disco livre | Principalmente a camada do Chromium. |
| ~2 GB de RAM livre | O Chromium precisa de folga; veja a nota sobre `shm_size` abaixo. |
| Uma chave de API da Anthropic | Opcional mas é o ponto do projeto. [console.anthropic.com](https://console.anthropic.com/) → API keys. |

### Caminho local

| Requisito | Notas |
|---|---|
| Python 3.11 ou 3.12 | `python --version`. 3.13 não é coberto pela CI. |
| Node.js 20+ e npm | Para o frontend. `node --version` |
| Git | |
| Uma sessão de desktop | O navegador precisa estar visível para você fazer login no LinkedIn. Num servidor Linux headless, use o caminho Docker — ele fornece um display virtual. |
| Uma chave de API da Anthropic | Como acima. |

---

## Docker

### 1. Clone e configure

```bash
git clone https://github.com/joaovictorgcu/smart-job-apply.git
cd smart-job-apply
```

Copie o arquivo de ambiente de exemplo e defina a sua chave de API:

```bash
cp .env.example .env
```

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
SECRET_KEY=
ENCRYPTION_KEY=
```

**No Docker você pode deixar ambos os segredos vazios.** O entrypoint do contêiner os gera no primeiro boot e
os guarda no volume de dados, para que os logins e a sessão salva do LinkedIn sobrevivam a reinícios. Defina-os
explicitamente se preferir gerenciá-los você mesmo — por exemplo, para manter um backup restaurável em um
host diferente, já que um volume restaurado precisa da mesma `ENCRYPTION_KEY` para descriptografar a sessão armazenada.

Para gerar os valores você mesmo, rode qualquer um destes duas vezes e mantenha-os distintos:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
openssl rand -base64 48
```

Sem Python ou OpenSSL no host?
`docker run --rm python:3.12-alpine python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Toda outra variável em [configuration.md](configuration.md) pode ir no mesmo arquivo. Duas são definidas para você em
`docker-compose.yml` e não devem ser sobrescritas: `DATA_DIR` (o caminho do contêiner respaldado pelo volume) e
`CORS_ORIGINS` (a própria origem do app, porque o backend serve o frontend).

### 2. Compile e inicie

```bash
docker compose up -d --build
```

O primeiro build leva vários minutos; o Chromium é grande. Depois:

```bash
docker compose ps          # todos os serviços devem estar rodando
docker compose logs -f     # acompanha a inicialização, Ctrl-C para desanexar
```

### 3. Abra as duas URLs

| URL | O que é |
|---|---|
| <http://localhost:8000> | O app inteiro — UI e API. Docs em <http://localhost:8000/docs>, saúde em <http://localhost:8000/api/health> |
| <http://localhost:6080> | **noVNC — a tela do navegador.** É aqui que você faz login no LinkedIn. |

A janela do noVNC não é opcional. O Chromium roda dentro do contêiner num display virtual, e a única forma
de vê-lo — para logar, para resolver um desafio de segurança, para acompanhar um formulário sendo preenchido — é por essa URL.
Abra-a antes de iniciar uma sessão de navegador. O VNC bruto na 5900 é deliberadamente não publicado; o x11vnc fica vinculado
ao localhost dentro do contêiner e acessível somente pela ponte noVNC.

Não há porta 5173 no Docker. O contêiner serve o frontend compilado a partir da mesma origem que a API,
e é por isso que `CORS_ORIGINS` aponta para `http://localhost:8000`.

### 4. Crie a sua conta

Registre-se pela UI em <http://localhost:8000>, ou pela linha de comando:

```bash
docker compose exec app python scripts/create_user.py --email you@example.com --name "Your Name"
```

Omita `--password` e você será solicitado por ela, para que fique fora do histórico do seu shell e da lista de processos.
A rota da API também funciona:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"a-long-password","full_name":"Your Name"}'
```

A senha precisa ter pelo menos 10 caracteres e no máximo 72 bytes (um limite do bcrypt). Contas novas começam em
modo de teste com aprovação manual obrigatória.

### Comandos Docker do dia a dia

O único serviço se chama `app`. Cada comando tem um atalho `make`.

```bash
docker compose logs -f            # acompanha os logs               (make docker-logs)
docker compose restart            # reinicia após uma mudança no .env
docker compose down               # para, mantém os dados           (make docker-down)
docker compose down -v            # para E APAGA o volume — destrói o seu banco e a sessão
docker compose exec app bash      # um shell dentro do contêiner
docker compose ps                 # status, incluindo o healthcheck
```

Mudanças de ambiente exigem um reinício, porque `get_settings()` fica em cache por processo.

O healthcheck consulta `/api/health` com um período de início de 60 segundos, já que o primeiro boot roda migrations e
inicia o Chromium. Um contêiner em `starting` por um minuto é normal.

### Chromium travando no Docker

Se o navegador morre na inicialização ou no meio de uma execução, é quase sempre memória compartilhada. O Chromium
aloca o heap do renderer em `/dev/shm`, e o padrão de 64 MB do Docker faz as abas travarem sem erro útil.
`docker-compose.yml` já define `shm_size: 1gb`; se ainda esbarrar nisso, aumente:

```yaml
services:
  app:
    shm_size: "2gb"
```

Depois `docker compose up -d --build`.

---

## Instalação local

### 1. Clone

```bash
git clone https://github.com/joaovictorgcu/smart-job-apply.git
cd smart-job-apply
```

### 2. Rode o script de setup

Os scripts criam um ambiente virtual, instalam as dependências de Python e Node, baixam o Chromium e
escrevem um `.env` inicial.

**Linux / macOS** — com `make`, os quatro comandos que levam do clone ao funcionamento são:

```bash
make install       # esta seção
make migrate       # passo 3, o schema
make user          # passo 5, a sua conta
make dev           # passo 4, os dois processos
```

`make help` lista todos os alvos. Sem `make`:

```bash
bash scripts/setup.sh
```

**Windows (PowerShell)**

```powershell
.\scripts\setup.ps1
```

Se o PowerShell se recusar a rodar o script, permita scripts locais apenas para esta sessão:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup.ps1
```

Prefere fazer à mão, ou o script falhou no meio? O equivalente manual vem a seguir.

### 3. Setup manual

**Crie e ative um ambiente virtual**

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Instale o backend**

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

Isto instala o pacote `app` em modo editável, então `import app.main` funciona de qualquer diretório.

**Instale o build do Chromium que o Playwright espera**

```bash
playwright install chromium
```

No Debian ou Ubuntu, puxe também as bibliotecas de sistema que o Chromium precisa:

```bash
playwright install --with-deps chromium
```

Esse comando usa `sudo` internamente. Se você preferir não, `playwright install-deps chromium` imprime
o que ele quer e você pode instalar os pacotes você mesmo.

**Instale o frontend**

```bash
cd frontend
npm ci
cd ..
```

`npm ci` instala exatamente o que `package-lock.json` especifica. Use `npm install` só quando você estiver
intencionalmente mudando dependências.

**Escreva o `.env`** na raiz do repositório:

```bash
cp .env.example .env
```

Diferente do caminho Docker, **defina `SECRET_KEY` e `ENCRYPTION_KEY` explicitamente aqui** — não há entrypoint
para gerá-los e persisti-los por você. Uma `SECRET_KEY` vazia significa uma nova aleatória por processo, o que desloga
você a cada reinício. Veja [configuration.md](configuration.md) para cada campo.

**Crie o schema do banco**

```bash
cd backend
alembic upgrade head
cd ..
```

`alembic.ini` vive em `backend/`, e é por isso que isto roda de lá. `make migrate` faz a mesma coisa
a partir da raiz do repositório.

Este é o caminho canônico e o que usar para qualquer coisa que você se importe. A aplicação também cria
tabelas faltantes na inicialização via `init_models()` como conveniência, mas as migrations são o que permite ao schema
evoluir sem perder dados.

### 4. Rode os dois processos

`make dev` roda ambos e para ambos no Ctrl-C. Caso contrário, dois terminais:

**Terminal 1 — backend**

```bash
.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend --port 8000
```

**Terminal 2 — frontend**

```bash
cd frontend
npm run dev
```

`--app-dir backend` coloca o pacote `app` no caminho de import, então isto funciona com ou sem o install
editável ter dado certo. Sobrescreva as portas com `BACKEND_PORT` e `FRONTEND_PORT` ao usar `make dev`.

Equivalentes em PowerShell — o cabeçalho do Makefile lista um para cada alvo:

```powershell
# Terminal 1
.venv\Scripts\python -m uvicorn app.main:app --reload --app-dir backend --port 8000
```

```powershell
# Terminal 2
cd frontend
npm run dev
```

### 5. Crie a sua conta

```bash
python scripts/create_user.py --email you@example.com --name "Your Name"
```

Ou `make user`. Omita `--password` e você será solicitado por ela, para que nunca alcance o histórico do seu shell ou a
lista de processos. Registrar-se pela UI também funciona.

### 6. Abra o app

| URL | O que é |
|---|---|
| <http://localhost:5173> | O painel (servidor de dev do Vite, com hot reload) |
| <http://localhost:8000/docs> | Docs OpenAPI ao vivo |
| <http://localhost:8000/api/health> | Verificação de saúde |

No modo local o navegador abre como uma janela real no seu desktop — não há noVNC nem porta 6080. Você
faz login no LinkedIn diretamente nessa janela.

---

## Notas por plataforma

### Windows

- Use PowerShell, não `cmd.exe`. O script de ativação é `.\.venv\Scripts\Activate.ps1`.
- Se `python` abrir a Microsoft Store, instale o Python de [python.org](https://www.python.org/downloads/)
  e marque "Add python.exe to PATH", ou use o launcher `py -3.12`.
- O suporte a caminhos longos importa: `node_modules` e o cache de navegadores do Playwright ambos aninham
  fundo. Habilite-o uma vez, num PowerShell elevado:

  ```powershell
  Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1
  ```

- No WSL2 não há display por padrão. Use o Docker com noVNC, ou use o WSLg no Windows 11.

### macOS

- O Python do Homebrew funciona: `brew install python@3.12 node`.
- O primeiro launch do Chromium pode pedir permissões. Permita.
- No Apple Silicon tudo roda nativamente; nenhum Rosetta necessário.

### Linux

- Instale o Python e o Node da sua distribuição ou de um gerenciador de versões.
- `playwright install --with-deps chromium` é a forma confiável de obter as bibliotecas compartilhadas. Uma faltante
  geralmente aparece como `error while loading shared libraries: libX...`.
- Num servidor headless, use o Docker. A automação precisa de um display para você logar e intervir.

---

## Trocando para PostgreSQL

O SQLite é o padrão e é suficiente para uma instalação auto-hospedada de um único usuário. Mude para o PostgreSQL se quiser
várias pessoas numa instância, ou backups tratados pelo seu ferramental de banco existente.

1. Instale o driver async:

   ```bash
   pip install -e ".[postgres]"
   ```

2. Crie o banco:

   ```bash
   createdb linkedin_auto_apply
   ```

3. Aponte `DATABASE_URL` para ele, no `.env`:

   ```dotenv
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/linkedin_auto_apply
   ```

   A parte `+asyncpg` é obrigatória. Uma URL `postgresql://` simples falha na criação do engine, porque o
   engine é async.

4. Crie o schema:

   ```bash
   cd backend && alembic upgrade head
   ```

Nenhuma mudança de código é necessária. `Base.type_annotation_map` normaliza datetimes em ambas as direções, então
o comportamento de timezone é idêntico em qualquer backend.

**Migrar dados existentes do SQLite** não é automatizado. Para um punhado de vagas e candidaturas, a abordagem
mais simples é começar do zero no PostgreSQL: recrie a sua conta, reenvie o seu currículo e reconecte o
LinkedIn. Se o histórico importa, faça dump e load das tabelas você mesmo com uma ferramenta como `pgloader` e
verifique que `linkedin_accounts.encrypted_storage_state` sobreviveu intacto.

---

## Atualizando

### Docker

```bash
git pull
docker compose down
docker compose up -d --build
docker compose logs -f            # acompanhe a migration rodar
```

O entrypoint aplica `alembic upgrade head` em todo boot, então não há passo de migration separado. Se uma
migration falhar, ele recorre a criar tabelas faltantes, deixa os dados existentes intactos e diz isso no
log — o que é a sua deixa para investigar em vez de continuar usando o contêiner.

O volume nomeado sobrevive a `docker compose down`, então os seus dados persistem. Nunca use `-v` a menos que você queira
destruí-lo.

### Local

```bash
git pull
pip install -e ".[dev]"            # pega mudanças de dependências
playwright install chromium        # caso o navegador fixado tenha mudado
cd frontend && npm ci && cd ..     # pega mudanças no lockfile
cd backend && alembic upgrade head && cd ..
```

Depois reinicie os dois processos.

**Leia as notas de release para mudanças de schema**, e faça um backup antes de migrar qualquer coisa que você se importe.

---

## Fazendo backup de `backend/data/`

Este diretório é o estado inteiro da sua instalação:

```text
backend/data/
├── app.db               # SQLite database (jobs, applications, encrypted session)
├── browser_profiles/    # Chromium profile directories
├── resumes/             # your uploaded CV files
├── screenshots/         # captures from the automation
└── .secrets.env         # Docker only: the generated SECRET_KEY and ENCRYPTION_KEY (chmod 600)
```

Ele está no gitignore, e contém cookies de sessão vivos do LinkedIn, o seu currículo e — no Docker — as chaves que
descriptografam a sessão. Faça backup em algum lugar onde você se sentiria confortável armazenando os três. Veja
[safety.md](safety.md#what-is-stored-and-where).

### Backup local

Pare o app primeiro, para que o SQLite não esteja no meio de uma escrita:

```bash
tar czf backup-$(date +%F).tar.gz backend/data
```

```powershell
Compress-Archive -Path backend\data -DestinationPath "backup-$(Get-Date -Format yyyy-MM-dd).zip"
```

Para fazer backup do banco enquanto o app está rodando, use o próprio comando de cópia consistente do SQLite em vez de
copiar o arquivo:

```bash
sqlite3 backend/data/app.db ".backup 'backup.db'"
```

### Backup no Docker

```bash
docker compose exec app tar czf - /app/backend/data > backup-$(date +%F).tar.gz
```

### Restaurando

Pare o app, substitua o diretório, inicie de novo.

**A sessão armazenada do LinkedIn só é legível com a mesma `ENCRYPTION_KEY`.** No Docker a chave fica
dentro do backup, em `.secrets.env`, então uma restauração de volume é autossuficiente. Numa instalação local a chave
vive no `.env` fora do diretório de dados — **restaure o `.env` junto**, ou você terá que reconectar o
LinkedIn e fazer login de novo. Todo o resto no backup ainda funciona de qualquer forma.

---

## Verificando a instalação

```bash
curl http://localhost:8000/api/health
# {"status":"ok","version":"0.1.0"}
```

```bash
make test              # backend tests, all offline (or: pytest)
make lint              # ruff check .
cd frontend && npm run typecheck
```

Se os testes passarem, a instalação está sólida. Continue com o passo a passo da primeira execução no
[README](../README.md#first-run-walkthrough).

---

## Solução de problemas

| Sintoma | Causa e correção |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Rode o uvicorn com `--app-dir backend`, ou rode de novo `pip install -e ".[dev]"` com a venv ativada. |
| `SettingsError: error parsing value for field "cors_origins"` | Uma configuração de lista ou tupla no `.env` não é JSON. Escreva `CORS_ORIGINS=["http://localhost:5173"]` e `DEFAULT_ACTION_DELAY_RANGE=[2.5, 7.0]`. Veja [configuration.md](configuration.md#automation). |
| `Executable doesn't exist at ...ms-playwright...` | `playwright install chromium` nunca foi rodado, ou rodou num ambiente diferente. |
| `error while loading shared libraries: libnss3.so` (Linux) | Bibliotecas de sistema faltando: `playwright install --with-deps chromium`. |
| O Chromium inicia e morre na hora (Docker) | `/dev/shm` pequeno demais. O Compose define `shm_size: 1gb`; aumente para `2gb`. |
| O navegador abre mas o LinkedIn mostra uma página de login toda vez | A sessão não está sendo persistida, ou `ENCRYPTION_KEY` mudou. Reconecte o LinkedIn e faça login mais uma vez. |
| "Could not decrypt stored data" | `ENCRYPTION_KEY` (ou `SECRET_KEY`, quando a primeira não está definida) mudou. Restaure o valor antigo, ou reconecte o LinkedIn. |
| Deslogado do painel a cada reinício | `SECRET_KEY` não está definida, então uma nova aleatória é gerada a cada início. Defina-a no `.env` (só instalações locais — o Docker persiste uma gerada). |
| O frontend carrega mas toda requisição falha com erro de CORS | A origem do painel não está em `CORS_ORIGINS`. Adicione-a como uma entrada de array JSON e reinicie. |
| `sqlite3.OperationalError: database is locked` | Dois processos escrevendo ao mesmo tempo. O modo WAL está habilitado exatamente para isso, então verifique se há um `uvicorn` perdido ainda rodando. |
| Porta 8000 ou 5173 já em uso | Algo mais está nela. `BACKEND_PORT=8100 make dev`, ou mude o mapeamento de portas do compose. |
| A página do noVNC está em branco na :6080 | O contêiner ainda está iniciando. Dê um momento, depois verifique `docker compose logs`. |
