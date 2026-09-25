# Run-Registry auf PostgreSQL umstellen

Überträgt die Run-Manifeste (`uploads/run_registry/<run_id>.json`) nach
`agora.runs` und schaltet die Ablage um. Gegenstück zu
[`simulation-postgres-umstellung.md`](simulation-postgres-umstellung.md) — und
**zeitlich danach**: `agora.runs.simulation_id` ist ein Fremdschlüssel auf
`agora.simulations`.

**Was hier nicht passiert:** Laufzeit-Artefakte wandern nicht.
`run_state.json`, Logs, Report-Dateien und Graph-Artefakte bleiben, wo sie
sind. Lease und Heartbeat (`metadata.owner_pid`, `owner_token`,
`heartbeat_at`, `lease_ttl_s`) bekommen keine eigene Spalte; sie stehen
weiter im Manifest, das jetzt in `agora.runs.payload` liegt.

## Voraussetzungen

- Simulationen sind bereits umgestellt: `AGORA_SIMULATION_BACKEND=postgres`,
  und `migrate_simulations_to_postgres.py --verify` war sauber.
  `Config.validate()` lehnt `AGORA_RUN_BACKEND=postgres` bei
  `AGORA_SIMULATION_BACKEND=file` beim Start ab.
- `DATABASE_URL` ist gesetzt (`postgresql+psycopg://user:pass@host:5432/db`).
- Ein Backup existiert.

## Der Ablauf braucht ein Wartungsfenster

**Agora muss zwischen Schritt 2 und Schritt 6 angehalten sein.** `migrate`
überspringt eine Kennung, die schon in der Tabelle steht. Schreibt ein
laufender Job nach Schritt 4 sein Manifest fort — Heartbeat, Fortschritt,
Endstatus —, landet das Update nie in PostgreSQL.

`AGORA_RUN_BACKEND` wird beim Import der `Config`-Klasse **einmal** gelesen.
Die Umstellung greift erst nach einem Neustart. Die Start-Reconciliation
liest danach die Registry aus PostgreSQL; der Prozess-Adapter hat dafür einen
Verbindungs-Timeout von 10 s, damit ein nicht erreichbarer Server den Start
nicht minutenlang aufhält.

## Ablauf

### 1. Schema anlegen

```bash
cd backend
uv run alembic -c migrations/alembic.ini upgrade head
```

Legt `agora.runs` an. Die Revision ist `3f9b2d7e6a41`.

### 2. Agora anhalten

```bash
docker compose stop backend    # oder der für die Installation übliche Weg
```

Laufende Graph-Builds, Vorbereitungen, Simulationen und Report-Läufe vorher
zu Ende laufen lassen oder abbrechen.

### 3. Baseline erheben und Bestand zählen

```bash
uv run python scripts/migration_baseline.py --output /tmp/vorher.json
uv run python scripts/migrate_runs_to_postgres.py --dry-run
```

`Scanned` ist die Zahl der Manifeste (`*.json`, ohne Temp-Dateien
`.tmp-json-*`). Ein leeres oder unlesbares Manifest erscheint schon hier als
`FEHLER:` mit Kennung.

### 4. Übertragen

```bash
uv run python scripts/migrate_runs_to_postgres.py
```

Ausgabe nach Plan §33:

```text
Scanned:   1204
Inserted:  1201
Skipped:      0
Failed:       3
FEHLER: run_…: Simulation sim_… fehlt in agora.simulations (…)
```

Idempotent: eine Kennung, die schon in der Tabelle steht, wird übersprungen
(`Skipped`) und nicht überschrieben. Ein Fehler betrifft nur den genannten
Run; der Rest wird übertragen. Exit-Code 1, sobald `Failed > 0`.

Die Fehlerarten:

1. **`Simulation … fehlt in agora.simulations`** — die Simulationen wurden
   noch nicht migriert (→ erst
   [`simulation-postgres-umstellung.md`](simulation-postgres-umstellung.md),
   dann diesen Schritt wiederholen), oder die `state.json` der Simulation ist
   unlesbar und fiel dort schon als Fehler auf. Solche Runs sind nach dem
   Umschalten nicht mehr sichtbar. Entscheiden: Simulation reparieren und
   nachmigrieren, Manifest archivieren, oder nicht umschalten.
