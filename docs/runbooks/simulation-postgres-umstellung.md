# Simulationsmetadaten auf PostgreSQL umstellen

Überträgt den Inhalt der `state.json`-Dateien nach `agora.simulations` und
schaltet die Ablage um. Gegenstück zu
[`projekt-postgres-umstellung.md`](projekt-postgres-umstellung.md) — und
**zeitlich danach**: `agora.simulations.project_id` ist ein Fremdschlüssel auf
`agora.projects`.

**Was hier nicht passiert:** Laufzeit-Artefakte wandern nicht.
`simulation_config.json`, Profile, `run_state.json`, Logs und IPC-Dateien
bleiben unter `uploads/simulations/<simulation_id>/`, unabhängig davon, wo die
Metadaten liegen.

## Voraussetzungen

- Projekte sind bereits umgestellt: `AGORA_PROJECT_BACKEND=postgres`, und
  `migrate_projects_to_postgres.py --verify` war sauber. `Config.validate()`
  lehnt `AGORA_SIMULATION_BACKEND=postgres` bei `AGORA_PROJECT_BACKEND=file`
  beim Start ab.
- `DATABASE_URL` ist gesetzt (`postgresql+psycopg://user:pass@host:5432/db`).
- Ein Backup existiert.

## Der Ablauf braucht ein Wartungsfenster

**Agora muss zwischen Schritt 2 und Schritt 6 angehalten sein.** Derselbe Grund
wie bei den Projekten: `migrate` überspringt eine Kennung, die schon in der
Tabelle steht. Schreibt eine laufende Simulation nach Schritt 4 ihre
`state.json` fort, landet das Update nie in PostgreSQL.

`AGORA_SIMULATION_BACKEND` wird beim Import der `Config`-Klasse **einmal**
gelesen. Die Umstellung greift erst nach einem Neustart.

## Ablauf

### 1. Schema anlegen

```bash
cd backend
uv run alembic -c migrations/alembic.ini upgrade head
```

Legt `agora.simulations` an. Die Revision ist `c4e8a1d93b56`.

### 2. Agora anhalten

```bash
docker compose stop backend    # oder der für die Installation übliche Weg
```

Laufende Simulationen vorher zu Ende laufen lassen oder abbrechen.

### 3. Baseline erheben und Bestand zählen

```bash
uv run python scripts/migration_baseline.py --output /tmp/vorher.json
uv run python scripts/migrate_simulations_to_postgres.py --dry-run
```

`Scanned` ist die Zahl der Verzeichnisse mit `state.json`. Eine leere oder
unlesbare `state.json` erscheint schon hier als `FEHLER:` mit Kennung.

### 4. Übertragen

```bash
uv run python scripts/migrate_simulations_to_postgres.py
```

Ausgabe nach Plan §33:

```text
Scanned:   412
Inserted:  410
Skipped:     0
Failed:      2
FEHLER: sim_…: Projekt proj_… fehlt in agora.projects (…)
```

Idempotent: eine Kennung, die schon in der Tabelle steht, wird übersprungen
(`Skipped`) und nicht überschrieben. Ein Fehler betrifft nur den genannten
Datensatz; der Rest wird übertragen. Exit-Code 1, sobald `Failed > 0`.

**`Projekt … fehlt in agora.projects`** hat zwei Ursachen:

1. Die Projekte wurden noch nicht migriert → erst
   [`projekt-postgres-umstellung.md`](projekt-postgres-umstellung.md), dann
   diesen Schritt wiederholen.
2. Das Projekt wurde gelöscht, die Simulation blieb liegen (das tut die
   Dateiablage heute). Solche Simulationen sind nach dem Umschalten nicht mehr
   sichtbar. Entscheiden: Verzeichnis archivieren/entfernen, oder die
   Simulation auf der Dateiablage belassen und nicht umschalten.

### 5. Verlustfreiheit prüfen

```bash
uv run python scripts/migrate_simulations_to_postgres.py --verify
```

Vergleicht jedes Feld jeder Simulation zwischen `state.json` und Tabelle.
Exit 0 und `Verified:  N/N` heißt: beide Seiten sind feldweise gleich. Jede
Abweichung wird mit Kennung, Feldname und beiden Werten ausgegeben.

**Erst weitermachen, wenn dieser Schritt sauber ist.** Dazu die Gegenprobe:

```bash
uv run python scripts/migration_baseline.py --output /tmp/nachher.json
uv run python scripts/migration_baseline.py --compare /tmp/vorher.json /tmp/nachher.json
```

### 6. Umschalten und neu starten

```bash
export AGORA_SIMULATION_BACKEND=postgres
docker compose up -d backend    # oder der für die Installation übliche Weg
```

### 7. Prüfen, dass die Oberfläche arbeitet

Simulationsliste eines Projekts öffnen, eine Simulation öffnen, einen Zweig
anlegen. Die Laufzeit-Artefakte müssen weiterhin gefunden werden — sie liegen
unverändert unter `uploads/simulations/<simulation_id>/`.

## Rückweg

```bash
export AGORA_SIMULATION_BACKEND=file
```

Danach neu starten. Die `state.json`-Dateien wurden nie verändert; sie sind
unverändert die Wahrheit. Änderungen, die nach dem Umschalten in PostgreSQL
entstanden sind, stehen nicht in den Dateien — wer zurückgeht, verliert sie.

Beim Rückweg der Projekte (`AGORA_PROJECT_BACKEND=file`) muss dieser Schalter
**zuerst** zurück; sonst verweigert `Config.validate()` den Start.

Das Schema lässt sich zurücknehmen, solange noch nichts umgeschaltet war:

```bash
uv run alembic -c migrations/alembic.ini downgrade 7a3c1e84f209
```

Das löscht `agora.simulations` samt Inhalt; `agora.projects` bleibt stehen.

## Was die Tabelle bewusst so hat

- **Kein `workspace_id`.** Multi-User ist eine eigene, freizugebende Phase.
- **`id` ist `text`.** Die Kennung ist der Verzeichnisname der
  Laufzeit-Artefakte.
- **`created_at`/`updated_at` sind `text`.** Der Vertrag führt ISO-8601-
  Zeichenketten; über `timestamptz` käme beim Lesen eine andere Zeichenkette
  zurück.
- **`project_id` ist nullable, `ON DELETE SET NULL`.** Der Vertrag kennt `''`
  als "kein Projekt" (in der Spalte `NULL`). Wird ein Projekt gelöscht, bleibt
  die Simulation stehen und verliert den Verweis — mit `RESTRICT` bliebe
  `delete_project` nach dem Entfernen der Artefakte an der Zeile hängen.
  Speichert ein noch laufender Vorgang danach seinen alten Zustand mit der
  gelöschten Projektkennung, bleibt der Verweis gelöst, statt den Speichervorgang
  scheitern zu lassen.
- **Kein Check-Constraint auf `status`.** Die Statuswerte leben in
  `SimulationStatus`, nicht im Vertrag; eine zweite Liste im Schema prüfte
  niemand gegen die erste.
