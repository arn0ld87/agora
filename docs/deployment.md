# Deployment

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Produktversion:** `0.9.5`

Diese Datei ist der Einstieg für Deployment-Fragen. Details bleiben getrennt:

- [`deployment-dev.md`](deployment-dev.md) — lokale Entwicklung/Hot-Reload
- [`deployment-prod-like.md`](deployment-prod-like.md) — gehärteter Single-User-Betrieb
- [`operator-guide.md`](operator-guide.md) — Installation/Update/Diagnose
- [`operations.md`](operations.md) — Laufzeit-/Recovery-Semantik
- [`backup-restore.md`](backup-restore.md) — Sicherung/Restore

## Schnellstart

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
./install.sh
```

`install.sh` erzeugt `.env` und sichere App-/Auth-/Fernet-Secrets. Anschließend mindestens `NEO4J_PASSWORD` und die für die konkrete Installation benötigten Provider-/Endpoint-Werte prüfen.

### Standard/Dev

```bash
docker compose up -d --build
```

### Prod-like

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d --build
```

## Aktuelle Prod-Grundsätze

- Host-Port des Backends standardmäßig Loopback.
- Neo4j/Redis im Prod-Override nicht unnötig öffentlich publizieren.
- read-only Root-Filesystem mit expliziten Write-Pfaden.
- Gunicorn verwendet bewusst **einen Worker**; nicht auf mehrere Worker erhöhen, solange prozesslokale Run-/Monitorzustände existieren.
- Agora-Service verwendet `init: true` und `stop_grace_period: 45s`.
- Reverse Proxy/Tailnet ist für Remote-Zugriff die vorgesehene Grenze.
- `AGORA_AUTH_TOKEN`/API-Key-Scope-Modell bleibt Single-User-/Single-Tenant-Auth, kein Multi-User-Identity-System.

## Wichtige Compose-/Runtime-Parameter

Die exakte Liste steht in `.env.example`/Compose. Häufig relevante Werte:

| Variable | Zweck |
|---|---|
| `AGORA_BIND_HOST` | Host-Bind, Default Loopback |
| `AGORA_BACKEND_PORT` | API/Frontend-Port |
| `AGORA_FRONTEND_PORT` | Dev-Frontend-Port |
| `AGORA_DNS_PRIMARY`, `AGORA_DNS_SECONDARY` | Container-DNS |
| `NEO4J_IMAGE` | Neo4j-Image-Pin |
| `NEO4J_HEAP_INITIAL`, `NEO4J_HEAP_MAX`, `NEO4J_PAGECACHE_SIZE` | Neo4j-Memory |
| `AGORA_STARTUP_RECONCILIATION` | stale Simulationen beim Workerstart korrigieren |

## Nach Deployment

```bash
curl -fsS http://localhost:5001/health
curl -fsS \
  -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/status
```

Zusätzlich ProviderConnection/Routing, Neo4j, Redis und einen produktnahen Smoke prüfen.

## Bekannte Betriebsgrenzen

- Prepare-/Report-/Graph-Daemon-Threads sind noch nicht vollständig restart-sicher (#1472).
- Mehrere parallele Reports können sich im einzelnen gevent-Worker stark verlangsamen (#1265).
- Embedding-UI und produktiver Runtime-Pfad können bis #1417 auseinanderlaufen.
- Ein dokumentiertes Backup ist noch kein nachgewiesener Fresh-Host-Restore; Release-Gate #766 bleibt offen.
