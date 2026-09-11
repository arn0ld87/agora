# Agora Operator Guide

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Scope:** Installation, Betrieb, Update und Diagnose einer Single-User-Agora-Instanz.

Verwandt:

- [`deployment.md`](deployment.md)
- [`deployment-prod-like.md`](deployment-prod-like.md)
- [`operations.md`](operations.md)
- [`backup-restore.md`](backup-restore.md)
- [`configuration.md`](configuration.md)
- [`provider-runtime-settings.md`](provider-runtime-settings.md)
- [`secret-key-lifecycle.md`](secret-key-lifecycle.md)

---

## 1. Voraussetzungen

Für den Docker-Pfad:

- Git
- Docker Engine/Desktop mit Compose v2 (`docker compose`)
- ausreichend freier Speicher für Neo4j, Uploads, Reports und Modellcache
- Zugriff auf den gewünschten LLM-/Embedding-Provider bzw. lokalen Ollama-/CLI-Transport

Für Host-/Entwicklungspfade zusätzlich je nach Workflow:

- `uv`
- Bun/Node gemäß Repo-Toolchain
- Python wird für Backend-Abhängigkeiten über `uv` verwaltet

Für jeden nicht rein lokalen Zugriff: Tailnet oder Reverse Proxy mit TLS/Auth. Der Default-Bind ist bewusst lokal/private ausgerichtet.

---

## 2. Fresh Install

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
./install.sh
```

`install.sh` erstellt bei Bedarf `.env` und generiert sichere Werte für:

- `SECRET_KEY`
- `AGORA_AUTH_TOKEN`
- `AGORA_SECRET_KEY`
- `AGORA_FERNET_KEY`

Bekannte Placeholder aus der Vorlage gelten nicht als „fertige Secrets“ (#1483).

### Danach manuell prüfen/setzen

Mindestens:

```text
NEO4J_PASSWORD
```

sowie die Provider-/Endpoint-Werte, die für die konkrete Installation erforderlich sind.

**Nicht erneut blind `cp .env.example .env` ausführen.** Das würde die Arbeit des Installers zurückdrehen und wäre eine erstaunlich effiziente Methode, sichere Keys wieder in Platzhalter zu verwandeln.

### `.env` schützen

```bash
chmod 600 .env
```

Nie committen.

---

## 3. Stack starten

### Entwicklung / Standard-Compose

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

Die exakten Compose-Kombinationen stehen in [`deployment.md`](deployment.md) und [`deployment-prod-like.md`](deployment-prod-like.md).

### Health

```bash
curl -fsS http://localhost:5001/health
```

### Authentifizierter Status

```bash
set -a
. ./.env
set +a

curl -fsS \
  -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/status
```

`X-Agora-Token` bleibt kompatibel, `Authorization: Bearer` ist der bevorzugte dokumentierte Weg.

---

## 4. Provider einrichten

Die aktuelle Architektur ist **nicht** mehr „API-Key im Browser-SessionStorage und pro Request mitschicken“.

Kanonischer Ablauf:

1. Settings → LLM Provider öffnen.
2. ProviderConnection anlegen/prüfen.
3. Bei `auth_mode=api_key` Secret im Backend-Store speichern.
4. Verbindung/Model-Discovery testen.
5. Workspace-/Stage-Routing bzw. Run-Route wählen.
6. Lauf starten.

Details: [`provider-runtime-settings.md`](provider-runtime-settings.md).

### CLI-Provider

`codex_cli`:

- kein API-Key-Feld
- keine Base-URL
- Auth über lokale Session

```bash
codex --version
```

```bash
export AGORA_CODEX_HOME="$HOME/.local/share/agora/codex"
mkdir -p "$AGORA_CODEX_HOME" && chmod 700 "$AGORA_CODEX_HOME"
CODEX_HOME="$AGORA_CODEX_HOME" codex login
```

Der Standard-Stack mountet **kein** Codex-Verzeichnis. Fuer den Containerbetrieb
kommt das Override dazu:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.codex-cli.yml \
  up -d
```

