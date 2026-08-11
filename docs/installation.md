# Installation

Two supported paths. **Docker** is recommended — it pins Chromium and its system libraries, which is the
part of a local install most likely to go wrong. **Local** is better if you want to hack on the code.

Read [safety.md](safety.md) before you run anything.

---

## Prerequisites

### Docker path

| Requirement | Notes |
|---|---|
| Docker Engine 24+ with Compose v2 | `docker compose version` should print `v2.x`. Docker Desktop on Windows and macOS includes it. |
| ~3 GB free disk | Mostly the Chromium layer. |
| ~2 GB free RAM | Chromium needs headroom; see the `shm_size` note below. |
| An Anthropic API key | Optional but the point of the project. [console.anthropic.com](https://console.anthropic.com/) → API keys. |

### Local path

| Requirement | Notes |
|---|---|
| Python 3.11 or 3.12 | `python --version`. 3.13 is not covered by CI. |
| Node.js 20+ and npm | For the frontend. `node --version` |
| Git | |
| A desktop session | The browser must be visible for you to log into LinkedIn. On a headless Linux server, use the Docker path — it provides a virtual display. |
| An Anthropic API key | As above. |

---

## Docker

### 1. Clone and configure

```bash
git clone https://github.com/joaovictorgcu/smart-job-apply.git
cd smart-job-apply
```

Create `.env` in the repository root:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
SECRET_KEY=<generated below>
ENCRYPTION_KEY=<generated below, different value>
```

Generate the two keys — run this twice and use a different value for each:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

No Python on the host? `openssl rand -base64 48` works, as does
`docker run --rm python:3.12-alpine python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Every other variable in [configuration.md](configuration.md) can go in the same file.

### 2. Build and start

```bash
docker compose up -d --build
```

The first build takes several minutes; Chromium is large. Then:

```bash
docker compose ps          # all services should be running
docker compose logs -f     # follow startup, Ctrl-C to detach
```

### 3. Open the two URLs

| URL | What it is |
|---|---|
| <http://localhost:8000> | The app. API docs at <http://localhost:8000/docs>, health at <http://localhost:8000/api/health> |
| <http://localhost:6080> | **noVNC — the browser's screen.** This is where you log into LinkedIn. |

The noVNC window is not optional. Chromium runs inside the container on a virtual display, and the only way
to see it — to log in, to solve a security challenge, to watch a form being filled — is through that URL.
Open it before you start a browser session.

### 4. Create your account

Register through the UI, or from the command line:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"a-long-password","full_name":"Your Name"}'
```

The password must be at least 10 characters and at most 72 bytes (a bcrypt limit).

### Everyday Docker commands

```bash
docker compose logs -f              # follow all logs
docker compose restart              # restart after an .env change
docker compose down                 # stop, keep data
docker compose down -v              # stop and delete volumes — destroys your database
docker compose exec backend bash    # a shell inside the backend container
```

Environment changes require a restart, because `get_settings()` is cached per process.

### Chromium crashing in Docker

If the browser dies on startup or partway through a run, it is almost always shared memory. Chromium's
default `/dev/shm` inside a container is 64 MB, which is not enough. The compose file sets a larger
`shm_size`; if you hit it anyway, raise it:

```yaml
services:
  backend:
    shm_size: "2gb"
```

Then `docker compose up -d --build`.

---

## Local install

### 1. Clone

```bash
git clone https://github.com/joaovictorgcu/smart-job-apply.git
cd smart-job-apply
```

### 2. Run the setup script

The scripts create a virtual environment, install the Python and Node dependencies, download Chromium, and
write a starter `.env`.

**Linux / macOS**

```bash
bash scripts/setup.sh
```

**Windows (PowerShell)**

```powershell
.\scripts\setup.ps1
```

If PowerShell refuses to run the script, allow local scripts for this session only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup.ps1
```

Prefer to do it by hand, or the script failed partway? The manual equivalent is next.

### 3. Manual setup

**Create and activate a virtual environment**

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

**Install the backend**

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

