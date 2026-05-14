# Multi-Stage Dockerfile für Agora.
#
# Targets:
#   dev   — Default, identisch mit der ursprünglichen Single-Stage-Variante.
#           Enthält Node + uv + alle Dev-Dependencies, lädt das Repo per
#           Bind-Mount und startet `npm run dev` (Vite + Flask).
#   prod  — schlanke Runtime: gebautes Frontend-Bundle, gunicorn vor Flask.
#           Kein Vite, kein npm, kein curl, kein Bind-Mount erwartet.
#
# Auswahl im Compose über `target: dev` / `target: prod`. Default-
# Compose nutzt `dev`. Für Produktions-Setups siehe
# `docker-compose.prod.yml`.

# ---------- shared base ----------
FROM python:3.14 AS base

RUN apt-get update \
  && apt-get install -y --no-install-recommends nodejs npm curl \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

# Große CUDA-Wheels (cudnn ~700 MB, nvshmem ~300 MB) sprengen den
# uv-Default von 30 s auf langsamen Leitungen.
ENV UV_HTTP_TIMEOUT=1800
ENV UV_HTTP_RETRIES=5

WORKDIR /app
RUN useradd -m -u 1000 agora \
  && mkdir -p /app/backend/uploads /app/backend/logs \
  && chown -R agora:agora /app

# ---------- dev (default) ----------
FROM base AS dev

COPY --chown=agora:agora package.json package-lock.json ./
COPY --chown=agora:agora frontend/package.json frontend/package-lock.json ./frontend/
COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock ./backend/

RUN npm ci \
  && npm ci --prefix frontend \
  && cd backend && uv sync --frozen \
  && chown -R agora:agora /app

COPY --chown=agora:agora . .

USER agora

ENV FLASK_HOST=0.0.0.0

EXPOSE 5173 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5001/health || exit 1

CMD ["npm", "run", "dev"]

# ---------- frontend-build (frontend bundle only) ----------
FROM base AS frontend-build

# Build-Time-Token-Gate (F2.1, Sub-Slice 46).
#
# Default: ALLOW_BUILD_TIME_TOKEN=false → der Build ignoriert
# VITE_AGORA_TOKEN, das Frontend-Bundle bekommt einen LEEREN Token-Wert
# einkompiliert. Das Frontend muss den Token zur Laufzeit per
# setAgoraToken() setzen (siehe frontend/src/api/index.ts und das
# UI-Eingabefeld in der App).
#
# Opt-In: ALLOW_BUILD_TIME_TOKEN=true erlaubt das Einbrennen des Tokens
# ins Bundle. Nur sinnvoll für Single-User-Tailnet-Deploys. Caveat:
# wer das Bundle hat, hat den Token. Niemals fuer Public-Internet-Deploys.
#
# Aufruf:
#   docker build --target frontend-build \
#     --build-arg ALLOW_BUILD_TIME_TOKEN=true \
#     --build-arg VITE_AGORA_TOKEN=<token> .
ARG ALLOW_BUILD_TIME_TOKEN=false
ARG VITE_AGORA_TOKEN=""
# ENV VITE_AGORA_TOKEN wird bewusst NICHT gesetzt — ein ENV-Befehl würde
# den ARG-Wert im RUN-Block überschreiben und das Gate wäre wirkungslos.
# Vite liest VITE_* zur Build-Zeit aus dem Shell-Kontext von npm run build;
# die /tmp/.vite_token_env-Datei speist den korrekten Wert ein.
RUN _token="${VITE_AGORA_TOKEN:-}" && \
    if [ "$ALLOW_BUILD_TIME_TOKEN" = "true" ] && [ -n "$_token" ]; then \
      echo "ALLOW_BUILD_TIME_TOKEN=true: VITE_AGORA_TOKEN wird ins Bundle einkompiliert."; \
      printf 'VITE_AGORA_TOKEN=%s\n' "$_token" > /tmp/.vite_token_env; \
    else \
      echo "ALLOW_BUILD_TIME_TOKEN=false (Default): Frontend-Bundle bekommt leeren Token. Runtime-Login erforderlich."; \
      echo "VITE_AGORA_TOKEN=" > /tmp/.vite_token_env; \
    fi

COPY --chown=agora:agora frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

COPY --chown=agora:agora frontend/ ./frontend/
RUN export $(cat /tmp/.vite_token_env) && rm /tmp/.vite_token_env && \
    cd frontend && npm run build

# ---------- backend-build (production Python environment only) ----------
FROM base AS backend-build

COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock ./backend/
# Backend-Dependencies ohne Dev-Group und strikt aus uv.lock installieren.
RUN cd backend && uv sync --frozen --no-dev \
  && chown -R agora:agora /app

# ---------- prod ----------
FROM python:3.14-slim AS prod

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_HOST=0.0.0.0 \
    PATH="/app/backend/.venv/bin:$PATH"

WORKDIR /app

RUN useradd -m -u 1000 -s /usr/sbin/nologin agora \
  && mkdir -p /app/backend/uploads /app/backend/logs /app/frontend/dist /home/agora/.cache /home/agora/.gunicorn \
  && chown -R agora:agora /app /home/agora

COPY --chown=agora:agora --from=backend-build /app/backend/.venv ./backend/.venv
COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock backend/run.py ./backend/
COPY --chown=agora:agora backend/app ./backend/app
COPY --chown=agora:agora backend/scripts ./backend/scripts
# E2E-Stub-Snapshot: llm_e2e_stub.py liest die Pflichtabschnitte aus dieser Datei.
# Der Fallback in _eleven_required_sections() greift wenn die Datei fehlt, aber
# die Primär-Quelle liegt hier — damit sind Snapshot-Drift-Tests (M11.8b) auch
# im prod-Image möglich (z. B. via /api/status-Erweiterungen).
COPY --chown=agora:agora backend/tests/eval/snapshots ./backend/tests/eval/snapshots
COPY --chown=agora:agora --from=frontend-build /app/frontend/dist ./frontend/dist

USER agora

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://localhost:5001/health', timeout=5).read()"]

# Gunicorn vor Flask mit gevent-Worker (non-blocking SSE).
# Direkter Binary-Aufruf statt `uv run` — `uv run` würde bei jedem
# Container-Start einen `.venv`-Sync versuchen und am read-only Rootfs
# scheitern.
CMD ["/app/backend/.venv/bin/gunicorn", \
     "-k", "gevent", \
     "--workers", "2", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--bind", "0.0.0.0:5001", \
     "--chdir", "/app/backend", \
     "--pid", "/home/agora/.gunicorn/gunicorn.pid", \
     "app:create_app()"]
