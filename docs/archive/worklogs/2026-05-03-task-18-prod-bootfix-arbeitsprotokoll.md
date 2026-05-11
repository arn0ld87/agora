# Sub-Slice 18 — Prod-Boot-Fix (Compose + Dockerfile)

**Datum:** 2026-05-03
**Branch:** `feat/task-18-prod-bootfix`
**Layer:** Deployment (quer zu 0–5, kein Layer-Lock)
**Refs:** keine offenen Issues — Drift im Repo selbst.

## Symptom

`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
führte zum **Restart-Loop** des `agora`-Containers. Dreistufige Fehlerkette,
jede Stufe hat die nächste maskiert:

1. **Build-Failure**: `uv sync --no-dev` brach beim Download von
   `nvidia-cudnn-cu12==9.10.2.21` (~700 MB) am Default-Timeout (`UV_HTTP_TIMEOUT=30`)
   ab. Erst auf langsamerer Leitung sichtbar.
2. **Runtime-Failure (read-only FS)**: gunicorn-CMD via `uv run` löste bei
   jedem Container-Start einen `.venv`-Sync-Versuch aus (lud sogar Dev-Deps
   `lupa`, `ruff` nach), schlug an `read_only: true` aus
   [`docker-compose.yml:23`](docker-compose.yml:23) fehl.
3. **Runtime-Failure (DNS)**: Nach Fix von 1+2 startete gunicorn, Worker
   crashte in `create_app() → validate_embedding_configuration()` mit
   `Failed to resolve 'ollama'`. Compose-Override hatte
   `LLM_BASE_URL=http://ollama:11434` hardgecoded — erwartet Sibling-Container
   `ollama` im `agora_default`-Netz, der nicht existiert (Ollama läuft nativ
   auf dem Host).

## Root Cause

`docker-compose.prod.yml` widersprach der eigenen Doku:

| Quelle | Aussage |
|---|---|
| [README.md:175](README.md:175) | „Ollama läuft standardmäßig auf dem Host und wird aus dem Container über `host.docker.internal` erreicht" |
| [docs/deployment-prod.md:289–296](docs/deployment-prod.md:289) | „Ollama läuft auf dem Host… Container nutzt `host.docker.internal` per `extra_hosts: host-gateway`" |
| [docker-compose.prod.yml:44–45](docker-compose.prod.yml:44) (vorher) | `LLM_BASE_URL=http://ollama:11434` — erwartet Container-Setup |

Der Inline-Kommentar (Z. 41–43) beschrieb die Sibling-Container-Variante als
Default, ohne den Setup-Schritt (`docker network connect agora_default ollama`)
in README/Doku zu spiegeln. Standardpfad nach Doku war damit kaputt.

## Fix (drei Edits, ein Commit)

### 1. [`Dockerfile`](Dockerfile) — `UV_HTTP_TIMEOUT=600` im base-Stage

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

# Große CUDA-Wheels (cudnn ~700 MB, nvshmem ~300 MB) sprengen den
# uv-Default von 30 s auf langsamen Leitungen.
ENV UV_HTTP_TIMEOUT=600
```

Greift in beiden Stages (dev + prod), weil base-Stage parent ist.

### 2. [`Dockerfile`](Dockerfile) — gunicorn-CMD direkt statt via `uv run`

Vorher:
```dockerfile
CMD ["uv", "run", "--project", "backend", "gunicorn", ...]
```

Nachher:
```dockerfile
# Direkter Binary-Aufruf statt `uv run` — `uv run` würde bei jedem
# Container-Start einen `.venv`-Sync versuchen und am read-only Rootfs
# scheitern.
CMD ["/app/backend/.venv/bin/gunicorn", \
     "--workers", "2", \
     "--bind", "0.0.0.0:5001", \
     "--chdir", "/app/backend", \
     "--pid", "/home/agora/.gunicorn/gunicorn.pid", \
     "app:create_app()"]
