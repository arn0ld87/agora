# Metadaten-Cutover auf PostgreSQL

Fasst die fünf Einzel-Runbooks in der Reihenfolge zusammen, in der sie
gefahren werden müssen, und nennt den Rückweg. Die Einzelheiten jeder Domäne
stehen in ihrem Runbook; dieses Dokument ersetzt sie nicht.

| Schritt | Domäne | Schalter | Runbook | Revision |
|---|---|---|---|---|
| 1 | LLM-Profile | `AGORA_LLM_PROFILE_BACKEND` | [`llm-profile-postgres-umstellung.md`](llm-profile-postgres-umstellung.md) | `b5d2c0a41f7e` |
| 2 | Projekte | `AGORA_PROJECT_BACKEND` | [`projekt-postgres-umstellung.md`](projekt-postgres-umstellung.md) | `7a3c1e84f209` |
| 3 | Simulationen | `AGORA_SIMULATION_BACKEND` | [`simulation-postgres-umstellung.md`](simulation-postgres-umstellung.md) | `c4e8a1d93b56` |
| 4 | Runs | `AGORA_RUN_BACKEND` | [`run-postgres-umstellung.md`](run-postgres-umstellung.md) | `3f9b2d7e6a41` |
| 5 | Reports | `AGORA_REPORT_BACKEND` | [`report-postgres-umstellung.md`](report-postgres-umstellung.md) | `8d6e0b3c2f15` |

Die Reihenfolge folgt den Fremdschlüsseln: Simulationen verweisen auf
Projekte, Runs und Reports auf Simulationen. `Config.validate()` verweigert
den Start, wenn ein Schalter auf `postgres` steht und seine Voraussetzung
nicht. LLM-Profile haben keinen Fremdschlüssel. Sie stehen vorn, weil sie der
kleinste und am besten erprobte Schritt sind.

**Das Wartungsfenster gilt für den gesamten Cutover.** Agora bleibt von der
ersten Übertragung bis zum Neustart mit den neuen Schaltern angehalten. Jedes
Migrationsskript überspringt Datensätze, die schon in PostgreSQL stehen; was
dazwischen in die Dateien geschrieben wird, landet nie in der Datenbank.

## Voraussetzungen

- `DATABASE_URL` ist gesetzt (`postgresql+psycopg://user:pass@host:5432/db`).
- Ein Backup existiert, **und der Restore ist geprobt**
  ([`restore-drill.md`](restore-drill.md)). Nach dem Cutover gehört die
  Datenbank zum Backup. Die Dateien unter `uploads/` gehören weiter dazu:
  Report-Inhalte und Simulationsartefakte bleiben dort.
- Neo4j und Redis sind vom Cutover nicht betroffen.

## Ablauf

### 1. Schema auf den Head bringen

```bash
cd backend
uv run alembic -c migrations/alembic.ini upgrade head
```

### 2. Agora anhalten

```bash
docker compose stop backend    # oder der für die Installation übliche Weg
```

Laufende Graph-Builds, Simulationen und Report-Erzeugungen vorher zu Ende
laufen lassen oder abbrechen.

### 3. Baseline vorher

```bash
uv run python scripts/migration_baseline.py --output /tmp/vorher.json
```

### 4. Übertragen, in dieser Reihenfolge

```bash
uv run python scripts/migrate_llm_profiles_to_postgres.py
uv run python scripts/migrate_projects_to_postgres.py
uv run python scripts/migrate_simulations_to_postgres.py
uv run python scripts/migrate_runs_to_postgres.py
uv run python scripts/migrate_reports_to_postgres.py
```

Jedes Skript kann vorher mit `--dry-run` gezählt werden. Meldet ein Skript
`Failed > 0`, erklärt das Einzel-Runbook die Fehlerarten. Erst weitermachen,
wenn jeder Fehler entschieden ist. Ein Datensatz, der nicht übertragen wurde,
ist nach dem Umschalten nicht mehr sichtbar.

### 5. Baseline nachher und Sammelprüfung

```bash
uv run python scripts/migration_baseline.py --output /tmp/nachher.json
uv run python scripts/verify_metadata_cutover.py --baseline /tmp/vorher.json /tmp/nachher.json
```

`verify_metadata_cutover.py` prüft in Cutover-Reihenfolge:

