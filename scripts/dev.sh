#!/usr/bin/env bash
# Run the API and the Vite dev server side by side. Ctrl-C stops both.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

VENV_PY="${REPO_ROOT}/.venv/bin/python"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

if [[ ! -x "${VENV_PY}" ]]; then
    printf 'ERROR: .venv is missing. Run: make install\n' >&2
    exit 1
fi

backend_pid=""
frontend_pid=""

# Forward the interrupt to both children, then wait for them to exit so the
# terminal is not left with a half-dead uvicorn holding port 8000.
shutdown() {
    trap - INT TERM
    printf '\nStopping...\n'
    for pid in "${backend_pid}" "${frontend_pid}"; do
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            kill -INT "${pid}" 2>/dev/null || true
        fi
    done
    for pid in "${backend_pid}" "${frontend_pid}"; do
        [[ -n "${pid}" ]] && wait "${pid}" 2>/dev/null || true
    done
    exit 0
}
trap shutdown INT TERM

printf '==> backend  http://localhost:%s  (docs at /docs)\n' "${BACKEND_PORT}"
"${VENV_PY}" -m uvicorn app.main:app \
    --reload \
    --app-dir backend \
    --host 127.0.0.1 \
    --port "${BACKEND_PORT}" &
backend_pid=$!

if [[ -f "${REPO_ROOT}/frontend/package.json" ]]; then
    printf '==> frontend http://localhost:%s\n' "${FRONTEND_PORT}"
    (cd "${REPO_ROOT}/frontend" && npm run dev -- --port "${FRONTEND_PORT}") &
    frontend_pid=$!
else
    printf '==> frontend skipped (frontend/package.json does not exist yet)\n'
fi

# Exit as soon as either process dies, so a crashed backend is not hidden behind
# a still-running Vite server.
while true; do
    for pid in "${backend_pid}" "${frontend_pid}"; do
        if [[ -n "${pid}" ]] && ! kill -0 "${pid}" 2>/dev/null; then
            printf '\nA process exited; shutting the other one down.\n'
            shutdown
        fi
    done
    sleep 1
done
