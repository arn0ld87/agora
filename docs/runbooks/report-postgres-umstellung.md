# Report-Metadaten auf PostgreSQL umstellen

Überträgt die Report-Metadaten (`uploads/reports/<Schlüssel>/meta.json` und
das Legacy-Flachformat `uploads/reports/<Schlüssel>.json`) nach
`agora.reports` und schaltet die Ablage um. Gegenstück zu
[`simulation-postgres-umstellung.md`](simulation-postgres-umstellung.md) — und
**zeitlich danach**: `agora.reports.simulation_id` ist ein Fremdschlüssel auf
`agora.simulations`. Die empfohlene Reihenfolge ist LLM-Profile → Projekte →
Simulationen → Runs → Reports.

**Was hier nicht passiert:** Report-Inhalte wandern nicht. `report-v3.json`,
`outline.json`, `section_XX.md`, `evidence-map.json` und Logs bleiben unter
`uploads/reports/<Schlüssel>/`, unabhängig davon, wo die Metadaten liegen
(Plan §11 Klasse B). Ein Backup braucht deshalb nach dem Umschalten **beide**
Seiten: die Datenbank und das Report-Verzeichnis.

## Voraussetzungen

- Simulationen sind bereits umgestellt: `AGORA_SIMULATION_BACKEND=postgres`,
  und `migrate_simulations_to_postgres.py --verify` war sauber.
  `Config.validate()` lehnt `AGORA_REPORT_BACKEND=postgres` bei
  `AGORA_SIMULATION_BACKEND=file` beim Start ab.
- `DATABASE_URL` ist gesetzt (`postgresql+psycopg://user:pass@host:5432/db`).
- Ein Backup existiert.

## Der Ablauf braucht ein Wartungsfenster

**Agora muss zwischen Schritt 2 und Schritt 6 angehalten sein.** `migrate`
überspringt einen Schlüssel, der schon in der Tabelle steht. Schreibt eine
laufende Report-Erzeugung nach Schritt 4 ihre `meta.json` fort, landet das
Update nie in PostgreSQL.

`AGORA_REPORT_BACKEND` wird beim Import der `Config`-Klasse **einmal**
gelesen. Die Umstellung greift erst nach einem Neustart.

## Ablauf

### 1. Schema anlegen

```bash
cd backend
uv run alembic -c migrations/alembic.ini upgrade head
```

Legt `agora.reports` an. Die Revision ist `8d6e0b3c2f15`.

### 2. Agora anhalten

```bash
docker compose stop backend    # oder der für die Installation übliche Weg
```

Laufende Report-Erzeugungen vorher zu Ende laufen lassen oder abbrechen.

### 3. Baseline erheben und Bestand zählen

```bash
uv run python scripts/migration_baseline.py --output /tmp/vorher.json
uv run python scripts/migrate_reports_to_postgres.py --dry-run
```

`Scanned` ist die Zahl der Report-Ordner mit `meta.json` plus der
`<Schlüssel>.json`-Dateien im Flachformat. Ein Ordner ohne `meta.json` ist
kein Report und zählt nicht mit. Ein unlesbares Manifest erscheint schon hier
als `FEHLER:` mit Schlüssel.

### 4. Übertragen

```bash
uv run python scripts/migrate_reports_to_postgres.py
```

Ausgabe nach Plan §33:

```text
Scanned:   87
Inserted:  86
Skipped:    0
Failed:     1
FEHLER: report_…: Simulation sim_… fehlt in agora.simulations (…)
```

Idempotent: ein Schlüssel, der schon in der Tabelle steht, wird übersprungen
(`Skipped`) und nicht überschrieben. Ein Fehler betrifft nur den genannten
Report; der Rest wird übertragen. Exit-Code 1, sobald `Failed > 0`.

Die Fehlerarten:

1. **`Simulation … fehlt in agora.simulations`** — die Simulationen wurden
   noch nicht migriert (→ erst
   [`simulation-postgres-umstellung.md`](simulation-postgres-umstellung.md),
   dann diesen Schritt wiederholen), oder die `state.json` der Simulation ist
   unlesbar und fiel dort schon als Fehler auf. Solche Reports sind nach dem
   Umschalten nicht mehr sichtbar. Entscheiden: Simulation reparieren und
   nachmigrieren, Report archivieren, oder nicht umschalten.
