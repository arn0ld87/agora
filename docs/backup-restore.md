# Backup & Restore

**Stand:** 20.09.2026  
**Geprüfte Main-Baseline:** `b62aea62`  
**Scope:** Single-User-Datensicherung und Recovery-Inventar. Kein Cluster-Backup, kein PITR.

> [!IMPORTANT]
> Diese Anleitung beschreibt den aktuellen Sicherungsumfang und die Recovery-Reihenfolge. Der **Release-Nachweis**, dass ein vollständiger Restore auf einem frischen Host inklusive Upgrade/Rollback reproduzierbar funktioniert, ist für `0.10` noch offen ([#766](https://github.com/arn0ld87/agora/issues/766)). Ein Markdown-Dokument ist keine Sicherung. Diese Erkenntnis musste die Menschheit offenbar mehrfach bezahlen.

Verwandt:

- [`operations.md`](operations.md)
- [`operator-guide.md`](operator-guide.md)
- [`secret-key-lifecycle.md`](secret-key-lifecycle.md)
- [`deployment-prod-like.md`](deployment-prod-like.md)

---

## Was gesichert werden muss

| Asset | Aktuelle Quelle | Kritikalität |
|---|---|---|
| Neo4j-Graph/Vektoren | Compose-Volume `neo4j_data` / Neo4j-Datenbank | **hoch** |
| Uploads + Simulationsartefakte | `backend/uploads/` | **hoch** |
| Reports + Evidence/Audit | `backend/uploads/reports/` | **hoch** |
| Provider-/Routing-/App-Stores | `backend/data/` | **hoch** |
| Instanzsettings | `backend/instance/` | **hoch** |
| PostgreSQL-Fachschema `agora` | Nur wenn ein `AGORA_*_BACKEND=postgres` aktiv ist | **hoch** |
| `.env` / Master-Keys | Repo-Root, nicht versioniert | **kritisch** |
| Redis | kurzlebiger Event-/Ticketzustand | niedrig; nicht als kanonisches Backup behandeln |
| HuggingFace-/Model-Cache | Cache | niedrig; rekonstruierbar |
| Logs | je nach Diagnose-/Auditbedarf | mittel/niedrig |

### Wichtige Korrektur

Reports liegen unter:

```text
backend/uploads/reports/
```

Der frühere abweichende Reports-Pfad war falsch und wurde mit #1483 korrigiert.

---

## Welche Secrets wirklich mitgesichert werden müssen

Mindestens:

- `SECRET_KEY`
- `AGORA_AUTH_TOKEN`
- `AGORA_SECRET_KEY`
- `AGORA_FERNET_KEY`
- `NEO4J_PASSWORD`
- weitere externe Provider-/Infrastruktur-Secrets, sofern nicht separat im Passwortmanager vorhanden

### Master-Key-Bedeutung

- `AGORA_SECRET_KEY` entschlüsselt gespeicherte LLM-Provider-Secrets **und** den Fernet-Store der LLM-Profil-Secrets (#1583). Er gehört ins Secret-Backup — niemals in den PostgreSQL-Dump, der nur verschlüsselte Referenzen/Ciphertexte trägt, nie den Schlüssel selbst.
- `AGORA_FERNET_KEY` schützt persistierte Agora-API-Key-Daten bzw. zugehörige Secret-/Hash-Pfade.

Ein Restore der verschlüsselten JSON-Datei **ohne den zugehörigen Master-Key** ist kein Restore, sondern eine besonders ordentlich archivierte Form von Datenverlust.

Secrets getrennt und verschlüsselt sichern, z. B. Passwortmanager oder verschlüsseltes Backup. Nie ins Git-Repository legen.

---

## Filesystem-Backup

Ein einzelner Backup-Job sollte mindestens diese Verzeichnisse erfassen:

```text
backend/uploads/
backend/data/
backend/instance/
```

Beispiel mit Restic:

```bash
restic -r /backups/agora backup \
  --tag agora-fs \
  --exclude '*.tmp' \
  --exclude '*.lock' \
  ./backend/uploads \
  ./backend/data \
  ./backend/instance
```

Lock-/Temp-Dateien sind Laufzeitartefakte und sollen nicht als konsistenter Anwendungszustand restauriert werden.

### Reports

`backend/uploads/reports/` liegt bereits unter `backend/uploads/` und muss bei einem vollständigen Upload-Backup **nicht doppelt** erfasst werden.

---

## Neo4j-Backup

Neo4j benötigt einen **konsistenten** Datenbank-/Volume-Stand. Zwei grundsätzlich vertretbare Strategien:

1. ein mit der eingesetzten Neo4j-5-Version kompatibler `neo4j-admin database dump`-Workflow,
2. ein konsistenter Storage-/Volume-Snapshot bei gestoppter bzw. entsprechend quiesced Datenbank.

Die exakte `neo4j-admin`-Syntax hängt an der tatsächlich eingesetzten Neo4j-Version und Betriebsform und soll **vor dem Drill gegen die laufende Version geprüft** werden. Diese Doku pinnt deshalb keinen Monate alten Befehl, der einen Server im Container stoppt und danach so tut, als könne man fröhlich weiter in denselben Prozess `exec`en.

### Minimaler sicherer Ablauf

```text
1. neue Schreibjobs stoppen
2. Agora-Webservice kontrolliert anhalten
3. Neo4j konsistent sichern
4. Hash/Größe/Backup-Metadaten speichern
5. Neo4j + Agora wieder starten
6. /health + /api/status prüfen
```

Bei Storage-Snapshots Neo4j nicht während unkontrollierter Writes einfrieren.

---

## Redis

Redis ist derzeit **nicht** die kanonische Persistenz für Runs, Reports oder Graphen. Es trägt kurzlebige Ticket-/Event-/PubSub-Zustände.

Darum:

- Redis-RDB kann optional mitgesichert werden,
- ein Agora-Disaster-Recovery darf aber **nicht** davon abhängen,
- nach Restore sind laufende SSE-/PubSub-Sessions erwartbar verloren.

Wichtig: Redis/Event Bus ist aktuell auch **keine persistente Jobqueue** für Prepare/Report/Graph (#1472).

---

## PostgreSQL-Backup (#1583)

**Nur relevant, wenn mindestens ein `AGORA_*_BACKEND` auf `postgres` steht** (`app/infrastructure/postgres/backends.py::any_postgres_backend`). Solange alles auf dem Legacy-Default steht (`docs/plans/supabase.md`, „Umgeschaltet ist nichts"), ist dieser Abschnitt ein No-Op — `scripts/restore-drill.sh` überspringt ihn dann und protokolliert das.

Ist ein Backend aktiv, sichert `scripts/restore-drill.sh` zusätzlich zu den drei Dateiverzeichnissen:

```bash
pg_dump --host=<host> --port=<port> --username=<user> --dbname=<db> \
  -n agora -Fc -f postgres.dump
```

Nur das Fachschema `agora` — kein Cluster-Dump, keine Rollen, kein `public`. Das Passwort geht ausschließlich über die Umgebungsvariable `PGPASSWORD` an `pg_dump`, nie als Kommandozeilenargument und nie ins Protokoll (`app/infrastructure/postgres/pg_cli.py` zerlegt `DATABASE_URL` dafür in seine Bestandteile).

Direkt danach entsteht `postgres-manifest.json` (`backend/scripts/postgres_backup_manifest.py`): die Alembic-Revision, auf der die Quelldatenbank *zum Zeitpunkt des Backups* tatsächlich stand, und die Zeilenzahl je Tabelle in `agora`. `restore_verify.py` prüft nach dem Restore genau dagegen — ohne dieses Manifest könnte es nur feststellen, DASS eine Datenbank existiert, nicht ob sie den erwarteten Stand hat.

**Die Alembic-Revision wird nach dem Restore nachgestempelt.** Die Versionstabelle `alembic_version` liegt in `public`, nicht in `agora` (`backend/migrations/env.py`), und ist deshalb nie Teil von `pg_dump -n agora`. Ohne sie verweigert das Start-Gate (#1582) den App-Start. Die Phase `pg_restore` führt deshalb nach dem Restore `alembic stamp <revision aus postgres-manifest.json>` aus; `restore_verify.py` prüft anschließend, dass Manifest-Revision, Revision der restaurierten Datenbank und Code-Head übereinstimmen.

Sekundäre Secrets im Fachschema — verschlüsselte Referenzen, keine Klartext-Master-Keys — laufen mit dem Dump; `AGORA_SECRET_KEY` selbst nicht (siehe oben).

---

## Recovery-Reihenfolge

Worst-Case auf einem frischen Host:

1. passende Agora-Version auschecken,
2. `.env`/Master-Keys aus sicherer Quelle herstellen,
3. `backend/data/` restaurieren,
4. `backend/instance/` restaurieren,
5. `backend/uploads/` restaurieren,
6. Neo4j-Datenbank/Volume konsistent restaurieren,
7. **falls ein `AGORA_*_BACKEND=postgres` aktiv ist:** PostgreSQL-Restore (`pg_restore --clean --if-exists`, danach `alembic stamp <revision aus postgres-manifest.json>`) — **vor** dem App-Start, damit die Anwendung nie gegen ein halb restauriertes Schema startet,
8. Dateirechte für den Container prüfen,
9. Stack starten,
10. Health/Status prüfen,
11. Provider-Secret-Store entschlüsseln/testen,
12. `backend/scripts/restore_verify.py` — bei aktivem PostgreSQL-Backend mit `--postgres-manifest`,
13. Graph/Run/Report eines Referenzfalls öffnen,
14. erst danach produktive neue Runs zulassen.

### Reihenfolge der Secrets

Master-Keys müssen **vor** dem ersten produktiven Zugriff auf die verschlüsselten Stores wiederhergestellt sein. Nicht mit neu generierten Keys starten und anschließend erwarten, dass die alten Ciphertexte plötzlich Verständnis zeigen.

---

## Restore-Verifikation

Ein Restore gilt erst als brauchbar, wenn mindestens folgende Checks grün sind.

Die Punkte unter „Artefakte", „Provider/Secrets", „Reconciliation" und — bei aktivem PostgreSQL-Backend — „PostgreSQL" prüft [`backend/scripts/restore_verify.py`](../backend/scripts/restore_verify.py) maschinell und schreibt ein Protokoll mit Zeitstempel und Exit-Code:

```bash
cd backend && uv run python scripts/restore_verify.py --data-dir uploads --store-dir data
cd backend && uv run python scripts/restore_verify.py --data-dir uploads --store-dir data \
  --postgres-manifest /pfad/postgres-manifest.json
```

`--data-dir` ist das Artefaktverzeichnis, `--store-dir` das der JSON-Stores (`backend/data` bzw. `AGORA_DATA_DIR`) — `provider_connections.json` liegt dort, nicht unter `uploads`.

Ein übersprungener Punkt zählt dort ausdrücklich **nicht** als bestanden: das Skript beendet sich dann mit Exit-Code `2` (Exit `1` = mindestens ein Prüfpunkt ist rot, Exit `0` = alles grün und nichts übersprungen). Für den vollständigen Fresh-Host-Durchgang siehe [`runbooks/restore-drill.md`](runbooks/restore-drill.md).

### Infrastruktur

```bash
docker compose ps
curl -fsS http://localhost:5001/health
curl -fsS \
  -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/status
```

### Neo4j

- Datenbank erreichbar
- Knoten-/Relationen-Größenordnung plausibel
- ein bekannter Graph lässt sich lesen

### Provider/Secrets

- gespeicherte ProviderConnections vorhanden
- Secret-Store lässt sich mit dem restaurierten `AGORA_SECRET_KEY` entschlüsseln
- gespeicherte Agora-API-Keys/Scope-Daten sind mit `AGORA_FERNET_KEY` lesbar, soweit der Pfad genutzt wird
- keine Secrets in Logs ausgeben

### PostgreSQL (#1583, nur bei aktivem `AGORA_*_BACKEND=postgres`)

- Revision aus dem Backup-Manifest, Revision der restaurierten Datenbank und Code-Head aus `backend/migrations/` stimmen überein
- Zeilenzahl je Tabelle im Schema `agora` stimmt mit dem Manifest überein
- jede in `agora.projects` referenzierte Kennung hat ein Projektverzeichnis unter `uploads/projects/<id>/`

### Artefakte

- ein bestehender Run ist sichtbar
- zugehörige Simulation-Artefakte vorhanden
- ein Report lädt
- Evidence-Endpunkt verhält sich contract-konform (validierte Map oder ehrliches `evidence_omitted`)

---

## Reconciliation nach Restore

Beim Start führt Agora Startup-Reconciliation aus — für persistierte Simulation-Runs anhand der gespeicherten PID (#1476) und für die In-Process-Jobs (Prepare, Report, Graph-Build) anhand der Prozess-Identität im Manifest (#1472). Runs, deren Eigentümerprozess auf dem neuen Host naturgemäß nicht mehr existiert, können als:

```text
failed / process_restart
```

korrigiert werden.

Das ist erwünscht: Ein restaurierter Host darf keinen historischen Prozess als „läuft gerade“ vortäuschen.

`COMPLETED`/`STOPPED` werden ohne beweisbare Zuordnung nicht geraten/überschrieben.

---

## Was ein Restore **nicht** reproduziert

Ein Restore ist keine Garantie für bitidentische neue Simulationen oder Reports.

Aktuell offen (#763/#1274):

- vollständige Prompt-Snapshots
- echter Input-Hash/Dateiname im Manifest
- vollständig verdrahteter RNG-Seed
- vollständige Route-/Feature-Flag-Snapshots
- identische Replay-Parameter

Ein wiederhergestelltes historisches Artefakt soll lesbar sein. Ein **neu ausgeführter** Run kann dennoch andere LLM-Ausgaben erzeugen.

---

## Backup-Frequenz

Richtwert für einen aktiv genutzten Single-User-Host:

| Asset | Vorschlag |
|---|---|
| `backend/uploads/`, `backend/data/`, `backend/instance/` | mindestens täglich; bei aktiver Nutzung häufiger inkrementell |
| Neo4j | täglich bzw. nach wichtigen Ingestion-/Migrationsläufen |
| `.env`/Master-Keys | bei jeder Rotation/Änderung |
| Release-/Migrations-Backup | **vor jedem Upgrade** |

Retention hängt von Disk/Compliance ab. Ein pragmatisches Schema ist 7 tägliche, 4 wöchentliche und mehrere monatliche Stände.

---

## Vor Upgrade

1. aktuellen Git-/Versionsstand dokumentieren,
2. Filesystem-Backup erstellen,
3. Neo4j konsistent sichern,
4. Secret-/Master-Key-Backup prüfen,
5. einen Restore-Punkt mit Timestamp/Version markieren,
6. erst dann Code/Image aktualisieren.

Rollback ohne passenden Daten-/Schema-Stand kann einen Mischzustand erzeugen. Genau deshalb ist #766 ein echter Release-Gate und kein Doku-Todo.

---

## 0.10-Abnahme (#766)

Vor dem Release Candidate fehlt noch der formale Nachweis:

- [ ] vollständiges Referenzprojekt auf frischem Host restauriert
- [ ] Graph, Runs, Reports und Secrets danach geprüft
- [ ] Upgrade 0.9.x → 0.10.0 durchgeführt
- [ ] absichtlich fehlgeschlagene Migration sauber zurückgerollt
- [ ] automatisierter Betriebs-Smoke für Restore oder Upgrade vorhanden
- [ ] Release-Artefakte/SBOM/Checksummen vorhanden

Bis diese Punkte dokumentiert durchgeführt sind, ist der Backup-Pfad **plausibel dokumentiert, aber nicht release-verifiziert**.
