# Sub-Slice 07 — Anti-Dekorations-Hardening: `global_items[:2]` entfernt

Datum: 2026-05-02
Layer: 1
Refs: #105

## Was geändert

### `backend/app/services/confidence_calculator.py` (Z. 97–98, neu)

Empty-Guard ganz oben in `compute_confidence`:

```python
if not evidence:
    return 0.15, "low"
```

Vorher lieferte `compute_confidence([])` den Wert `0.0` über die Formelkomponenten
(alle Komponenten fallen bei leerem Input auf 0). Neu: expliziter Minimal-Score `0.15`
mit Label `"low"` — damit ist die Rückgabe für Downstream-Code konsistent und
testbar ohne auf die interne Formelkaskade zu vertrauen.

### `backend/app/services/report_agent.py` (Z. 526–561)

**Edit 1 — dekorativen Fallback entfernt:**

```python
# ALT:
if embedder_ok:
    if not bound:
        bound = deepcopy(global_items[:2])   # dekorativ
    evidence_items = bound
    ...
else:
    evidence_items = direct_items + global_items  # überdeckte orphan-Claims

# NEU:
if embedder_ok:
    evidence_items = bound
    ...
else:
    evidence_items = direct_items
```

**Edit 2 — Anti-Dekorations-Guard nach `compute_confidence`-Call:**

```python
if not evidence_items:
    confidence_score, confidence_label = 0.15, "low"
    audit_trail.append({
        "type": "model_generated_inference",
        "source": "validator",
        "tool_name": "evidence_validator",
        "snippet": "no_direct_evidence_bound",
        "raw": {"reason": "no_direct_evidence_bound"},
    })
```

Orphan-Claims (kein Embedder-Match, kein direktes Section-Evidence) erhalten
damit ehrliche `low`-Confidence und einen rückverfolgbaren Audit-Eintrag statt
stiller Dekorationsdaten aus dem globalen Pool.

## Warum

Eingangs-Audit (2026-04-22) hatte ein 70 %-Konzentrationsproblem identifiziert:
leere Bindings wurden mit zwei globalen Metriken aufgefüllt, die als „Evidence"
für jeden Claim erschienen. Das verursachte:

- falsch-hohe Confidence-Scores für ungebundene Claims
- `graph_metric`-Items aus dem globalen Pool tauchten in allen Claims auf
- Downstream-Reader sahen konsistent „Evidence", obwohl keine claim-spezifische
  Evidenz vorlag

Layer-1-Hardening laut Architektur-Layer-Tabelle.

## Tests

Neue Datei: `backend/tests/services/test_anti_dekoration.py` — 3 Tests:

| Test | Was wird geprüft |
|---|---|
| `test_compute_confidence_empty_returns_low` | `compute_confidence([])` → `(0.15, "low")` |
| `test_orphan_claim_gets_low_confidence` | Embedder läuft, `bound==[]`, `direct_items==[]` → `confidence_label=="low"`, Score < 0.3, `audit_trail` enthält `"no_direct_evidence_bound"` |
| `test_no_global_items_decoration` | `global_items` nicht-leer, `bound==[]`, `direct_items==[]` → `evidence_items` enthält keinen `global_items`-Content |

Angepasste bestehende Tests:

- `tests/test_confidence_calculator.py::test_no_evidence_yields_low` — Score von `0.0` auf `0.15` aktualisiert
- `tests/test_report_manager.py::test_report_claim_model_keeps_legacy_fields_and_numeric_score` — Score von `0.65` auf `0.64`, `evidence_types` von `{"graph_fact", "graph_metric"}` auf `{"graph_fact"}` (kein globaler Leak mehr)

Gesamtergebnis: **919 passed, 2 skipped** (Redis nicht verfügbar, expected).

## Verbleibende Lücken

- `compute_confidence`-Formel-Reform (Kalibrierung, Komponenten-Gewichte) ist Issue #75 — separat, wird hier nicht angefasst.
- Contradiction-Detector ist noch ein Stub (`contradiction_penalty=0.0` fest) — Issue offen.
- Der `else`-Pfad (kein Embedder) gibt jetzt nur `direct_items` zurück. Falls `direct_items` ebenfalls leer ist, greift der Anti-Dekorations-Guard und der Claim erhält `low` + Audit-Entry. Das ist das gewünschte Verhalten.