`AGORA_CODEX_HOME` ist Pflicht und zeigt bewusst auf ein Agora-eigenes
Verzeichnis, nicht auf `~/.codex`: sonst haette der Backend-Prozess Lese- und
Schreibzugriff auf die persoenliche ChatGPT-Session des Hosts. Das Verzeichnis
muss vor dem `up` existieren — legt Docker es an, gehoert es root und der
Container-User (uid=1000) kommt nicht hinein.

### Provider-Secrets prüfen

Soweit für die Installation verfügbar:

```bash
uv run --project backend python scripts/llm-secrets-doctor.py status
uv run --project backend python scripts/llm-secrets-doctor.py verify
```

Keine Klartext-Secrets in Diagnoseausgaben kopieren.

---

## 5. Embedding-Konfiguration

Chat-Routing und Embeddings sind getrennt.

Aktuell wichtig: [#1417](https://github.com/arn0ld87/agora/issues/1417). Die UI kann eine aktive Embedding-Konfiguration anzeigen, während einzelne Runtime-Consumer weiterhin `EMBEDDING_*` aus `.env` lesen.

Vor einem produktiven Modellwechsel deshalb:

1. Store-Konfiguration prüfen,
2. `.env`-/Runtime-Konfiguration prüfen,
3. `VECTOR_DIM` prüfen,
4. vorgesehenen Migrations-Lifecycle verwenden,
5. nach Migration Retrieval/Graph-Pfad testen.

Gleiche Vektordimension bedeutet nicht gleicher semantischer Vektorraum.

---

## 6. Lauf starten und beobachten

Ein kompletter Lauf umfasst fachlich:

```text
Quelle
  → Graph
  → Prepare / Personas
  → Simulation
  → Report
```

Wichtige Zustandsregeln:

- vollständiger Persona-LLM-Fallback ist blockierend
- Nutzer-Stop → `stopped/user_stop`
- Worker-/Containerverlust kann stale Simulation → `failed/process_restart` reconciliieren
- unvollständiger, aber auslieferbarer Report → `INCOMPLETE`, nicht künstlich `COMPLETED`

### Logs

```bash
docker compose logs -f agora
```

Laufbezogen zusätzlich:

- Simulationsartefakte unter `backend/uploads/<simulation_id>/`
- Reports unter `backend/uploads/reports/<report_id>/`
- Report-Agent-Forensik über `agent_log.jsonl`

---

## 7. Restart / Deploy während laufender Jobs

### Simulation

OASIS-Simulationen besitzen seit #1474/#1476 deutlich bessere Stop-/Restart-/Reconciliation-Semantik.

### Prepare / Report / Graph

**Nicht gleich robust.** Diese Jobs laufen weiterhin als daemonisierte Threads im Webprozess (#1472).

Operative Regel bis zur Behebung:

> Einen Container-/Worker-Recreate möglichst nicht mitten in Prepare, Report oder Graph-Build durchführen.

Ein SIGTERM kann diese Arbeit beenden, ohne einen vollständigen persistenten Interrupted-/Resume-Zustand zu hinterlassen.

---

## 8. Parallelität

Gunicorn läuft produktiv bewusst mit **einem Worker**. Nicht auf `workers=2` oder höher drehen, um einen langsamen Report zu „beschleunigen“.

Warum:

- Run-/Monitor-/Cancel-Teile sind prozesslokal
- mehrere Worker könnten widersprüchlichen Zustand erzeugen
- parallele CPU-schwere Reports konkurrieren im gevent-Worker (#1265)

Bis zur Worker-/Queue-Entkopplung:

- möglichst ein schwerer Report zur Zeit
- Latenz erst gegen CPU/Konkurrenz messen, bevor Provider gewechselt werden

---

## 9. Backup vor Update

Vor jedem produktiven Update:

1. `.env`/Master-Keys sicher verfügbar?
2. `backend/uploads/` gesichert?
3. `backend/data/` gesichert?
4. `backend/instance/` gesichert?
5. Neo4j konsistent gesichert?
6. Git-/Versionsstand dokumentiert?

Komplette Recovery-Reihenfolge: [`backup-restore.md`](backup-restore.md).

Der alte Pfad `backend/reports/` ist falsch. Reports liegen unter `backend/uploads/reports/`.

---

## 10. Update-Prozess

Beispiel für ein normales Code-/Image-Update:

```bash
# Vorher Backup/Smoke entsprechend Betriebsstandard

git fetch origin
git log --oneline HEAD..origin/main
git pull --ff-only origin main

docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d --build

curl -fsS http://localhost:5001/health
```

Wenn Release Notes/Migrationen zusätzliche Schritte verlangen, haben diese Vorrang.

### Kein automatisches „migrate“-Kommando erfinden

Nur einen Migrationsbefehl ausführen, wenn er in der konkreten Release-/Runbook-Doku für diese Version existiert. Ein generisches `python -m app.migrate` gehört nicht als Ritual in jede Update-Anleitung, wenn der konkrete Releasepfad es nicht definiert.

---

## 11. Diagnose

### Dienste

```bash
docker compose ps
docker compose logs --tail 200 agora
docker compose logs --tail 200 neo4j
docker compose logs --tail 200 redis
```

### Redis

```bash
docker compose exec redis redis-cli ping
```

### Neo4j

```bash
docker compose exec neo4j \
  cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1"
```

### Status

```bash
curl -fsS \
  -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/status | jq
```

Weitere konkrete Fehlerbilder: [`troubleshooting.md`](troubleshooting.md).

---

## 12. Häufige aktuelle Befunde

| Symptom | Aktueller erster Verdacht |
|---|---|
| Provider/Modell geht an falsche URL | Route → ProviderConnection → transport/auth → Secret-Resolver prüfen; nicht zuerst `.env` |
| `codex_cli` ohne Key/URL | normal; Session-Transport |
| Embedding-UI und Runtime widersprechen sich | #1417 |
| Run hängt nach Restart | Startup-Reconciliation/`run_state.json`/PID prüfen; bei Prepare/Report/Graph #1472 beachten |
| User-Stop endet `failed` | Regression gegen #1474 |
| Teilreport wirkt vollständig | `metadata.report_status`; Regression gegen #1479 |
| Evidence 200 ohne Map | möglichen `evidence_omitted`-Contract prüfen (#1477) |
| parallele Reports extrem langsam | #1265 / Ein-Worker-gevent-Kontext |
| Budget via Vision/Tool/Interview | #1478 sollte greifen; ParallelIPC-Follow-up beachten |
| Personas driften fachlich | #1471/#1470 |

---

## 13. Security-Basics

- kein direktes öffentliches Exposure ohne geeignete Auth/TLS-/Tailnet-Grenze
- `.env` nie committen
- `AGORA_SECRET_KEY` und `AGORA_FERNET_KEY` separat recoverbar halten
- Provider-Keys über Secret Store statt Run-Artefakte/Browserpersistenz
- Logs vor externer Weitergabe auf Secrets/Personendaten prüfen
- offene Dependency-Risiken über [`dependency-risk-register.md`](dependency-risk-register.md) behandeln

Prompt-Injection-Härtung der Simulations-`observation` ist als #1224 noch offen.

---

## 14. Operator-DoD

### Fresh Install

- [ ] `./install.sh` erfolgreich
- [ ] keine bekannten Placeholder-Secrets in `.env`
- [ ] `NEO4J_PASSWORD` bewusst gesetzt
- [ ] LLM-/Embedding-Runtime konfiguriert
- [ ] `/health` grün
- [ ] `/api/status` mit Auth lesbar
- [ ] Provider-Verbindung getestet

### Vor Update

- [ ] Backup-Punkt vorhanden
- [ ] Master-Keys recoverbar
- [ ] laufende daemonisierte Jobs beendet/abgewartet
- [ ] Release-/Migrationshinweise gelesen

### Nach Update

- [ ] `/health` grün
- [ ] `/api/status` plausibel
- [ ] Neo4j/Redis erreichbar
- [ ] Provider-Route korrekt
- [ ] mindestens ein produktnaher Smoke

Für einen `0.10`-RC reicht diese Checkliste allein nicht: Fresh-Host-Restore, Upgrade und Rollback müssen als echter Nachweis durchgeführt werden (#766).