2. **`meta.json leer, unlesbar oder ohne Pflichtfeld`** — die Laufzeit
   überspringt einen solchen Report heute schon still.

Der **Ablageschlüssel bleibt der Schlüssel.** Ein Altbestand unter
`report_deepseek_<hex>/` mit `report_<hex>` im Manifest bekommt den
Ordnernamen als Primärschlüssel; seine Inhalte werden weiter gefunden.

### 5. Verlustfreiheit prüfen

```bash
uv run python scripts/migrate_reports_to_postgres.py --verify
```

Vergleicht jedes Feld jedes Reports zwischen `meta.json` und Tabelle. Exit 0
und `Verified:  N/N` heißt: beide Seiten sind feldweise gleich. Jede
Abweichung wird mit Schlüssel, Feldname und beiden Werten ausgegeben.

**Erst weitermachen, wenn dieser Schritt sauber ist.** Dazu die Gegenprobe:

```bash
uv run python scripts/migration_baseline.py --output /tmp/nachher.json
uv run python scripts/migration_baseline.py --compare /tmp/vorher.json /tmp/nachher.json
```

### 6. Umschalten und neu starten

```bash
export AGORA_REPORT_BACKEND=postgres
docker compose up -d backend    # oder der für die Installation übliche Weg
```

### 7. Prüfen, dass die Oberfläche arbeitet

Report-Liste öffnen, einen Report öffnen (Outline, Sections, Evidence),
den Export als JSON und ZIP ziehen, einen Zweig mit Report-Kopie anlegen,
einen Test-Report löschen. Neue Reports dürfen unter `uploads/reports/<id>/`
Inhalte, aber keine `meta.json` mehr anlegen.

## Rückweg

```bash
export AGORA_REPORT_BACKEND=file
```

Danach neu starten. Die `meta.json`-Dateien wurden nie verändert; sie sind
unverändert die Wahrheit. Reports, die nach dem Umschalten entstanden sind,
haben ihre Inhalte zwar unter `uploads/reports/`, aber keine `meta.json` —
sie sind nach dem Rückweg nicht sichtbar. Metadaten-Änderungen nach dem
Umschalten (Status, Markdown) gehen verloren. Ein in PostgreSQL gelöschter
Report hat keinen Ordner mehr; seine alte `meta.json` ist mit dem Ordner
entfernt.

Die Reihenfolge ist umgekehrt zur Umstellung: beim Rückweg der Simulationen
(`AGORA_SIMULATION_BACKEND=file`) muss dieser Schalter **zuerst** zurück;
sonst verweigert `Config.validate()` den Start.

Das Schema lässt sich zurücknehmen, solange noch nichts umgeschaltet war:

```bash
uv run alembic -c migrations/alembic.ini downgrade 3f9b2d7e6a41
```

Das löscht `agora.reports` samt Inhalt; `agora.runs` bleibt stehen.

## Was die Tabelle bewusst so hat

- **`id` ist der Ablageschlüssel, nicht zwingend die `report_id`.** Die
  Inhalte liegen unter dem Ordnernamen; `report_id` steht zusätzlich als
  eigene Spalte. Neue Reports haben beide gleich.
- **`payload` ist der vollständige Datensatz, die Spalten sind abgeleitet.**
  `report_id`, `simulation_id`, `status`, `created_at`, `completed_at` werden
  bei jedem Schreiben aus dem Datensatz gezogen. Gelesen wird allein aus dem
  `payload`, auch der Filter nach Simulation.
- **Kein `workspace_id`.** Multi-User ist eine eigene, freizugebende Phase.
- **Zeitstempel sind `text`.** Der Vertrag führt ISO-8601-Zeichenketten
  (`''` für "noch nicht"); über `timestamptz` käme beim Lesen eine andere
  Zeichenkette zurück.
- **`simulation_id` ist nullable, `ON DELETE SET NULL`.** Ein Report überlebt
  seine Simulation. Ein neuer Report mit unbekannter Simulation scheitert mit
  `ReportSimulationMissing`; ein laufender, dessen Simulation inzwischen
  fehlt, schreibt weiter.
- **Löschen geht über das Repository.** `ReportManager.delete_report` entfernt
  die Zeile und danach den Ordner mit den Inhalten.
- **Kein Check-Constraint auf `status`.** Die Statuswerte leben in
  `ReportStatus`, nicht im Vertrag.
