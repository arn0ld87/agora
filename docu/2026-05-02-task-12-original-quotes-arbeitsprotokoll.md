# Task 12 — Original-Quotes mit Provenance-Anker (Sub-Slice 12, Layer 3)

**Datum:** 2026-05-02
**Branch:** `feat/layer-3-task-12-original-quotes-provenance`
**Basis:** `origin/main` = `60ccd18`
**Issue:** Closes #169

## Ziel

`EvidenceItemModel` erhält zwei neue optionale Felder (`quote`, `source_id_anchor`),
damit das Frontend bei jedem Evidence-Item ein Original-Zitat anzeigen und per
Scroll-To-Source-Klick zur Ursprungsquelle navigieren kann. Das ist die Voraussetzung
fuer den Diff/Confidence-UI in Task 16.

## Geaenderte Dateien

| Datei | Art | Zeilen |
|---|---|---|
| `backend/app/contracts/report_contract.py` | Modell-Erweiterung | +17 |
| `backend/app/services/report_agent.py` | 2 Helper + 1 Schleife | +55 |
| `backend/tests/contracts/test_report_contract.py` | 5 neue Cases | +53 |
| `backend/tests/services/test_report_agent_provenance.py` | neu, 6 Cases | +39 |
| `frontend/src/contracts/reportContract.ts` | Zod-Spiegel | +2 |
| `frontend/src/contracts/__tests__/reportContract.spec.ts` | 2 neue Cases | +28 |
| `schemas/evidence-map.schema.json` | auto-generiert | +28 |
| `schemas/report-contract.schema.json` | auto-generiert | +28 |
| `CHANGELOG.md` | Added-Bullet | +1 |

## Felder

### `quote: Optional[str]`
- min_length=1, max_length=500
- Wörtlicher Auszug aus der Quelle (kein Summary)
- None = nicht ableitbar (unveraenderte Konstruktion ohne das Feld bleibt valid)

### `source_id_anchor: Optional[str]`
- min_length=1, max_length=200
- Format absichtlich offen fuer verschiedene Quellen-Klassen:
  - `"agent-log-42#entry-p1234"` (agent_log_ref)
  - `"web:https://example.com/x#:~:text=Fragment"` (raw.url + text)
- None = kein Anker ableitbar

## Implementierung

Zwei statische pure Methoden in `ReportAgent`, vor `_build_claims_for_section`:

- `_build_source_id_anchor(item)` — Prioritaet: agent_log_ref > raw.url > None
- `_attach_provenance(item)` — idempotenter Mutator, bestehende Werte werden nicht ueberschrieben

In `_build_claims_for_section` eine Schleife direkt vor `compute_confidence`:

```python
evidence_items = [self._attach_provenance(it) for it in evidence_items]
```

Leere Listen (Anti-Dekorations-Pfad) sind kein Problem — `[]` bleibt `[]`.

## Testergebnis

- `uv run pytest tests/contracts/ tests/services/test_report_agent_provenance.py -x -v`: 38 passed
- `uv run pytest -x -q`: 505 passed, 1 failed (vorbestehend: `test_validate_process_uses_configured_entity_cap`)
- `uv run ruff check app/ tests/`: clean
- `npm run test -- --run src/contracts/`: 9 passed (7 bestehend + 2 neu)

## Schema-Drift

`schemas/evidence-map.schema.json` und `schemas/report-contract.schema.json` je +28 Zeilen
(beide enthalten `EvidenceItemModel` inline). `report.schema.json` unveraendert.
