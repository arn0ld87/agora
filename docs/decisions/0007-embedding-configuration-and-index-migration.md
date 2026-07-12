# ADR-0007: Embedding-Konfiguration und Indexmigration

- Status: Accepted
- Datum: 2026-07-10 (Proposed), 2026-07-12 (Accepted via PR-Merge für Slice 4.1+4.2)

## Kontext

Embedding-Konfiguration und Dimensionsprüfung sind doppelt verdrahtet. Bei
Dimensionsdrift kann ein Neo4j-Index neu erstellt werden, ohne vorhandene
Embedding-Properties zu migrieren.

## Entscheidung

Chat- und Embedding-Konfiguration werden getrennt. Ein Wechsel mit vorhandenen
Daten nutzt versionierte Properties/Indizes, einen resumierbaren Re-Embedding-
Job, Validierung und atomaren Umschaltpunkt. Ein alter Index bleibt bis zum Ende
der Rollback-Frist bestehen.

`DROP INDEX` ohne Bestätigung, Backup-Plan, erfolgreiche Re-Embedding-
Validierung und Rollback ist verboten.

## Konkrete Umsetzung (Stand 2026-07-12, Slice 4.1+4.2)

* Kanonische Verträge in `backend/app/contracts/embedding_contract.py`:
  `EmbeddingConfiguration` (SSoT), `EmbeddingMigrationJob` (vollständiger
  Lifecycle `pending → running → validating → completed | rolled_back | failed`),
  `EmbeddingIndexVersion` (versionierter Neo4j-Vector-Index mit eigenem
  `index_name` + `property_key` pro Version). Slice 4.1.
* Persistenter Store `backend/app/services/embedding_configuration_store.py`
  mit `flock`-basierter Prozesssperre, atomarem Write (`os.replace`),
  Datei-Modus 0600. Slice 4.2.
* Service `backend/app/services/embedding_configurations/service.py` mit
  anbieter-spezifischer Probe (Ollama lokal, Ollama Cloud, OpenAI,
  OpenAI-kompatibel, Gemini) und Lifecycle-Wechsel mit Eindeutigkeits-
  Garantie: pro `scope` (`global` / `project` + `project_id`) ist
  hoechstens eine Konfiguration gleichzeitig `active`. Slice 4.2.
* Legacy-Adapter `backend/app/services/embedding_configurations/legacy.py`:
  liest `Config.EMBEDDING_*` on-demand, ohne Schreiben in den Store.
  Vermeidet stillen Startup-Repair, der die ADR-Forderung "kein DROP ohne
  Backup-Plan" verletzen würde. Slice 4.2.
* Re-Embedding-Migrations-Engine und Ollama-Download: Slice 4.3 (offen).
  Die in diesem ADR geforderten Garantien sind im Vertrag modelliert,
  werden aber erst in 4.3 vom Verhalten durchgesetzt.

## Folgen

- zusätzlicher Job- und Statusvertrag;
- höherer temporärer Speicherbedarf;
- sichere Wiederaufnahme und klare Operatorentscheidung statt stillem Startup-
Repair.
