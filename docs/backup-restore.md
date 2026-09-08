# Backup & Restore

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
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

- `AGORA_SECRET_KEY` entschlüsselt gespeicherte LLM-Provider-Secrets.
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

## Recovery-Reihenfolge

Worst-Case auf einem frischen Host:

1. passende Agora-Version auschecken,
2. `.env`/Master-Keys aus sicherer Quelle herstellen,
3. `backend/data/` restaurieren,
4. `backend/instance/` restaurieren,
5. `backend/uploads/` restaurieren,
6. Neo4j-Datenbank/Volume konsistent restaurieren,
7. Dateirechte für den Container prüfen,
8. Stack starten,
9. Health/Status prüfen,
10. Provider-Secret-Store entschlüsseln/testen,
11. Graph/Run/Report eines Referenzfalls öffnen,
12. erst danach produktive neue Runs zulassen.

### Reihenfolge der Secrets

Master-Keys müssen **vor** dem ersten produktiven Zugriff auf die verschlüsselten Stores wiederhergestellt sein. Nicht mit neu generierten Keys starten und anschließend erwarten, dass die alten Ciphertexte plötzlich Verständnis zeigen.

---

## Restore-Verifikation

Ein Restore gilt erst als brauchbar, wenn mindestens folgende Checks grün sind:

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

### Artefakte

- ein bestehender Run ist sichtbar
- zugehörige Simulation-Artefakte vorhanden
- ein Report lädt
- Evidence-Endpunkt verhält sich contract-konform (validierte Map oder ehrliches `evidence_omitted`)

---

## Reconciliation nach Restore

Beim Start führt Agora für persistierte Simulation-Runs Startup-Reconciliation aus (#1476). Runs, deren gespeicherte PID auf dem neuen Host naturgemäß nicht mehr lebt, können als:

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
