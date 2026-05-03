# Arbeitsprotokoll N2 — Dev-Compose Loopback-Binding

**Datum:** 2026-05-03  
**Slice:** M9-2.5 / N2  
**Subagent:** agora-refactor-worker (Sonnet)  
**Branch:** fix/n2-loopback-binding  
**Refs:** PLAN.md N2, SECURITY_REVIEW.md

## Problem

`docker-compose.yml:23-24` publizierte Frontend (5173) und Backend (5001) ohne `127.0.0.1:`-Prefix. Auf Linux bedeutet das automatisch `0.0.0.0` — der Dev-Stack war aus dem LAN erreichbar, obwohl README/CLAUDE.md behaupteten „loopback first". Neo4j (Z. 108-109) hatte das Prefix korrekt gesetzt.

## Änderungen

### 1. `docker-compose.yml` — Ports auf 127.0.0.1

```diff
     ports:
-      - "${AGORA_FRONTEND_PORT:-5173}:5173"
-      - "${AGORA_BACKEND_PORT:-5001}:5001"
+      - "127.0.0.1:${AGORA_FRONTEND_PORT:-5173}:5173"
+      - "127.0.0.1:${AGORA_BACKEND_PORT:-5001}:5001"
```

Kommentar aktualisiert: macOS-Bug-Hinweis entfernt (Docker Desktop 4.30+ behandelt 127.0.0.1 korrekt), stattdessen Tailscale-Override-Hinweis.

### 2. `scripts/verify-deploy.sh` — Bind-Check

```bash
# N2: Loopback-Bind-Check
echo
echo "N2 (Loopback-Bind):"
check "Vite auf 127.0.0.1:5173" bash -c "docker compose exec -T agora ss -tlnp | grep ':5173' | grep -q '127.0.0.1'"
check "Flask auf 127.0.0.1:5001" bash -c "docker compose exec -T agora ss -tlnp | grep ':5001' | grep -q '127.0.0.1'"
```

### 3. Kein `docker-compose.override.yml`-Change

Der Tailnet-Override-Pfad existiert bereits via ENV (`AGORA_BIND_HOST=0.0.0.0` in `.env` → User-Opt-in). `docker-compose.override.yml` bleibt unverändert.

## Akzeptanz

```bash
cd /tmp/agora-n2 && grep -E 'ports:' -A2 docker-compose.yml
# → 127.0.0.1:5173 und 127.0.0.1:5001
docker compose up -d && ss -tlnp | grep -E ':(5173|5001)'
# → 127.0.0.1:5173, 127.0.0.1:5001
```

## Offen

- Merge auf `main` nach 90s + CI-Prüfung.
- Nächster Slice: F2.1 (ALLOW_BUILD_TIME_TOKEN-Gate im Dockerfile).