2. **`Manifest trägt abweichende run_id`** — Dateiname und `run_id` im
   Manifest stimmen nicht überein. Die Laufzeit findet einen Run über den
   Dateinamen; unter der anderen Kennung fände ihn niemand wieder. Manifest
   prüfen und von Hand bereinigen.
3. **`Manifest leer oder unlesbar`** — kaputtes JSON. Die Laufzeit überspringt
   es heute schon still.

### 5. Verlustfreiheit prüfen

```bash
uv run python scripts/migrate_runs_to_postgres.py --verify
```

Vergleicht jedes Feld jedes Manifests zwischen Datei und Tabelle — auch, ob
ein Feld auf einer Seite fehlt, das auf der anderen `null` ist. Exit 0 und
`Verified:  N/N` heißt: beide Seiten sind feldweise gleich. Jede Abweichung
wird mit Kennung, Feldname und beiden Werten ausgegeben.

**Erst weitermachen, wenn dieser Schritt sauber ist.** Dazu die Gegenprobe:

```bash
uv run python scripts/migration_baseline.py --output /tmp/nachher.json
uv run python scripts/migration_baseline.py --compare /tmp/vorher.json /tmp/nachher.json
```

### 6. Umschalten und neu starten

```bash
export AGORA_RUN_BACKEND=postgres
docker compose up -d backend    # oder der für die Installation übliche Weg
```

### 7. Prüfen, dass die Oberfläche arbeitet

Run-Übersicht öffnen, einen Run öffnen (Events, Artefakte), einen
abgebrochenen Run fortsetzen (`POST /api/runs/<id>/resume`). Ein Run mit
aktiver Lease muss weiter mit `409 job_lease_active` antworten. Neue Runs
dürfen unter `uploads/run_registry/` keine Datei mehr anlegen.

## Rückweg

```bash
export AGORA_RUN_BACKEND=file
```

Danach neu starten. Die Manifeste unter `uploads/run_registry/` wurden nie
verändert; sie sind unverändert die Wahrheit. Runs, die nach dem Umschalten
in PostgreSQL entstanden oder fortgeschrieben wurden, stehen nicht in den
Dateien — wer zurückgeht, verliert sie.

Die Reihenfolge ist umgekehrt zur Umstellung: beim Rückweg der Simulationen
(`AGORA_SIMULATION_BACKEND=file`) muss dieser Schalter **zuerst** zurück;
sonst verweigert `Config.validate()` den Start.

Das Schema lässt sich zurücknehmen, solange noch nichts umgeschaltet war:

```bash
uv run alembic -c migrations/alembic.ini downgrade c4e8a1d93b56
```

Das löscht `agora.runs` samt Inhalt; `agora.simulations` bleibt stehen.

## Was die Tabelle bewusst so hat

- **`payload` ist das vollständige Manifest, die Spalten sind abgeleitet.**
  `RunRecord.to_manifest()` unterscheidet "Feld fehlt" von "Feld ist `null`";
  eine Spalte kann das nicht tragen. `run_type`, `entity_id`, `status`,
  `simulation_id` und die drei Zeitstempel werden bei jedem Schreiben aus dem
  Manifest gezogen und dienen Sortierung, Filter und Fremdschlüssel.
- **Kein `workspace_id`.** Multi-User ist eine eigene, freizugebende Phase.
- **`id` und Zeitstempel sind `text`.** Der Vertrag führt ISO-8601-
  Zeichenketten; über `timestamptz` käme beim Lesen eine andere Zeichenkette
  zurück.
- **`simulation_id` ist nullable, `ON DELETE SET NULL`.** Der Wert stammt aus
  `linked_ids.simulation_id`; Graph-Build-Runs haben keinen. Die
  Run-Historie überlebt eine gelöschte Simulation; der Verweis im Manifest
  bleibt erhalten. Ein neuer Run mit unbekannter Simulation scheitert mit
  `RunSimulationMissing`; ein bestehender Run, dessen Simulation inzwischen
  fehlt, schreibt weiter (die Registry hält das Manifest im Cache).
- **Kein Check-Constraint auf `status`.** `RunRecord` nimmt jeden Status an
  (Altbestand); die Kanonisierung macht `RunRegistry.canonical_status` beim
  Schreiben.