This installs the `app` package in editable mode, so `import app.main` works from any directory.

**Install the Chromium build Playwright expects**

```bash
playwright install chromium
```

On Debian or Ubuntu, also pull the system libraries Chromium needs:

```bash
playwright install --with-deps chromium
```

That command uses `sudo` internally. If you would rather not, `playwright install-deps chromium` prints
what it wants and you can install the packages yourself.

**Install the frontend**

```bash
cd frontend
npm ci
cd ..
```

`npm ci` installs exactly what `package-lock.json` specifies. Use `npm install` only when you are
intentionally changing dependencies.

**Write `.env`** in the repository root — same contents as the Docker path above. See
[configuration.md](configuration.md) for every field.

**Create the database schema**

```bash
cd backend
alembic upgrade head
cd ..
```

This is the canonical path and the one to use for anything you care about. The application also creates
missing tables on startup via `init_models()` as a convenience, but migrations are what let the schema
evolve without losing data.

### 4. Run both processes

Two terminals, or `make dev` if `make` is available on your machine.

**Terminal 1 — backend**

```bash
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend**

```bash
cd frontend
npm run dev
```

PowerShell equivalents, with the venv activated in each window:

```powershell
# Terminal 1
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

```powershell
# Terminal 2
cd frontend
npm run dev
```

### 5. Open the app

| URL | What it is |
|---|---|
| <http://localhost:5173> | The dashboard (Vite dev server, with hot reload) |
| <http://localhost:8000/docs> | Live OpenAPI docs |
| <http://localhost:8000/api/health> | Health check |

In local mode the browser opens as a real window on your desktop — there is no noVNC and no port 6080. You
log into LinkedIn in that window directly.

### 6. Create your account

Register in the UI at <http://localhost:5173>, or with the `curl` call shown in the Docker section.

---

## Platform notes

### Windows

