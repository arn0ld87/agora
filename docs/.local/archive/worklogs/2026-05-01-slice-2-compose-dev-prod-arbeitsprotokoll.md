# Slice 2 — Compose Dev/Prod-Trennung (PR2)

**Datum:** 2026-05-01
**Branch:** `claude/sleepy-torvalds-32f68f`
**Slice-Quelle:** Repo-Review PR2 (User-Prompt, „Docker-Compose Dev/Prod-Trennung").

## Ziel

Default-Compose baut explizit `target: dev` (Vite + Flask, Hot-Reload). Alle
Host-Ports binden auf `127.0.0.1`. Der Prod-Override entfernt Vite und Neo4j-
Host-Ports komplett (`!reset []`), der Backend-Port bleibt auf Loopback.

## Ausgangslage

- [docker-compose.yml](../docker-compose.yml) hatte `build: .` ohne `target` →
  letzter Multi-Stage (`prod`) wurde gebaut. Dev-User mussten manuell
  `docker compose build --build-arg target=dev` setzen.
- Alle Host-Ports (5173, 5001, 7474, 7687) banden auf `0.0.0.0`.
- [docker-compose.prod.yml](../docker-compose.prod.yml) erbte Neo4j-Ports vom
  Default (kein Override), exponierte damit Browser/Bolt auch in Prod.

## Änderungen

### docker-compose.yml
- `agora.build.target: dev` explizit gesetzt
- Alle Ports auf `127.0.0.1` gelockt (agora 5173/5001, neo4j 7474/7687)
- Kommentare dokumentieren Loopback-Bind und Reverse-Proxy-Empfehlung

### docker-compose.prod.yml
- `agora.ports` via `!override` auf `127.0.0.1:${AGORA_BACKEND_PORT:-5001}:5001`
- `neo4j.ports: !reset []` — Host-Ports komplett raus; Container→Container-Bolt
  läuft weiter übers Compose-Netzwerk
- Kommentare zu `!reset []`-Abhängigkeit (Docker Compose v2.24+) und Fallback
- `!reset []` braucht Docker Compose v2.24+. Ältere Versionen fallen back auf
  array-merge — dann erbt Prod die Loopback-Ports vom Default. Kein
  Sicherheitsbruch (127.0.0.1)

### README.md
- Schnellstart in Dev-/Prod-Blöcke aufgeteilt
- Loopback-Tabelle mit allen Endpoints
- Reverse-Proxy-Hinweis für LAN/Tailscale
- Docker-Kommandos angepasst (`up -d --build`)

### backend/tests/test_compose_snapshot.py (neu)
- 8 Cases in zwei Klassen, skip-if-no-docker
- Dev: target=dev, alle Ports auf 127.0.0.1
- Prod: kein 5173, kein Neo4j-Host-Port, Backend auf 127.0.0.1

## Verifikation

- `npm run check` grün
- Backend: 683 passed, 9 skipped (2 Redis-Integration, 7 Compose-Snapshot wg.
  fehlendem `.env` im Worktree — normal)
- Frontend: 40 passed, Lint 0 errors / 1 pre-existing Warnung (`nextTick` unused)
- Build ok
- `docker compose config` zeigt `target: dev`
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` zeigt
  kein 5173, kein Neo4j-Host-Port-Mapping
