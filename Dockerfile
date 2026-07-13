# Multi-Stage Dockerfile für Agora.
#
# Targets:
#   dev   — Default, identisch mit der ursprünglichen Single-Stage-Variante.
#           Enthält Bun + uv + alle Dev-Dependencies, lädt das Repo per
#           Bind-Mount und startet `bun run dev` (Vite + Flask).
#   prod  — schlanke Runtime: gebautes Frontend-Bundle, gunicorn vor Flask.
#           Kein Vite, kein Bun, kein curl, kein Bind-Mount erwartet.
#
# Auswahl im Compose über `target: dev` / `target: prod`. Default-
# Compose nutzt `dev`. Für Produktions-Setups siehe
# `docker-compose.prod.yml`.

# ---------- shared base ----------
FROM python:3.14@sha256:09b29c360b84742bf98eba40b214f7f6b4b53286bb2c8a8b5b1afa188a8d9c0e AS base

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl unzip \
  && rm -rf /var/lib/apt/lists/*

COPY --from=oven/bun:1 /usr/local/bin/bun /usr/local/bin/bun
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

# Große CUDA-Wheels (cudnn ~700 MB, nvshmem ~300 MB) sprengen den
# uv-Default von 30 s auf langsamen Leitungen.
ENV UV_HTTP_TIMEOUT=1800
ENV UV_HTTP_RETRIES=5

ENV TZ=Europe/Berlin

WORKDIR /app
RUN useradd -m -u 1000 agora \
  && mkdir -p /app/backend/uploads /app/backend/logs \
  && chown -R agora:agora /app

# ---------- dev (default) ----------
FROM base AS dev

COPY --chown=agora:agora package.json bun.lock ./
COPY --chown=agora:agora frontend/package.json frontend/bun.lock ./frontend/
COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock ./backend/

RUN bun install --frozen-lockfile \
  && bun install --frozen-lockfile --cwd frontend \
  && cd backend && uv sync --frozen \
  && chown -R agora:agora /app

COPY --chown=agora:agora . .

USER agora

ENV FLASK_HOST=0.0.0.0

EXPOSE 5173 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5001/readyz || exit 1

CMD ["bun", "run", "dev"]

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
# Build-Provenance-Marker (Design-Language-Version).
# Wird in main.ts als `import.meta.env.VITE_UI_VERSION` ausgelesen und
# auf `window.__AGORA_UI_VERSION__` gespiegelt. Sichtbar in Browser-DevTools,
# damit Rollouts/Rollbacks ohne Bundle-Hash-Vergleich identifizierbar sind.
ARG VITE_UI_VERSION="v4"
# ENV VITE_AGORA_TOKEN wird bewusst NICHT gesetzt — ein ENV-Befehl würde
# den ARG-Wert im RUN-Block überschreiben und das Gate wäre wirkungslos.
# Vite liest VITE_* zur Build-Zeit aus dem Shell-Kontext von bun run build;
# die /tmp/.vite_token_env-Datei speist den korrekten Wert ein.
RUN _token="${VITE_AGORA_TOKEN:-}" && \
    if [ "$ALLOW_BUILD_TIME_TOKEN" = "true" ] && [ -n "$_token" ]; then \
      echo "ALLOW_BUILD_TIME_TOKEN=true: VITE_AGORA_TOKEN wird ins Bundle einkompiliert."; \
      printf 'VITE_AGORA_TOKEN=%s\n' "$_token" > /tmp/.vite_token_env; \
    else \
      echo "ALLOW_BUILD_TIME_TOKEN=false (Default): Frontend-Bundle bekommt leeren Token. Runtime-Login erforderlich."; \
      echo "VITE_AGORA_TOKEN=" > /tmp/.vite_token_env; \
    fi && \
    printf 'VITE_UI_VERSION=%s\n' "${VITE_UI_VERSION:-v4}" >> /tmp/.vite_token_env && \
    echo "VITE_UI_VERSION=${VITE_UI_VERSION:-v4} (Build-Provenance)."

COPY --chown=agora:agora frontend/package.json frontend/bun.lock ./frontend/
RUN cd frontend && bun install --frozen-lockfile

COPY --chown=agora:agora frontend/ ./frontend/
RUN export $(cat /tmp/.vite_token_env) && rm /tmp/.vite_token_env && \
    cd frontend && bun run build

# ---------- backend-build (production Python environment only) ----------
FROM base AS backend-build

COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock ./backend/
# Backend-Dependencies ohne Dev-Group und strikt aus uv.lock installieren.
RUN cd backend && uv sync --frozen --no-dev \
  && chown -R agora:agora /app

# ---------- prod ----------
FROM python:3.14-slim@sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1 AS prod

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_HOST=0.0.0.0 \
    PATH="/app/backend/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends tzdata \
  && rm -rf /var/lib/apt/lists/* \
  && ln -snf /usr/share/zoneinfo/Europe/Berlin /etc/localtime \
  && echo "Europe/Berlin" > /etc/timezone

ENV TZ=Europe/Berlin

RUN useradd -m -u 1000 -s /usr/sbin/nologin agora \
  && mkdir -p /app/backend/uploads /app/backend/logs /app/frontend/dist /home/agora/.cache /home/agora/.gunicorn \
  && chown -R agora:agora /app /home/agora

COPY --chown=agora:agora --from=backend-build /app/backend/.venv ./backend/.venv
COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock backend/run.py backend/wsgi.py backend/gunicorn.conf.py ./backend/
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
  CMD ["python", "-c", "import sys; from urllib.request import urlopen; sys.exit(0 if urlopen('http://localhost:5001/readyz', timeout=5).status == 200 else 1)"]

# Gunicorn vor Flask mit gevent-Worker (non-blocking SSE).
# Direkter Binary-Aufruf statt `uv run` — `uv run` würde bei jedem
# Container-Start einen `.venv`-Sync versuchen und am read-only Rootfs
# scheitern.
#
# Konfiguration (workers, preload, timeouts, post_fork-Hook) liegt in
# backend/gunicorn.conf.py. Der post_fork-Hook resetet vererbte
# Neo4j/Redis-Pool-Sockets im Child — siehe Datei-Header dort. Damit ist
# --preload auch unter -k gevent sicher; os.register_at_fork allein war
# es nicht (gevent monkey-patcht os.fork).
#
# HARDSTOP --workers 1 (Code-Review 2026-05-17, Finding 1.2) bleibt
# bestehen, ist aber jetzt in der conf-Py dokumentiert.
#
# Issue #529: App-Target ist wsgi:app (NICHT mehr app:create_app()), weil
# wsgi.py als allererstes Statement gevent.monkey.patch_all() ausführt.
# Ohne diese Reihenfolge importiert --preload requests/urllib3/ssl mit
# ungepatchtem socket → RecursionError in jedem HTTP-Call.
CMD ["/app/backend/.venv/bin/gunicorn", \
     "--config", "/app/backend/gunicorn.conf.py", \
     "wsgi:app"]

# ---------- proxy (nginx-Sidecar mit eingebackenem Frontend-Bundle) ----------
FROM nginx:alpine@sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa AS proxy
# Alpine-Pakete auf Repo-Stand heben, solange das Base-Image hinterherhinkt:
# CVE-2026-33630 (c-ares < 1.34.8-r0), CVE-2026-56407/-56408/-56131
# (libexpat < 2.8.2-r0) — Trivy-Gate scannt HIGH/CRITICAL mit exit-code 1.
RUN apk upgrade --no-cache
COPY deploy/nginx/agora.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html
