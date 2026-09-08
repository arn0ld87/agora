# Operations

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Scope:** Single-User-Betrieb, Diagnose, Restart-/Recovery-Semantik und bekannte operative Grenzen.

Verwandt:

- [`operator-guide.md`](operator-guide.md) — Installation und täglicher Betrieb
- [`backup-restore.md`](backup-restore.md) — Datensicherung/Recovery
- [`deployment.md`](deployment.md) — Deployment-Einstieg
- [`configuration.md`](configuration.md) — Runtime-Konfiguration
- [`security-threat-model.md`](security-threat-model.md) — Trust Boundaries

---

## Betriebsmodell

Aktueller Prod-Grundsatz:

```text
Reverse Proxy / Tailnet
        ↓
Frontend / API
        ↓
Gunicorn (gevent, workers=1, preload_app=True)
        ├─ Flask API
        ├─ Run-/Task-Orchestrierung
        ├─ Redis/Event Bus
        ├─ Neo4j
        └─ OASIS-Subprozesse
```

### Warum `workers=1`?

Das ist derzeit ein **HARDSTOP**, kein versehentlich zu kleiner Tuningwert. Teile von RunRegistry, Monitor-/Cancel- und Jobzustand sind prozesslokal. Mehr Gunicorn-Worker würden denselben Run aus mehreren unkoordinierten Prozessen sehen.