| Schritt | Prüft |
|---|---|
| `flags` | Schalter untereinander konsistent (dieselben Regeln wie `Config.validate()`), `DATABASE_URL` gesetzt |
| `alembic_head` | Datenbank steht auf dem Alembic-Head (dieselbe Prüfung wie das Start-Gate) |
| `llm_profiles` … `reports` | das `--verify` jedes Migrationsskripts: jeder Datensatz feldweise gleich. Dazu kommt die Gegenrichtung: Eine Zeile, die nur in PostgreSQL steht (etwa ein Rest aus einem früheren Versuch), ist `FEHLER`. Fehlt die Quelle (Verzeichnis oder SQLite), ist der Schritt `UNGEPRÜFT` und nicht `OK 0/0`. |
| `baseline` | `migration_baseline.py --compare`: Anzahl, IDs, Felder und Prüfsummen unverändert |

Ausgabe nach Plan §33:

```text
[OK] flags: Verified 1/1
[OK] alembic_head: Verified 1/1
[OK] llm_profiles: Verified 3/3
…
Scanned:   8
Inserted:  0
Skipped:   0
Failed:    0
Verified:  8/8
```

**Exit 0 nur, wenn jeder Schritt `OK` ist.** Exit 1 bedeutet: mindestens ein
Schritt ist `FEHLER`. Exit 2 bedeutet: nichts ist rot, aber mindestens ein
Schritt ist `UNGEPRÜFT`, typischerweise die Baseline ohne `--baseline` oder
mit einer Klasse, deren Quelle nicht erreichbar war (Neo4j). Ein ungeprüfter
Schritt ist kein Erfolg. Entweder die Ursache beheben oder bewusst
entscheiden und das Ergebnis festhalten.

Die Sammelprüfung darf **vor** dem Umschalten laufen. `flags` prüft die
Schalter so, wie sie in der Umgebung des Aufrufs stehen. Zur Prüfung der
Zielkonfiguration werden die Schalter für den Aufruf gesetzt:

```bash
AGORA_LLM_PROFILE_BACKEND=postgres AGORA_PROJECT_BACKEND=postgres \
AGORA_SIMULATION_BACKEND=postgres AGORA_RUN_BACKEND=postgres \
AGORA_REPORT_BACKEND=postgres \
uv run python scripts/verify_metadata_cutover.py --baseline /tmp/vorher.json /tmp/nachher.json
```

### 6. Umschalten und neu starten

Alle fünf Schalter in der Umgebung der Installation auf `postgres` setzen,
dann neu starten. Das Start-Gate (#1582) bricht ab, wenn das Schema nicht auf
dem Head steht. `/readyz` meldet den PostgreSQL-Zustand (#1581).

### 7. Prüfen, dass die Oberfläche arbeitet

Die Punkte „Prüfen, dass die Oberfläche arbeitet“ der fünf Einzel-Runbooks
nacheinander abarbeiten.

## Rückweg

Die Schalter gehen **in umgekehrter Reihenfolge** zurück. Sonst verweigert
`Config.validate()` den Start:

```bash
export AGORA_REPORT_BACKEND=file
export AGORA_RUN_BACKEND=file
export AGORA_SIMULATION_BACKEND=file
export AGORA_PROJECT_BACKEND=file
export AGORA_LLM_PROFILE_BACKEND=sqlite
```

Danach neu starten. Die Dateien und die SQLite wurden nie verändert und sind
wieder die Wahrheit. Was nach dem Umschalten nur in PostgreSQL entstanden
oder geändert wurde, fehlt dort. Das betrifft neue Projekte, Simulationen,
Runs und Reports, jeden Statuswechsel und jedes gelöschte Element, das in den
Dateien noch steht. Wie viel das ist, hängt von der Zeit seit dem Umschalten
ab. Der Rückweg ist deshalb für die ersten Stunden nach dem Cutover gedacht,
nicht für Wochen später.

Ein Teil-Rückweg ist möglich, solange die Reihenfolge stimmt: Reports allein
auf `file` zurück geht, Simulationen allein nicht, solange Runs oder Reports
auf `postgres` stehen.

Das Schema lässt sich zurücknehmen, solange nichts umgeschaltet ist. Die
Revisionen stehen in der Tabelle oben. `downgrade` auf die Revision **vor**
der Domäne entfernt deren Tabelle samt Inhalt und alle späteren.

## Was dieses Runbook nicht abdeckt

- Den Cutover auf dem Produktivhost (#1592). Dort kommen Host-spezifische
  Schritte dazu: Compose-Datei, Umgebung, Backup-Ziel.
- Blob-Storage (#1584, #1586). Uploads, Exports und Report-Inhalte bleiben
  im Dateisystem.
- Das Löschen der Legacy-Ablagen. Frühestens zwei stabile Releases nach dem
  Cutover (Plan §35).
