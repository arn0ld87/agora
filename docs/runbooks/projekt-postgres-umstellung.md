# Projektmetadaten auf PostgreSQL umstellen

Überträgt den Inhalt der `project.json`-Dateien nach `agora.projects` und
schaltet die Ablage um. Gegenstück zu
[`llm-profile-postgres-umstellung.md`](llm-profile-postgres-umstellung.md).

**Was hier nicht passiert:** Artefakte wandern nicht. `files/`,
`extracted_text.txt` und das Dokument-Manifest bleiben auf dem Dateisystem,
unabhängig davon, wo die Metadaten liegen. Das ist keine Zwischenlösung,
sondern die Festlegung des Plans.

## Voraussetzungen

- Die Supabase-/PostgreSQL-Instanz läuft und ist erreichbar.
- `DATABASE_URL` ist gesetzt (`postgresql+psycopg://user:pass@host:5432/db`).
- Ein Backup existiert. Der Rückweg unten setzt voraus, dass die Dateien noch
  da sind — das Skript rührt sie nicht an, aber ein Backup ersetzt das nicht.

## Der Ablauf braucht ein Wartungsfenster

**Agora muss zwischen Schritt 2 und Schritt 6 angehalten sein. Sonst gehen Daten
verloren, ohne dass ein Werkzeug es meldet.**

Der Grund ist keine Schwäche des Skripts, sondern eine Folge seiner
Idempotenz: `migrate` überträgt ein Projekt, dessen Kennung schon in der
Tabelle steht, **nicht erneut** — es überspringt es. Das ist richtig, damit ein
zweiter Lauf nach einem Abbruch nichts überschreibt. Es heißt aber auch:

Läuft Agora während der Migration weiter, kann ein Graph-Build nach Schritt 4
eine `project.json` aktualisieren. `--verify` in Schritt 5 vergleicht danach
und meldet die Abweichung — aber wer sie durch einen erneuten `migrate`-Lauf
beheben will, stellt fest, dass das Projekt übersprungen wird. Und schließt der
Build erst **nach** Schritt 5 ab, meldet `--verify` gar nichts: der Stand von
Schritt 4 gilt als geprüft, das Update landet nie in PostgreSQL, und nach dem
Umschalten zeigt die Oberfläche dauerhaft den alten Stand.

Ebenfalls wichtig: `AGORA_PROJECT_BACKEND` wird beim Import der `Config`-Klasse
**einmal** gelesen. Die Variable zu setzen genügt nicht — der Prozess muss neu
starten, damit die Umstellung greift.

## Ablauf

### 1. Schema anlegen

```bash
cd backend
uv run alembic -c migrations/alembic.ini upgrade head
```

Legt `agora.projects` an. Die Revision ist `7a3c1e84f209`.

Wird dieser Schritt vor dem Umschalten von `AGORA_PROJECT_BACKEND` vergessen, startet Agora seit Issue #1582 nicht mehr still gegen die fehlende Tabelle — `create_app` prüft beim Start die Alembic-Revision der Datenbank gegen den Head aus `backend/migrations/` und bricht mit einer Meldung ab, die beide Revisionen nennt (`app/infrastructure/postgres/schema_gate.py`). Vorher hätte die Anwendung anstandslos gestartet und wäre erst beim ersten Projektzugriff mit einem Datenbankfehler gescheitert.

### 2. Agora anhalten

```bash
docker compose stop backend    # oder der für die Installation übliche Weg
```

Ab hier bis Schritt 6 schreibt niemand mehr in die `project.json`-Dateien. Das
ist die Voraussetzung dafür, dass `--verify` in Schritt 5 überhaupt etwas
aussagt — siehe oben.

