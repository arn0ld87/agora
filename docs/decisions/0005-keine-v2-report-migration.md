# ADR-0005: Keine v2→ReportV3-Migration mehr vorhalten

- Status: akzeptiert
- Datum: 2026-09-08
- Bezug: schließt den Migrationspfad aus Sub-Slice P3.1 (`PLAN.md §4.1`);
  berührt [ADR-0002](0002-evidence-gating.md) nicht

## Kontext

`backend/app/services/evidence_migrations.py::migrate_v2_to_v3` baute aus einem
v2-Report-Dict eine gegen `ReportV3` validierbare Struktur. Die Funktion war mit
zyklomatischer Komplexität 68 der zweithöchste Hotspot des Projekts, nach
`ReportManager.build_report_v3` (69), und stand als eigener Eintrag mit
Obergrenze `# cc<=68` in `backend/radon-allowlist.txt`.

Sie stand damit auf jeder Refactoring-Liste weit oben. Vor dem ersten Schnitt
wurde ihre Erreichbarkeit geprüft — mit einem Ergebnis, das jeden Refactor
gegenstandslos macht.

## Befund

1. **Kein Produktionsaufrufer.** `grep` über `backend/app/` findet außer der
   Definition und zwei Docstring-Erwähnungen keinen Aufruf. Auch
   `backend/scripts/migrate_v2_full_report_to_v3.py` importiert sie nicht.

2. **Der produktive ReportV3-Pfad ist ein anderer.** `ReportV3` entsteht
   ausschließlich in `report_agent/manager.py::build_report_v3`. Personas,
   Segments, FrictionPoints und TrustSignals kommen dort aus
   `merge_section_metadata` — im Code ausdrücklich als kanonische Quelle
   kommentiert und als Ersatz für den leeren ReportV3-Pfad eingeführt (P0-6).
   Persistierte ReportV3-Dateien hebt
   `report_agent/storage.py::_upgrade_report_v3_payload` auf Schema 4, eine
   eigenständige, deutlich kleinere Implementierung.

3. **Es existiert kein migrierbarer Bestand.** Gemessen am 08.09.2026 gegen
   `backend/uploads/reports/` (16 Report-Ordner, Mai bis August 2026): acht
   Ordner tragen eine `report-v3.json`, **alle auf `schema_version=4`**, keiner
   auf 3 oder darunter. Die acht übrigen haben gar keine — ihr Status ist
   ausnahmslos `incomplete`, `failed` oder `stopped`, es sind abgebrochene
   Läufe ohne migrierbaren Inhalt. Agora ist ein Single-User-System ohne
   Fremd-Deployments; eine andere Bestandsmenge existiert nicht.

4. **Am Leben gehalten wurde die Funktion allein durch Tests.** Aufrufer waren
   `tests/services/test_evidence_migrations_aggregation.py` (16 von 16 Tests),
   fünf Tests in `tests/contracts/test_report_v3_contract.py` und einer in
   `tests/services/test_legacy_evidence_identity_migration.py`. Zuletzt
   inhaltlich geändert wurde sie am 11.05.2026 (Commit `83b74882`).

Damit gilt: der Pfad hat nie einen realen Report berührt und kann keinen mehr
erreichen. Ein Refactor hätte 68 Komplexitätspunkte auf Code investiert, den
nichts aufruft.

## Entscheidung

`migrate_v2_to_v3` und ihre ausschließlich von ihr genutzte Helfer-Hülle werden
ersatzlos entfernt: `_resolve_evidence_refs`, `_label_to_confidence`,
`_section_title_matches`, `_load_personas_from_store`, `_map_profile_to_persona`,
`_aggregate_segments`. Die Abgrenzung wurde per AST über die transitive Hülle
bestimmt, nicht per Textsuche.

Eine Auslagerung als CLI-Skript wäre Konservierung ohne Gegenstand: es gibt
kein Eingabeformat mehr, das damit gefüttert werden könnte.

## Was ausdrücklich bleibt

`normalize_persisted_evidence_map`, `migrate_v1_to_v2`,
`migrate_evidence_map_v2_to_v3`, `demote_unanchored_seed_corpus_records`,
`migrate_legacy_claims_to_anchored`, `migrate_medium_seed_only_claims_to_low`,
`strip_seed_doc_anchor_from_agent_quote_records` und
`_legacy_item_to_record_and_binding`. Diese sind über
`normalize_persisted_evidence_map` live erreichbar und werden quer durch
`report.py`, `report_export.py` und vier `report_agent`-Module importiert.
Die Evidence-Map-Migration v1→v2→v3 bleibt damit vollständig erhalten — entfallen
ist ausschließlich der Report-**Container**-Aufbau.

Die Semantik `legacy_unresolved` (unaufgelöste Legacy-Evidence wird Hypothese,
nicht Claim) bleibt in `migrate_evidence_map_v2_to_v3` bestehen und ist über
`tests/api/test_report_evidence_route.py` abgedeckt.

## Konsequenzen

- 390 Zeilen Produktcode entfallen, `evidence_migrations.py` schrumpft von 1092
  auf 702 Zeilen.
- Der zweithöchste Komplexitäts-Hotspot des Projekts verschwindet; zwei
  Einträge fallen aus `radon-allowlist.txt` (`migrate_v2_to_v3  # cc<=68` und
  `_map_profile_to_persona  # cc<=21`).
- Die einzige Kopplung des Moduls an `artifact_store` entfällt — der
  `TYPE_CHECKING`-Import ist ersatzlos weg.
- 22 Tests entfallen, die ausschließlich totes Verhalten prüften.

## Rückweg

Sollte je ein v2-Report-Dict auftauchen, das nach ReportV3 gehoben werden muss,
ist der Weg die Wiederherstellung aus der Git-Historie (Stand `4fed7839`) als
einmaliges Skript — nicht die Rückkehr in den Modul-Pfad.