- Use PowerShell, not `cmd.exe`. The activation script is `.\.venv\Scripts\Activate.ps1`.
- If `python` opens the Microsoft Store, install Python from [python.org](https://www.python.org/downloads/)
  and tick "Add python.exe to PATH", or use the `py -3.12` launcher.
- Long-path support matters: `node_modules` and the Playwright browser cache both nest deeply. Enable it
  once, in an elevated PowerShell:

  ```powershell
  Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1
  ```

- Under WSL2 there is no display by default. Either use Docker with noVNC, or use WSLg on Windows 11.

### macOS

- Homebrew Python works: `brew install python@3.12 node`.
- The first Chromium launch may prompt for permissions. Allow it.
- On Apple Silicon everything runs natively; no Rosetta needed.

### Linux

- Install Python and Node from your distribution or a version manager.
- `playwright install --with-deps chromium` is the reliable way to get the shared libraries. A missing one
  usually surfaces as `error while loading shared libraries: libX...`.
- On a headless server, use Docker. The automation needs a display for you to log in and intervene.

---

## Switching to PostgreSQL

SQLite is the default and is enough for a self-hosted single-user install. Move to PostgreSQL if you want
several people on one instance, or backups handled by your existing database tooling.

1. Install the async driver:

   ```bash
   pip install -e ".[postgres]"
   ```

2. Create the database:

   ```bash
   createdb linkedin_auto_apply
   ```

3. Point `DATABASE_URL` at it, in `.env`:

   ```dotenv
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/linkedin_auto_apply
   ```

   The `+asyncpg` part is required. A plain `postgresql://` URL fails at engine creation, because the
   engine is async.

4. Create the schema:

   ```bash
   cd backend && alembic upgrade head
   ```

No code changes are needed. `Base.type_annotation_map` normalizes datetimes in both directions, so
timezone behavior is identical on either backend.

**Migrating existing SQLite data** is not automated. For a handful of jobs and applications, the simplest
approach is to start fresh on PostgreSQL: re-create your account, re-upload your CV, and reconnect
LinkedIn. If the history matters, dump and load the tables yourself with a tool such as `pgloader` and
verify that `linkedin_accounts.encrypted_storage_state` survived intact.

---

## Upgrading

### Docker

```bash
git pull
docker compose down
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

Named volumes survive `docker compose down`, so your data persists. Never use `-v` unless you mean to
delete it.

### Local

```bash
git pull
pip install -e ".[dev]"            # picks up dependency changes
playwright install chromium        # in case the pinned browser moved
cd frontend && npm ci && cd ..     # picks up lockfile changes
cd backend && alembic upgrade head && cd ..
```

Then restart both processes.

**Read the release notes for schema changes**, and take a backup before migrating anything you care about.

---

## Backing up `backend/data/`

This directory is the entire state of your installation:

```text
backend/data/
├── app.db               # SQLite database (jobs, applications, encrypted session)
├── browser_profiles/    # Chromium profile directories
└── resumes/             # your uploaded CV files
```

It is gitignored, and it contains live LinkedIn session cookies and your CV. Back it up somewhere you would
be comfortable storing both. See [safety.md](safety.md#what-is-stored-and-where).

### Local backup

Stop the app first, so SQLite is not mid-write:

```bash
tar czf backup-$(date +%F).tar.gz backend/data
```

```powershell
Compress-Archive -Path backend\data -DestinationPath "backup-$(Get-Date -Format yyyy-MM-dd).zip"
```

To back up the database while the app is running, use SQLite's own consistent-copy command instead of
copying the file:

```bash
sqlite3 backend/data/app.db ".backup 'backup.db'"
```

### Docker backup

```bash
docker compose exec backend tar czf - /app/backend/data > backup-$(date +%F).tar.gz
```

### Restoring

Stop the app, replace the directory, start it again. **Restore `.env` alongside it** — specifically the same
`ENCRYPTION_KEY`. With a different key the stored LinkedIn session cannot be decrypted, and you will have
to reconnect and log in again. Everything else in the backup still works.

---

## Verifying the install

```bash
curl http://localhost:8000/api/health
# {"status":"ok","version":"0.1.0"}
```

```bash
pytest                 # backend tests, all offline
ruff check .           # lint
cd frontend && npm run typecheck
```

If the tests pass, the install is sound. Continue with the first-run walkthrough in the
[README](../README.md#first-run-walkthrough).

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | The editable install did not happen, or the venv is not active. Re-run `pip install -e ".[dev]"` with the venv activated. |
| `SettingsError: error parsing value for field "cors_origins"` | A list or tuple setting in `.env` is not JSON. Write `CORS_ORIGINS=["http://localhost:5173"]` and `DEFAULT_ACTION_DELAY_RANGE=[2.5, 7.0]`. See [configuration.md](configuration.md#automation). |
| `Executable doesn't exist at ...ms-playwright...` | `playwright install chromium` was never run, or ran in a different environment. |
| `error while loading shared libraries: libnss3.so` (Linux) | Missing system libraries: `playwright install --with-deps chromium`. |
| Chromium starts and immediately dies (Docker) | `/dev/shm` too small. Raise `shm_size` to `2gb`. |
| Browser opens but LinkedIn shows a login page every time | The session is not being persisted, or `ENCRYPTION_KEY` changed. Reconnect LinkedIn and log in once more. |
| "Could not decrypt stored data" | `ENCRYPTION_KEY` (or `SECRET_KEY`, when the former is unset) changed. Restore the old value, or reconnect LinkedIn. |
| Logged out of the dashboard after every restart | `SECRET_KEY` is unset, so a new random one is generated each start. Set it in `.env`. |
| Frontend loads but every request fails with a CORS error | The dashboard's origin is not in `CORS_ORIGINS`. Add it as a JSON array entry and restart. |
| `sqlite3.OperationalError: database is locked` | Two processes writing at once. WAL mode is enabled for exactly this, so check for a stray `uvicorn` still running. |
| Port 8000 or 5173 already in use | Something else is on it. `uvicorn app.main:app --port 8100`, or change the compose port mapping. |
| noVNC page is blank at :6080 | The container is still starting. Give it a moment, then check `docker compose logs`. |