Laufende Graph-Builds oder Simulationen vorher zu Ende laufen lassen oder
abbrechen; ein Lauf, der beim Stoppen mitten in der Arbeit ist, hinterlässt
ohnehin keinen wiederaufnehmbaren Zustand
([#1472](https://github.com/arn0ld87/agora/issues/1472)).

### 3. Baseline erheben und Bestand zählen

```bash
uv run python scripts/migration_baseline.py --output /tmp/vorher.json
uv run python scripts/migrate_projects_to_postgres.py --dry-run
```

Die Baseline ist der Nachweis, dass die Migration **nichts anderes** beschädigt
— sie erhebt neben den Projekten auch Simulationen, Läufe, Berichte, Personas,
LLM-Profile und Prüfsummen über die Artefaktdateien. Ohne sie wäre in Schritt 6
nur belegt, dass die Projekte stimmen, nicht dass der Rest unangetastet blieb.
Dasselbe Vorgehen wie in
[`llm-profile-postgres-umstellung.md`](llm-profile-postgres-umstellung.md).

Die von `--dry-run` gemeldete Zahl ist die Anzahl der Verzeichnisse mit lesbarer
`project.json`. Weicht sie von der erwarteten Projektzahl ab, hier anhalten und
nachsehen: ein Verzeichnis ohne `project.json` ist ein halb angelegtes Projekt
und wird übersprungen, eine **unlesbare** Datei bricht dagegen ab.

### 4. Übertragen

```bash
uv run python scripts/migrate_projects_to_postgres.py
```

Idempotent. Ein Projekt, dessen Kennung schon in der Tabelle steht, wird
übersprungen und **nicht** überschrieben. Nach einem Abbruch kann derselbe
Befehl ohne Weiteres wiederholt werden.

### 5. Verlustfreiheit prüfen

```bash
uv run python scripts/migrate_projects_to_postgres.py --verify
```

Vergleicht jedes Feld jedes Projekts zwischen Datei und Tabelle. Exit 0 und
`OK: …` heißt: beide Seiten sind feldweise gleich. Jede Abweichung wird mit
Projektkennung, Feldname und beiden Werten ausgegeben.

**Erst weitermachen, wenn dieser Schritt sauber ist.**

Dazu die Gegenprobe über die Baseline aus Schritt 3:

```bash
uv run python scripts/migration_baseline.py --output /tmp/nachher.json
uv run python scripts/migration_baseline.py --compare /tmp/vorher.json /tmp/nachher.json
```

Erwartet wird „Kein Unterschied gefunden". Die Migration schreibt nur nach
PostgreSQL; jede Abweichung auf der Dateiseite hieße, dass etwas anderes
mitgelaufen ist — dann anhalten und nachsehen, statt umzuschalten.

Meldet das Werkzeug zusätzlich „nicht alles war vergleichbar", benennt es
Objektklassen, die es nicht erreichen konnte (etwa Neo4j bei abgeschaltetem
Graph). Das ist kein Fehler, aber es schränkt ein, was der Vergleich belegt —
die genannten Klassen sind dann ungeprüft, nicht bestätigt.

### 6. Umschalten und neu starten

```bash
export AGORA_PROJECT_BACKEND=postgres
docker compose up -d backend    # oder der für die Installation übliche Weg
```

**Der Neustart ist Teil des Schritts, nicht optional.**
`AGORA_PROJECT_BACKEND` wird beim Import der `Config`-Klasse einmal gelesen;
ein laufender Prozess sieht die geänderte Variable nicht und schreibt weiter in
die Dateien.

Der Schalter ist getrennt von `AGORA_METADATA_BACKEND` und
`AGORA_LLM_PROFILE_BACKEND` — die Stores werden einzeln umgestellt.

`Config.validate()` lehnt `postgres` ohne gesetzte `DATABASE_URL` beim Start
ab, statt es beim ersten Projektzugriff scheitern zu lassen.

### 7. Prüfen, dass die Oberfläche arbeitet

Projektliste öffnen, ein Projekt öffnen, einen Graph-Build starten. Die
Artefakte müssen weiterhin gefunden werden — sie liegen unverändert unter
`uploads/projects/<project_id>/`, und die Kennung hat sich durch die Migration
nicht geändert.

## Rückweg

```bash
export AGORA_PROJECT_BACKEND=file
```

Mehr ist nicht nötig. Die Dateien wurden nie verändert, gelöscht oder
verschoben; sie sind unverändert die Wahrheit.

**Wichtig:** Änderungen, die nach dem Umschalten in PostgreSQL entstanden sind,
stehen nicht in den Dateien. Wer zurückgeht, verliert sie. Umgekehrt sind die
Dateien nach dem Umschalten eingefroren — sie altern, sobald die Anwendung auf
PostgreSQL schreibt.

Das Schema lässt sich zurücknehmen, wenn es sein muss:

```bash
uv run alembic -c migrations/alembic.ini downgrade -1
```

Das löscht `agora.projects` samt Inhalt. Nur sinnvoll, solange noch nichts
umgeschaltet war.

## Was die Tabelle bewusst nicht hat

- **Kein `workspace_id`.** Multi-User ist eine eigene, freizugebende Phase.
- **Der Primärschlüssel ist `text`, nicht `uuid`.** `project_id` ist zugleich
  der Verzeichnisname der Artefakte; ein Formatwechsel bräche jeden Pfad.
- **`created_at`/`updated_at` sind `text`.** Der Vertrag führt ISO-8601-
  Zeichenketten; über `timestamptz` käme beim Lesen eine andere Zeichenkette
  zurück, und der Datensatz wäre nicht mehr zeichengleich zur Datei.
- **Keine Secrets.** `llm_provider` trägt ausschließlich `redacted_metadata()`.
