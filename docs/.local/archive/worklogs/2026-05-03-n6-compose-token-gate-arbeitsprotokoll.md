# Arbeitsprotokoll N6 — Compose-Token-Gate konsistent mit Dockerfile

**Datum:** 2026-05-03  
**Slice:** M9-3.5 / N6  
**Subagent:** agora-refactor-worker (Sonnet)  
**Branch:** fix/n6-compose-token-gate  
**Refs:** PLAN.md N6, F2.1

## Problem

`docker-compose.prod.yml` reichte `VITE_AGORA_TOKEN` als Build-Arg durch, ohne das `ALLOW_BUILD_TIME_TOKEN`-Gate zu setzen. Das Dockerfile hatte zwar `ARG ALLOW_BUILD_TIME_TOKEN=false` (F2.1/Slice 46), aber Compose überschrieb es nie — das Gate war im Compose-Pfad unwirksam.

## Aenderungen

### 1. `docker-compose.prod.yml` — Gate-Arg hinzugefuegt

```yaml
args:
  ALLOW_BUILD_TIME_TOKEN: ${ALLOW_BUILD_TIME_TOKEN:-false}
  VITE_AGORA_TOKEN: ${VITE_AGORA_TOKEN:-}
```

### 2. `.env.example` — Build-Args dokumentiert

```ini
# Docker-Compose Build-Args (Prod)
ALLOW_BUILD_TIME_TOKEN=false
VITE_AGORA_TOKEN=
```

## Akzeptanz

```bash
# Default-Build (kein Gate): kein Token im Bundle
ALLOW_BUILD_TIME_TOKEN= VITE_AGORA_TOKEN=test1234 \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker run --rm <image-tag> sh -c 'grep -rl test1234 /app/frontend/dist/ || true'
# → leer

# Opt-In-Build (Gate=true): Token ist im Bundle
ALLOW_BUILD_TIME_TOKEN=true VITE_AGORA_TOKEN=test1234 \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker run --rm <image-tag> sh -c 'grep -rl test1234 /app/frontend/dist/'
# → gefunden
```

## Offen

- Merge auf `main` nach 90s Wartezeit.
