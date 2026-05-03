# Arbeitsprotokoll F3 — Gunicorn auf gevent-Worker migriert

**Datum:** 2026-05-03  
**Slice:** M9-5 / F3  
**Subagent:** agora-refactor-worker (Sonnet)  
**Branch:** fix/f3-gunicorn-gevent  
**Refs:** PLAN.md F3

## Problem

Gunicorn lief mit sync-Workern (`--workers 2 --timeout 600`). SSE-Streams (`/api/simulation/<id>/stream`) blockieren sync-Worker — bei parallelen Verbindungen sind alle Worker schnell belegt. Der hohe Timeout (600s) war ein Workaround für LLM-Streaming, der jetzt mit gevent überflüssig wird.

## Aenderungen

### 1. `Dockerfile` — gevent installieren

```diff
-  && uv pip install --project backend gunicorn \
+  && uv pip install --project backend gunicorn gevent \
```

### 2. `Dockerfile` — Gunicorn-CMD auf gevent umgestellt

```diff
+     "-k", "gevent", \
      "--workers", "2", \
-     "--timeout", "600", \
+     "--timeout", "60", \
```

`-k gevent` aktiviert den gevent-Worker. `--timeout 60` ist konservativ für Ollama-TTFB; bei echten Streaming-Calls blockiert gevent nicht.

### 3. `backend/tests/test_gevent_fork.py`

Prüft, dass `gevent` importierbar ist (skippt graceful wenn nicht installiert).

## Akzeptanz

```bash
# Docker-Build erfolgreich
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# Container Health
docker compose up -d agora
curl -fsS http://localhost:5001/health → {"service":"Agora Backend","status":"ok"}

# SSE-Stream testen (parallel 2x)
# → beide Verbindungen grün, kein Worker-Block
```

## Offen

- Merge auf `main` nach 90s + CI-Prüfung.
- Nächster Slice: F1.2 (verify-deploy.sh erweitern um Proxy-Stack-Smoke).