Folge: CPU-schwere Reportarbeit konkurriert innerhalb eines gevent-Workers. [#1265](https://github.com/arn0ld87/agora/issues/1265) dokumentiert starke Verlangsamung bei parallelen Reports. Bis zur Auslagerung/Serialisierung gilt operativ: **keine unnötigen parallelen Reports starten**.

---

## Health und Status

### `GET /health`

Liveness-Probe für Container/Proxy. Keine tiefe fachliche Readiness-Prüfung.

```bash
curl -fsS http://localhost:5001/health
```

### `GET /api/status`

Aggregierte Komponenten-Sicht. In geschütztem Betrieb authentifizieren:

```bash
curl -fsS \
  -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/status
```

Wichtige Bereiche:

- Backend-Version/Status
- Neo4j-Erreichbarkeit
- LLM/Ollama-Sicht
- Disk
- GPU-/E2E-Diagnose, soweit verfügbar

Seit #1459 werden interne Fehler in Status-Teilbäumen strukturiert gemeldet; rohe Exception-Strings mit Pfaden/Hostnamen/Treiberdetails gehören ins Log, nicht in die Clientantwort.

**Wichtig:** Ein Ollama-Status ist nicht automatisch ein globales Run-Gate. Ein Run kann über eine unabhängige ProviderConnection/CLI-Route laufen.

---

## Logs

Primäre Diagnosequellen:

| Bereich | Quelle |
|---|---|
| Backend/Gunicorn | `docker compose logs agora` bzw. Backend-Logverzeichnis |
| Neo4j | `docker compose logs neo4j` |
| Redis | `docker compose logs redis` |
| Simulation | `backend/uploads/<simulation_id>/simulation.log` bzw. laufbezogene Subprozess-Artefakte |
| Report | `backend/uploads/reports/<report_id>/agent_log.jsonl` + Report-Artefakte |
| Run-Zustand | RunRegistry/Manifest + `run_state.json` der Simulation |

Nicht jedes historische Artefakt trägt exakt dieselben Dateinamen; für neue Runs ist der Code/ArtifactStore führend.

Logger-Redaction schützt bekannte Bearer-/Ticket-/Secret-Muster in den Agora-Loggern. Direkte Subprozessausgaben oder fremde Libraries sind dadurch nicht magisch geheilt; Diagnose-Bundles vor Weitergabe prüfen.

---

## Restart- und Crash-Verhalten

### Simulationen

Seit #1476 läuft Startup-Reconciliation:

1. `create_app` führt sie in Dev/Test-Kontexten aus.
2. Gunicorn `post_fork` führt sie bei **jedem Workerstart** aus, also auch nach Worker-Replacement unter `preload_app=True`.
3. `pending`/`processing`/`paused` Runs werden gegen die persistierte Prozess-PID geprüft.
4. Tote/unklare Prozesse werden `failed` mit `termination_reason="process_restart"`.
5. `COMPLETED`/`STOPPED` werden ohne sichere Run-ID-Zuordnung nicht auf andere Manifeste geraten.

Zusätzliche Härtung:

- Starts pro `simulation_id` serialisiert
- 30-s-Grace für frisches `STARTING` ohne PID
- Force-Restart-Generation-Tokens verhindern stale Monitor-Finalisierung (#1474)
- expliziter User-Stop bleibt `stopped/user_stop`

`AGORA_STARTUP_RECONCILIATION=false` schaltet diese Korrektur bewusst ab.

### Prepare / Report / Graph-Build

Hier besteht weiterhin eine wichtige Grenze: Jobs laufen als daemonisierte Threads im Webprozess. Ein SIGTERM kann den Thread beenden, ohne einen vollständigen persistenten Interrupted-/Resume-Zustand zu erzeugen. Siehe [#1472](https://github.com/arn0ld87/agora/issues/1472).

**Betriebsfolge:** Container-/Worker-Recreate möglichst nicht mitten in Prepare/Report/Graph-Build durchführen. Langfristiges Ziel ist eine persistente Queue/Worker-Grenze, nicht noch mehr Hoffen auf daemon threads.

---

## Graceful Shutdown

Die Compose-Definitionen setzen am Agora-Service:

```yaml
init: true
stop_grace_period: 45s
```

Gunicorn verwendet einen kleineren `graceful_timeout`, damit normale Shutdown-Logik vor Docker-SIGKILL eine Chance hat.

Das reduziert Orphans, ersetzt aber nicht die fehlende Job-Persistenz aus #1472.

---

## Neo4j

### Retry-/Idempotenz-Semantik

Episode- und `RELATION`-Writes sind seit #1460 gegen den Fall gehärtet:

```text
Server committet Write
        ↓
ACK geht verloren
        ↓
Client retryt
```

Stabile UUID + `MERGE` verhindern, dass der Retry als zweites Objekt bzw. Constraint-Fehler endet.

Echte Integrationstests prüfen einen idempotenten Write-Pfad gegen Neo4j (#1481).

### Diagnose

```bash
docker compose ps neo4j
docker compose logs --tail 200 neo4j
docker compose exec neo4j \
  cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1"
```

---

## Redis und Event Bus

Redis dient unter anderem Live-/Event-/Ticket-Infrastruktur. Ein Ausfall kann je nach `EVENT_BUS_BACKEND` auf File-Fallback degradieren.

```bash
docker compose exec redis redis-cli ping
```

Die neue Integrationstest-Schicht bestätigt echte Pub/Sub-Zustellung, nicht nur einen retained Snapshot (#1481).

**Kein Missverständnis:** Redis Pub/Sub/Event-Bus ist derzeit **keine durable Jobqueue** für Prepare/Report/Graph.

---

## LLM-Provider im Betrieb

Nicht nur `.env` prüfen. Die Runtime kann über `ProviderConnection` + Routing + Secret Store laufen.

Diagnosefolge:

1. Run-/Workspace-Route
2. ProviderConnection
3. `transport`/`auth_mode`
4. Secret-Resolver
5. Fallback-Env

CLI-Provider wie `codex_cli` haben absichtlich keine Base-URL und keinen API-Key im Agora-Store.

Details: [`provider-runtime-settings.md`](provider-runtime-settings.md).

---

## Run-Budgets

Preflight und Runtime-Budgets erfassen Zeit, Token/Kosten bzw. harte LLM-Call-Grenzen gemäß Contract.

Seit #1478 werden auch:

- native Tool-Calls,
- Vision,
- Direct-Interviews,
- normale IPC-Reportinterviews

gegen Budget geprüft und im Ledger erfasst.

### Bekannte Lücke

Der separate `ParallelIPCHandler` in `scripts/run_parallel_simulation.py` besitzt noch nicht dieselbe vollständige `SubprocessBudgetGuard`-Attribution. Für harte Budget-Abnahmen diesen Pfad ausdrücklich mitprüfen.

---

## Report-Persistenz

Seit #1475 gilt die Commit-Invariante:

```text
Evidence atomar persistieren
        ↓
Markdown atomar persistieren
        ↓
Markdown vorhanden = Commit-Marker
```

Bei Resume:

- Markdown ohne passende Evidence ist ein Orphan,
- Orphan wird entfernt,
- Section wird regeneriert,
- Orphan-Inhalt darf nicht in `previous_sections` für spätere Prompts gelangen.

`os.replace` plus Datei-/Directory-`fsync` schützt gegen Crash-/Powerloss-Fenster. Unsupported-FS-Fälle dürfen degradiert werden; echte POSIX-Permission-/Storagefehler propagieren.

---

## Disk und Datenpfade

Wichtige persistente Bereiche:

- `backend/uploads/` — Uploads, Simulationsartefakte, Laufdaten
- `backend/uploads/reports/` — Reports und Report-Auditdaten
- `backend/data/` — Provider-/Routing-/weitere persistente Stores
- `backend/instance/` — Instanzsettings
- Neo4j-Volume

Historische Doku mit `backend/reports/` ist falsch; der aktuelle Reportpfad liegt unter `backend/uploads/reports/` (#1483).

Disk prüfen:

```bash
du -sh backend/uploads/* 2>/dev/null | sort -h | tail -20
```

Nicht blind einen `<sim_id>`-Ordner löschen, bevor Run-/Report-Verknüpfungen geprüft sind.

---

## Installations-/Secret-Checks

`install.sh` behandelt bekannte Placeholder (`change-me`, `agora`, `password` usw. gemäß Code) als ungesetzt und erzeugt sichere Werte, wo möglich (#1483).

Bei Fresh Install prüfen:

```bash
grep -E '^(SECRET_KEY|AGORA_AUTH_TOKEN|AGORA_SECRET_KEY|AGORA_FERNET_KEY|NEO4J_PASSWORD)=' .env
```

Keine Werte in Tickets/Logs/PRs kopieren.

---

## Backup/Restore

Der aktuelle Sicherungsumfang muss mindestens enthalten:

- Neo4j-Daten
- `backend/uploads/`
- `backend/data/`
- `backend/instance/`
- `.env`/Master-Keys in einer **separaten verschlüsselten** Sicherung

Siehe [`backup-restore.md`](backup-restore.md).

Für 0.10 zählt nicht „wir haben eine Anleitung“, sondern ein dokumentierter Fresh-Host-Restore-/Upgrade-/Rollback-Smoke (#766).

---

## Performance-Regeln bis zur Worker-Entkopplung

- nicht mehrere CPU-schwere Reports parallel starten (#1265)
- Container-Recreate nicht mitten in daemonisierten Jobs durchführen (#1472)
- bei langer Reportlaufzeit zuerst Konkurrenz im selben Worker prüfen, bevor der Provider beschuldigt wird
- Neo4j-/Provider-Latenz getrennt messen; eine 100-%-CPU-Grenze des Webworkers ist kein Netzproblem

---

## Routine-Diagnose

```bash
# Container
docker compose ps

# Logs
docker compose logs --tail 200 agora
docker compose logs --tail 200 neo4j
docker compose logs --tail 200 redis

# Liveness
curl -fsS http://localhost:5001/health

# Authentifizierter Status
curl -fsS \
  -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/status

# Redis
docker compose exec redis redis-cli ping
```

---

## Release-relevante offene Ops-Punkte

1. #1472 durable/restart-fähige langlaufende Jobs
2. #1265 Report-Worker/Serialisierung
3. #1417 Embedding-Runtime-SSoT
4. #766 Restore/Upgrade/Rollback-Nachweis
5. #1274 echte Manifest-/Replay-Reproduzierbarkeit

Diese Liste ist absichtlich kurz. Der komplette aktuelle Iststand steht in [`STATUS.md`](STATUS.md), nicht in einem Operations-Changelog mit Persönlichkeitsspaltung.
