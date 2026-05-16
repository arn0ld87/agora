# Backup & Restore

**Stand:** 2026-05-01, Europe/Berlin
**Scope:** Wie Agora-Daten gesichert und wiederhergestellt werden. Drei
Asset-Klassen: Neo4j-Graph, FS-Artefakte (Uploads, Reports, OASIS-State)
und `.env` mit Secrets. Kein Cluster-Backup, kein PITR — Single-User-
Setup.

Verwandte Dokumente:
- [`operations.md`](operations.md) — Logs, Healthcheck, Ausfälle.
- [`deployment-prod-like.md`](deployment-prod-like.md) — Update- und
  Rollback-Pfad.
- [`security-threat-model.md`](security-threat-model.md), Asset-Tabelle.

---

## Was gesichert werden muss

| Asset | Quelle | Restore-Verlust akzeptabel? |
|---|---|---|
| Neo4j-Graph (Knoten, Episoden, Embeddings) | Compose-Volume `neo4j_data` (Container `/data`) | nein — entspricht Wochen/Monaten Ingestion. |
| Uploads (PDF/MD/TXT, OASIS-Subprocess-Snapshots, Console-Logs) | Bind-Mount `./backend/uploads/` | teilweise — Quelldokumente können neu hochgeladen werden, aber Run-State wäre weg. |
| Reports + Audit-Trails | `./backend/reports/` plus `ArtifactStore`-Pfade unter `backend/uploads/<sim_id>/` | teilweise — neuer Run reproduziert nicht zwingend dasselbe Report-Wording. |
| `simulation_config.json`, `state.json` | unter `backend/uploads/<sim_id>/` | nein, sobald die Simulation läuft. Frozen Config wird beim Run-Start geschrieben. |
| **Multi-Provider-Hub-Daten** (Issue #450 P1.3) | Bind-Mount `./backend/data/` mit `llm_provider_secrets.json` + `workspace_llm_routing.json` | nein — verschlüsselte Provider-Keys + Workspace-Routing-Defaults. Verlust = jeder Workspace muss seine Cloud-Keys neu eingeben. |
| **`AGORA_SECRET_KEY`** | `.env` (Fernet-Master-Key für `backend/data/llm_provider_secrets.json`) | nein — Verlust = Provider-Keys sind nicht mehr entschlüsselbar (Datenverlust). Separat zu `.env` sichern. |
| UI-Settings (LLM-Provider, Modell-Defaults) | Bind-Mount `./backend/instance/` (`settings.json`, `llm_profiles.db`) | nein, sobald operative Defaults gesetzt sind. |
| `.env` (Secrets) | Repo-Root, **nicht versioniert** | nein — `SECRET_KEY`, `AGORA_AUTH_TOKEN`, `NEO4J_PASSWORD`, `AGORA_SECRET_KEY`. |
| HuggingFace-Cache | `./backend/.cache/huggingface/` | ja — kostenfrei nachladbar (~1 GB). |
| Redis | Compose-Volume `redis_data` (RDB-Snapshot) | ja — nur Tickets + Pub/Sub-Backlog, kurzlebig. |
| Neo4j-Logs | Compose-Volume `neo4j_logs` | ja. |

---

## Neo4j

### Online-Dump (Hot-Backup mit Neo4j-Admin)

Neo4j 5 unterstützt `neo4j-admin database dump` im Online-Modus für die
Community Edition mit der Einschränkung, dass die Datenbank gestoppt sein
muss. Pragmatisch heißt das: Backend kurz pausieren, Dump ziehen, weiter.

```bash
TS=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=/var/backups/agora/neo4j
mkdir -p "$BACKUP_DIR"

# 1. Backend anhalten — Neo4j muss frei sein.
docker compose stop agora

# 2. Neo4j stoppen (nur die DB, nicht den Container).
docker compose exec neo4j neo4j-admin server stop

# 3. Dump.
docker compose exec neo4j neo4j-admin database dump neo4j \
  --to-path=/var/lib/neo4j/dumps

# 4. Dump aus dem Container holen.
docker compose cp neo4j:/var/lib/neo4j/dumps/neo4j.dump \
  "$BACKUP_DIR/neo4j-$TS.dump"

# 5. Neo4j wieder hoch und Backend dazu.
docker compose exec neo4j neo4j-admin server start &
docker compose start agora
```

Dump-Größe: typisch ~30–60 % der `neo4j_data`-Volume-Größe (Pagecache
und Logs sind nicht im Dump).

### Schnelle Volume-Variante

Für regelmäßige Cronjobs reicht oft der Volume-Snapshot. Setzt voraus,
dass die Backup-Lösung (Btrfs, ZFS, Restic) konsistente Snapshots auf
Block-Ebene macht.

```bash
docker compose stop agora neo4j
sudo btrfs subvolume snapshot \
  /var/lib/docker/volumes/agora_neo4j_data \
  /backups/snapshots/neo4j-$(date +%Y%m%d-%H%M%S)
docker compose start neo4j agora
```

Vorteil: schneller, weniger Disk-IO. Nachteil: braucht Btrfs/ZFS-Filesystem
unter `/var/lib/docker/volumes`.

### Restore aus Dump

```bash
# Backend + Neo4j stoppen
docker compose stop agora
docker compose exec neo4j neo4j-admin server stop

# Dump in den Container kopieren
docker compose cp /var/backups/agora/neo4j/neo4j-20260501-030000.dump \
  neo4j:/var/lib/neo4j/dumps/neo4j.dump

# Vorhandenes Neo4j-DB-Volume leerräumen — sonst meckert load
docker compose exec neo4j rm -rf /data/databases/neo4j /data/transactions/neo4j

# Restore
docker compose exec neo4j neo4j-admin database load neo4j \
  --from-path=/var/lib/neo4j/dumps --overwrite-destination=true

# Neo4j + Backend starten
docker compose exec neo4j neo4j-admin server start &
docker compose start agora

# Verifikation
docker compose exec neo4j cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  "MATCH (n) RETURN count(n) AS knoten"
```

### Restore-Drill

**Pflicht-Routine, sonst wertloses Backup.** Quartalsweise mindestens
einmal:

1. Dump aus Production-Backup auf Test-Maschine kopieren.
2. Frischen Compose-Stack hochfahren mit Test-`.env`.
3. Restore-Schritte oben ausführen.
4. Smoke-Test: `curl http://localhost:5001/api/status` (auth-pflichtig)
   und Cypher-Knoten-Count gegen erwartete Größenordnung.

Wenn der Drill fehlschlägt, ist das Backup defekt — vor dem
nächsten regulären Lauf reparieren.

---

## Filesystem-Artefakte

### Uploads + OASIS-State

Bind-Mount `./backend/uploads/` enthält pro Simulation einen Ordner
`<sim_id>/` mit:

- Original-Upload-Dateien (`*.pdf`, `*.md`).
- `simulation_config.json` (frozen Config: Modell, Persona-Limit,
  Sprache, Time-Profile).
- `state.json` (Run-State: Status, Round-Counter, Pause-Marker).
- `console.log` (Subprocess-Output).
- Persona-CSV, Round-Snapshots, Event-Bus-File-Backlog.

Sicherung mit Restic (vom Repo-Host):

```bash
restic -r /backups/agora backup \
  --tag agora-uploads \
  --exclude '*.tmp' \
  ./backend/uploads
```

Mit Borg analog. Btrfs-Snapshot des Subvolume genauso valide.

### Reports

`./backend/reports/` enthält generierte Reports und Audit-Trails (per
`ReportLogger`). Wird selten überschrieben — meistens append-only. Im
Restic-Job mitsichern.

### Multi-Provider-Hub (`backend/data/`)

Seit dem LLM-Provider-Hub liegen in `backend/data/`:

- `llm_provider_secrets.json` — Fernet-verschlüsselte Provider-Keys, gehärtet
  via `fcntl.flock` + Mode `0600`. Klartext-Keys gibt es nur kurzzeitig im
  Speicher der Backend-Prozesse.
- `workspace_llm_routing.json` — Workspace-Routing-Defaults (Global-Default
  und Stage-Overrides pro Pipeline-Stage), ebenfalls mit `0600`.
- `*.lock` — Sidecar-Dateien für `fcntl.flock`; sind transient und müssen
  **nicht** mitgesichert werden.

Backup mit Restic:

```bash
restic -r /backups/agora backup \
  --tag agora-data \
  --exclude '*.lock' \
  --exclude '*.tmp' \
  ./backend/data
```

Restore-Reihenfolge:

1. `docker compose down` (Backend muss aus sein, weil Workspace-Routing-Writes
   beim Start passieren können).
2. `restic restore latest --include backend/data --target /opt/agora-restore`.
3. `rsync -a --delete /opt/agora-restore/backend/data/ ./backend/data/`.
4. **`AGORA_SECRET_KEY` aus dem ursprünglichen `.env` wiederherstellen** —
   sonst ist `llm_provider_secrets.json` mit dem aktuellen Key nicht
   entschlüsselbar (`scripts/llm-secrets-doctor.py verify` schlägt dann fehl).
5. `docker compose up -d --build` und im UI prüfen, ob die Provider-Maske
   die gewohnten Keys zeigt.

> **Achtung — Host-Rechte.** Der Container läuft als `uid=1000`. Auf
> Linux-Hosts muss das Host-Verzeichnis `./backend/data/` für diesen User
> schreibbar sein (`chown -R 1000:1000 backend/data` einmal vor dem ersten
> Start; danach erbt der Bind-Mount die Rechte). Auf macOS/Docker-Desktop
> mapped Docker die Bind-Mount-UID automatisch — kein `chown` nötig.

### `.env` (Secrets)

Wegen der `SECRET_KEY` / `AGORA_AUTH_TOKEN`-Werte ist `.env` kritisch.
Optionen:

- Verschlüsselt im Restic-Backup mitsichern (`restic` macht das per
  Default mit dem Repo-Passwort, sofern das nicht `.env` selbst ist).
- Separate Sicherung in Passwort-Manager (Bitwarden, KeePass).
- Nicht im Git versionieren — `.gitignore` sperrt sie. Niemals
  Pull-Request mit echter `.env` öffnen.

---

## Cron-Strategie (Vorschlag)

Crontab auf dem Compose-Host (Repo-Root als Working-Dir):

```cron
# Täglicher Neo4j-Dump um 03:00 — schiebt Backend für ~30s in Pause.
0 3 * * * /usr/local/bin/agora-backup-neo4j.sh

# Stündliches Restic-Inkrement für Uploads/Reports + Multi-Provider-Hub.
17 * * * * cd /opt/agora && restic -r /backups/agora backup \
              --tag agora-fs --exclude '*.lock' --exclude '*.tmp' \
              ./backend/uploads ./backend/reports ./backend/data

# Wöchentliche Restic-Forget-Politik.
30 4 * * 0 restic -r /backups/agora forget \
              --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
```

`agora-backup-neo4j.sh` umschließt die `neo4j-admin dump`-Sequenz oben
plus `gzip` und Restic-Push an `/backups/agora`.

### Retention-Vorschlag

| Klasse | Retention |
|---|---|
| Neo4j-Dumps | 7 Tage täglich, 4 Wochen wöchentlich, 6 Monate monatlich. |
| Uploads/Reports (Restic) | analog Neo4j. |
| `.env` | bei Rotation neu sichern; alte Versionen 90 Tage halten. |

---

## Recovery-Reihenfolge (Worst-Case)

1. `docker compose down`. Volumes nicht löschen, falls noch erreichbar.
2. `.env` aus Backup wiederherstellen.
3. Neo4j-Dump ins Volume restauren — siehe oben.
4. Uploads + Reports per Restic restauren:
   ```bash
   restic -r /backups/agora restore latest \
     --target /opt/agora-restore --include backend/uploads --include backend/reports
   rsync -a --delete /opt/agora-restore/backend/uploads/ ./backend/uploads/
   rsync -a --delete /opt/agora-restore/backend/reports/ ./backend/reports/
   ```
5. `docker compose up -d --build`.
6. Smoke-Test: `/api/status`, Cypher-Knoten-Count, ein Run-Detail im
   Frontend öffnen.

Wenn Neo4j-Dump und Restic-Snapshot zeitlich auseinanderlaufen,
gewinnt Neo4j — Reports referenzieren Graph-IDs, also lieber neuere
FS-Daten verwerfen als Graph-Drift einzubauen.

---

## Was nicht gesichert wird (bewusst)

- **Redis** — nur kurzlebige Tickets und Pub/Sub-Backlog. Nach Restore
  sind Live-SSE-Sessions weg, das ist unkritisch.
- **HuggingFace-Cache** — Re-Pull beim ersten OASIS-Run. Ein
  Backup-Eintrag für den Cache verdoppelt das Volumen ohne Mehrwert.
- **`/tmp`-tmpfs** — Definition.

---

## Checks nach jedem Backup

| Check | Wie |
|---|---|
| Dump-Größe plausibel | `du -sh /var/backups/agora/neo4j/*.dump | tail -5`. |
| Restic-Snapshot vorhanden | `restic -r /backups/agora snapshots --tag agora-fs | tail -10`. |
| Cronjob-Log fehlerlos | `journalctl --user -u cron --since '24 hours ago' | grep agora`. |
| Restore-Drill quartalsweise | Termin im Kalender, nicht in `crontab`. |
