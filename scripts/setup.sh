#!/usr/bin/env bash
# One-shot development setup for Linux and macOS. Safe to re-run: nothing that
# already exists is recreated, and an existing .env is never overwritten.
#
# Windows: use scripts/setup.ps1 instead.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

VENV_DIR="${REPO_ROOT}/.venv"
ENV_FILE="${REPO_ROOT}/.env"
ENV_TEMPLATE="${REPO_ROOT}/.env.example"
MIN_PY_MAJOR=3
MIN_PY_MINOR=11

step() { printf '\n==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
step "Checking Python"
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        if "${candidate}" -c "import sys; sys.exit(0 if sys.version_info >= (${MIN_PY_MAJOR}, ${MIN_PY_MINOR}) else 1)" 2>/dev/null; then
            PYTHON_BIN="${candidate}"
            break
        fi
    fi
done

if [[ -z "${PYTHON_BIN}" ]]; then
    die "Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR} or newer is required but was not found.
       Install it (e.g. 'brew install python@3.12' or your distribution's
       python3.12 package) and run this script again."
fi
info "using $(${PYTHON_BIN} --version) at $(command -v "${PYTHON_BIN}")"

# ---------------------------------------------------------------------------
# Virtual environment and backend dependencies
# ---------------------------------------------------------------------------
step "Creating the virtual environment"
if [[ -d "${VENV_DIR}" ]]; then
    info ".venv already exists, reusing it"
else
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    info "created .venv"
fi

VENV_PY="${VENV_DIR}/bin/python"
[[ -x "${VENV_PY}" ]] || die "The virtual environment looks broken: ${VENV_PY} is missing.
       Delete .venv and run this script again."

step "Installing the backend (this takes a minute)"
"${VENV_PY}" -m pip install --upgrade pip >/dev/null
"${VENV_PY}" -m pip install -e ".[dev]"

step "Installing the Chromium build Playwright drives"
"${VENV_PY}" -m playwright install chromium
# --with-deps needs root, so it is not attempted here. If Chromium fails to
# start later, run: sudo .venv/bin/python -m playwright install-deps chromium

# ---------------------------------------------------------------------------
# Frontend dependencies
# ---------------------------------------------------------------------------
step "Installing the frontend"
if ! command -v npm >/dev/null 2>&1; then
    info "npm was not found — skipping. Install Node.js 20+ from https://nodejs.org"
    info "and then run: cd frontend && npm install"
elif [[ ! -f "${REPO_ROOT}/frontend/package.json" ]]; then
    info "frontend/package.json does not exist yet — skipping"
else
    (cd "${REPO_ROOT}/frontend" && npm install --no-audit --no-fund)
fi

# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------
step "Preparing .env"
if [[ -f "${ENV_FILE}" ]]; then
    info ".env already exists, leaving it untouched"
else
    [[ -f "${ENV_TEMPLATE}" ]] || die "${ENV_TEMPLATE} is missing; cannot create .env."
    cp "${ENV_TEMPLATE}" "${ENV_FILE}"
    # Fill in the two keys that must never be a shared default. Done in Python
    # because in-place sed is not portable between GNU and BSD.
    "${VENV_PY}" - "${ENV_FILE}" <<'PYTHON'
import re
import secrets
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    content = handle.read()

for key in ("SECRET_KEY", "ENCRYPTION_KEY"):
    content = re.sub(
        rf"^{key}=.*$",
        f"{key}={secrets.token_urlsafe(48)}",
        content,
        count=1,
        flags=re.MULTILINE,
    )

with open(path, "w", encoding="utf-8") as handle:
    handle.write(content)
PYTHON
    chmod 600 "${ENV_FILE}"
    info "created .env with a fresh SECRET_KEY and ENCRYPTION_KEY"
fi

# ---------------------------------------------------------------------------
# What to do next
# ---------------------------------------------------------------------------
cat <<'NEXT'

Setup finished. Three things left:

  1. Add your Anthropic API key to .env
         ANTHROPIC_API_KEY=sk-ant-...
     Get one at https://console.anthropic.com/

  2. Create the database and an account
         make migrate
         make user

  3. Start the app
         make dev
     Backend  http://localhost:8000   (API docs at /docs)
     Frontend http://localhost:5173

Then, inside the app, open the browser session and sign in to LinkedIn by hand.
Only the session cookies are stored, encrypted; your LinkedIn password never is.

Nothing is ever submitted without you confirming it explicitly.
NEXT
