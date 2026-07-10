# ADR-0007: Embedding-Konfiguration und Indexmigration

- Status: Proposed
- Datum: 2026-07-10

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

## Folgen

- zusätzlicher Job- und Statusvertrag;
- höherer temporärer Speicherbedarf;
- sichere Wiederaufnahme und klare Operatorentscheidung statt stillem Startup-
Repair.
