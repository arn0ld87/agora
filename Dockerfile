# Multi-Stage Dockerfile für Agora.
#
# Targets:
#   dev   — Default, identisch mit der ursprünglichen Single-Stage-Variante.
#           Enthält Node + uv + alle Dev-Dependencies, lädt das Repo per
#           Bind-Mount und startet `npm run dev` (Vite + Flask).
#   prod  — schlanke Runtime: gebautes Frontend-Bundle, gunicorn vor Flask.
#           Kein Vite, kein npm, kein Bind-Mount erwartet.
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
ENV UV_HTTP_TIMEOUT=600

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
  && cd backend && uv sync \
  && chown -R agora:agora /app

COPY --chown=agora:agora . .

USER agora

ENV FLASK_HOST=0.0.0.0

EXPOSE 5173 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5001/health || exit 1

CMD ["npm", "run", "dev"]

# ---------- prod-builder (frontend bundle only) ----------
FROM base AS prod-builder

# VITE_AGORA_TOKEN wird als Build-Arg durchgereicht und von Vite zur
# Build-Zeit in das Frontend-Bundle als Plaintext einkompiliert. Nur
# sinnvoll für Single-User-Tailnet-Deploys; nicht für Public-Internet.
ARG VITE_AGORA_TOKEN=""
ENV VITE_AGORA_TOKEN=${VITE_AGORA_TOKEN}

COPY --chown=agora:agora frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

COPY --chown=agora:agora frontend/ ./frontend/
RUN cd frontend && npm run build

# ---------- prod ----------
FROM base AS prod

COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock ./backend/
# Backend-Dependencies installieren ohne Dev-Group; gunicorn als
# Production-WSGI-Server obendrauf.
RUN cd backend && uv sync --no-dev \
  && uv pip install --project backend gunicorn \
  && chown -R agora:agora /app

COPY --chown=agora:agora backend/ ./backend/
COPY --chown=agora:agora --from=prod-builder /app/frontend/dist ./frontend/dist

USER agora

ENV FLASK_HOST=0.0.0.0

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5001/health || exit 1

# Gunicorn vor Flask. Worker-Count konservativ; bei CPU-bound Workloads
# über `--workers` per Compose env überschreibbar.
# Direkter Binary-Aufruf statt `uv run` — `uv run` würde bei jedem
# Container-Start einen `.venv`-Sync versuchen und am read-only Rootfs
# scheitern.
# `--timeout 600` deckt LLM-Streaming-Calls ab (Ontology-Generation,
# Report-Agent, Persona-Generation laufen synchron via httpx-Stream gegen
# Ollama und blockieren den sync-Worker — Default 30 s killt jeden
# nicht-trivialen Call). Folge-Slice migriert auf gevent-Worker, dann
# kann der Timeout konservativer werden.
CMD ["/app/backend/.venv/bin/gunicorn", \
     "--workers", "2", \
     "--timeout", "600", \
     "--graceful-timeout", "30", \
     "--bind", "0.0.0.0:5001", \
     "--chdir", "/app/backend", \
     "--pid", "/home/agora/.gunicorn/gunicorn.pid", \
     "app:create_app()"]
