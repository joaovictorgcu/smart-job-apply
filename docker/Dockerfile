# syntax=docker/dockerfile:1
#
# Single image that runs everything: the FastAPI backend, the built frontend, a
# virtual X display, and a noVNC bridge so you can open the automated browser in
# your own browser and log in to LinkedIn by hand.
#
# Build from the repository root:
#     docker build -f docker/Dockerfile -t linkedin-auto-apply .

# -----------------------------------------------------------------------------
# Stage 1 — build the frontend
# -----------------------------------------------------------------------------
FROM node:22-slim AS frontend

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
# `npm ci` is the reproducible path; fall back to `npm install` when the lockfile
# is not yet in sync with package.json so a fresh clone still builds.
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# -----------------------------------------------------------------------------
# Stage 2 — runtime
# -----------------------------------------------------------------------------
# The Playwright image already ships Chromium and every system library it needs,
# which is the hard part of running a real browser in a container.
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/backend \
    DISPLAY=:99 \
    DATA_DIR=/app/backend/data

# Virtual display + VNC + the websocket bridge noVNC needs, and supervisor to
# keep the four processes alive.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        xvfb \
        x11vnc \
        novnc \
        websockify \
        supervisor \
        tini \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix \
 # noVNC ships its client as vnc.html; make "/" open the viewer directly.
 && ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html

WORKDIR /app

# Install the Python dependencies before the source is copied so that editing
# the backend does not invalidate this layer. The stub package exists only so
# the editable install can resolve project metadata; the real code lands below
# at the same path and the editable path hook picks it up.
COPY pyproject.toml README.md ./
RUN mkdir -p backend/app \
 && touch backend/app/__init__.py \
 && pip install --no-cache-dir -e ".[postgres]"

COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
# Replaces the distribution default outright, so there is exactly one
# supervisord configuration in the image.
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf

# Runs unprivileged. The data directory holds the database, the encrypted
# LinkedIn session and the user's resumes, so it must be writable by this user;
# it is also where the named volume is mounted at run time.
RUN useradd --create-home --shell /bin/bash --uid 10001 appuser \
 && chmod +x /usr/local/bin/entrypoint.sh \
 && mkdir -p /app/backend/data /var/log/supervisor \
 && chown -R appuser:appuser /app /var/log/supervisor

USER appuser

# 8000 = application (API + frontend). 6080 = noVNC, where you log in manually.
EXPOSE 8000 6080

# tini reaps the browser processes Playwright leaves behind.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
