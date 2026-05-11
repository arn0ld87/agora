# Sub-Slice 23 — v1→v2 Report-Migration-Skript (Closes #107)

**Datum:** 2026-05-03
**Branch:** `feat/layer-5-task-18-migrate-reports-v1-v2`
**Layer:** 5 (Eval/Baseline)

## Ziel

Einmaliges Migrations-Skript, das gespeicherte v1-Evidence-Maps auf
`schema_version=2` hebt. Schließt den letzten offenen Sub-Task von #107
(Schema-Drift-Fix war bereits in Sub-Slice 02a/02b gelandet; Laufzeit-Migration
in `report.py:434`; Bestandsdaten auf Disk blieben bislang unmigriert).

## Geänderte / neue Dateien

| Datei | Art | Beschreibung |
|---|---|---|
| `backend/scripts/__init__.py` | NEU (leer) | Macht `scripts/` als Python-Package für `python -m` aufrufbar |
| `backend/scripts/migrate_reports_v1_to_v2.py` | NEU | CLI-Skript mit `main(argv)` |
| `backend/tests/scripts/test_migrate_reports_v1_to_v2.py` | NEU | 6 Tests (tmp_path-Fixtures) |
| `backend/pyproject.toml` | GEÄNDERT | `--import-mode=importlib` + `pythonpath=["."]` zu pytest `addopts` |
| `docs/2026-05-03-sub-slice-23-arbeitsprotokoll.md` | NEU | Dieses Dokument |
| `CHANGELOG.md` | GEÄNDERT | `[Unreleased] ### Added` Bullet |

## Designentscheidungen

**Namespace-Konflikt `tests/scripts/` vs `backend/scripts/`:** Das bestehende
`tests/scripts/__init__.py` registriert `scripts` als Python-Package unter dem
Tests-Namespace. Das überdeckt beim Sammeln den Top-Level-Import aus
`backend/scripts/`. Lösung: Das Test-Modul lädt das Migrations-Skript via
`importlib.util.spec_from_file_location` direkt aus dem Dateisystem — kein
namespace-abhängiger Import, aber `main(argv)` und `_process_file` bleiben direkt
aufrufbar (kein Subprozess).

**Section-`schema_version` stripping:** `migrate_v1_to_v2` setzt `schema_version`
auf Section-Ebene zur internen Markierung. `ReportSectionModel` kennt dieses Feld
aber nicht (`extra="forbid"`). Das Skript ruft `_strip_section_schema_version()`
vor `EvidenceMapModel.model_validate` auf, um den `extra_forbidden`-Fehler zu
vermeiden. Das kanonische `schema_version` sitzt ausschließlich auf
`EvidenceMapModel`-Ebene.

**Idempotenz:** Backup wird nur angelegt wenn `<datei>.v1.bak.json` noch nicht
existiert. Zweiter Lauf detektiert `schema_version == CURRENT_SCHEMA_VERSION` und
tut nichts.

## Test-Ergebnis

```
6 passed in 0.77s
```

Gesamtsuite: 1282 passed, 9 skipped (identisch mit Baseline, +6 neue Tests in
1289 collected).

## Vorher/Nachher-Beispiel

### v1-Datei (Bestandsdaten auf Disk)

```json
{
  "schema_version": 1,
  "report_id": "rep-abc",
  "simulation_id": "sim-xyz",
  "global_evidence": [],
  "sections": [
    {
      "schema_version": 1,
      "section_index": 1,
      "section_title": "Reaktionen der Zielgruppe",
      "section_summary": "Zusammenfassung",
      "claims": [
        {
          "claim_id": "claim_01",
          "claim_text": "Die Mehrheit lehnt das Produkt ab.",
          "confidence_label": "medium",
          "confidence_score": 0.55,
          "evidence": [],
          "audit_trail": []
        }
      ]
    }
  ]
}
```

### v2-Datei (nach Migration)

```json
{
  "schema_version": 2,
  "report_id": "rep-abc",
  "simulation_id": "sim-xyz",
  "global_evidence": [],
  "sections": [
    {
      "section_index": 1,
      "section_title": "Reaktionen der Zielgruppe",
      "section_summary": "Zusammenfassung",
      "claims": [
        {
          "claim_id": "claim_01",
          "claim_text": "Die Mehrheit lehnt das Produkt ab.",
          "confidence_label": "medium",
          "confidence_score": 0.55,
          "evidence": [],
          "audit_trail": []
        }
      ]
    }
  ]
}
```

Unterschiede: `schema_version` von 1 auf 2 gehoben; `sections[].schema_version`
entfernt (nicht Teil von `ReportSectionModel`). Backup `<datei>.v1.bak.json`
enthält den ursprünglichen Zustand.

## Schema-Drift

Kein Drift — `git diff schemas/` leer. Das Skript konsumiert bestehende Contracts,
definiert keine neuen.
