# Sub-Slice 02c — EvidenceMapModel-Validation am Schreib-Boundary in report_agent.py

**Datum:** 2026-05-02
**Refs:** #107 (Layer-0 Contract-Architektur)
**Branch:** feat/layer-0-task-02c-pydantic-generator

## Was geändert

### `backend/app/services/report_agent.py`

| Stelle | Art | Beschreibung |
|--------|-----|-------------|
| Z. 25 (neu) | Import | `from ..contracts import EvidenceMapModel` |
| Z. 181–193 | Refactor | `_init_evidence_map`: rohes Dict wird via `EvidenceMapModel.model_validate(payload).model_dump(mode="json")` validiert, bevor es in `self.evidence_map` gespeichert wird |
| Z. 565–586 | Refactor | `_save_evidence_section`: (1) `schema_version`-Key aus Section-Dicts entfernt (war Legacy-Feld aus `migrate_v1_to_v2`, `ReportSectionModel` hat es nicht), (2) gesamte Map vor `save_evidence_map` validiert via `EvidenceMapModel.model_validate(self.evidence_map).model_dump(mode="json")` |
| Z. 1133–1143 | Refactor | Fallback-Init im Tool-Loop: `EvidenceMapModel.model_validate({...}).model_dump(mode="json")` statt rohem Dict |

### `backend/tests/test_report_agent_contracts.py` (neu)

3 Tests:
1. `test_init_evidence_map_sets_schema_version_2` — `_init_evidence_map` liefert schema_version=2, EvidenceMapModel-konformes Dict
2. `test_save_evidence_section_invalid_section_raises_before_persist` — invalides `section_title` (Länge < 3) wirft `ValidationError` **vor** `ReportManager.save_evidence_map` (Mock bestätigt: nicht aufgerufen)
3. `test_save_evidence_section_round_trip` — saubere Section speichern, persistiertes Dict erneut validieren → keine Exception, schema_version=2

## Warum (Layer-0 Boundary-Validation)

Bisher wurden alle drei Schreib-Stellen im Report-Generator als rohe Dicts an `ReportManager.save_evidence_map` übergeben. Das `EvidenceMapModel`-Pydantic-Modell existierte bereits (Sub-Slice 02a/02b), wurde aber nur am Lese-/Export-Boundary verwendet (`api/report.py:437`). Damit konnten intern falsch geformte Maps persistiert werden, ohne dass der Fehler bis zum Export-Zeitpunkt sichtbar wurde.

Sub-Slice 02c schließt diese Lücke: jede Schreib-Operation läuft nun durch das Modell.

### Nebenbefund: `schema_version` auf Section-Ebene

`migrate_v1_to_v2` schreibt `schema_version` in Section-Dicts (dokumentiert als Migration-Verhalten). `ReportSectionModel` erlaubt dieses Feld nicht (`extra="forbid"`). Die Bereinigung erfolgt in `_save_evidence_section` beim Aufbau der `existing_sections`-Liste via Dict-Comprehension. **`evidence_migrations.py` wurde nicht geändert** (verboten laut Scope).

## Tests

- `uv run pytest tests/test_report_agent_contracts.py -v` → **3 passed**
- `uv run pytest tests/contracts/ -v` → **20 passed**
- `uv run pytest -q --ignore=tests/test_ontology_generator.py --deselect=tests/test_report_manager.py::test_report_claim_model_keeps_legacy_fields_and_numeric_score` → **904 passed, 9 skipped**
- Beide deselektierten Tests sind Pre-existing-Failures (kein LLM_API_KEY bzw. Confidence-Formel-Drift, nicht durch diese Änderung verursacht, bestätigt via `git stash`-Verifikation)

## Schema-Drift

`uv run python -m app.contracts.dump_schemas` → keine Änderungen in `schemas/` (Vertrags-Shape unverändert, wir konsumieren `EvidenceMapModel`, definieren es nicht)

## Lint

`uv run ruff check app/services/report_agent.py` → sauber

## Verbleibende Lücken (bewusst, Slice bleibt klein)

- Interner Code arbeitet weiterhin auf `Dict[str, Any]`, nicht auf `EvidenceMapModel`-Instanzen. `self.evidence_map` bleibt ein Dict. Die Boundary-Validation passiert nur beim Schreiben.
- `migrate_v1_to_v2` schreibt `schema_version` in Section-Dicts — das ist ein bekanntes Design-Problem. Eine saubere Lösung würde die Migration auf ein Dict-Cleanup beschränken; das ist separater Scope.
- Alle anderen Stellen, die `self.evidence_map` lesen (z. B. `_build_claims_for_section`), sind nicht abgesichert — das ist bewusst, da sie nur lesen, nicht persistieren.