```

Die `.venv` ist im Image gebacken (Zeile 79: `uv pip install --project backend gunicorn`),
shebang in `gunicorn`-Skript zeigt korrekt auf `.venv/bin/python`.

### 3. [`docker-compose.prod.yml`](docker-compose.prod.yml) — Ollama-URL doku-konform

Vorher: `LLM_BASE_URL=http://ollama:11434/v1` + `EMBEDDING_BASE_URL=http://ollama:11434`

Nachher: `LLM_BASE_URL=http://host.docker.internal:11434/v1` +
`EMBEDDING_BASE_URL=http://host.docker.internal:11434`

`extra_hosts: host-gateway` aus dem Default-Compose ([docker-compose.yml:38–39](docker-compose.yml:38))
wird per Compose-Merge ins Prod-Override übernommen (kein `!reset` nötig).

Kommentar überarbeitet — Sibling-Container ist jetzt explizit als
**Variante B** dokumentiert, nicht als versteckter Default.

## Verifikation

```
$ docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build agora
 Image agora-agora Built
 Container agora Started

$ docker logs --tail 12 agora
[INFO] Starting gunicorn 25.3.0
[INFO] Listening at: http://0.0.0.0:5001 (1)
[INFO] Booting worker with pid: 7
[INFO] Booting worker with pid: 8
INFO: Embedding configuration validated (qwen3-embedding:4b → 2560 dims)
INFO: Neo4jStorage initialized (connected to bolt://neo4j:7687)
INFO: SimulationEventBus: RedisEventBus connected to redis://redis:6379/0
INFO: AgoraContainer wired (neo4j_storage + artifact_store + event_bus=RedisEventBus)
INFO: Static SPA serving enabled: /app/frontend/dist
INFO: Agora Backend startup complete

$ docker exec agora curl -fsS http://localhost:5001/health
{"service":"Agora Backend","status":"ok"}
```

- gunicorn 25.3.0, 2 Sync-Worker ✓
- Embedding-Probe gegen Host-Ollama erfolgreich (2560-dim qwen3) ✓
- Neo4j + Redis EventBus connected ✓
- Static SPA aus `/app/frontend/dist` ausgeliefert (kein vite, kein npm) ✓
- Boot-Zeit: ~22 s
- Container-FS bleibt `read_only: true` — kein `.venv`-Sync mehr ✓

## Out of Scope

- **Backend/Frontend-Tests**: Code unverändert, `npm run check` hier nicht
  re-laufen — Sub-Slice ändert nur Build/Runtime-Konfiguration.
- **Reverse-Proxy vor Prod-Container** (offenes Issue [#106](https://github.com/arn0ld87/Agora/issues/106)).
- **Tailscale-Access via Vite (`allowedHosts: ['.ts.net']`)**: separater
  Diff in `frontend/vite.config.js`, gehört nicht zum Prod-Pfad und ist
  in `git stash` zwischengeparkt für eigenen Sub-Slice.

## Geänderte Dateien

- `Dockerfile` — UV_HTTP_TIMEOUT (base-Stage), gunicorn-Direct-CMD (prod-Stage)
- `docker-compose.prod.yml` — Ollama-URLs auf `host.docker.internal`, Kommentar korrigiert
- `CHANGELOG.md` — `[Unreleased]` / Fixed-Block
- `docs/2026-05-03-task-18-prod-bootfix-arbeitsprotokoll.md` (neu)

## Folge-Empfehlung

Issue mit Label `deployment, bug` anlegen und Commit nachträglich auf
`Closes #N` referenzieren. Slice-Workflow erwartet 1 Issue pro Sub-Slice;
hier wäre der Bug-Eintrag nützlich für Update-Hinweise (jeder, der seit
dem ursprünglichen Prod-Slice (siehe [docs/2026-04-29-prod-slice2-gunicorn.md](docs/2026-04-29-prod-slice2-gunicorn.md))
Prod versucht hat, war potenziell betroffen).
