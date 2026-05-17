# Sub-Slice 08 · Confidence-Kalibrierung + Contradiction-Penalty

**Datum:** 2026-05-02
**Branch:** feat/layer-1-task-08-confidence-kalibrierung
**Issue:** Closes #165, Refs #105, Refs #75
**Aufwand:** M (laut PLAN.md)

## Änderungen

### confidence_calculator.py
- **Match-Score-Cap**: alle match_scores < 0.55 → score gedeckelt auf 0.69 (medium)
- **Verified-Quellen-Check**: verified nur bei `match_score >= 0.85` UND min. 2 unabhängigen Quellen (`(type, source)`-Tupel)
- Beide Gates arbeiten nach der bestehenden Formel, keine Änderung der Gewichtung

### evidence_binder.py
- Neue Funktion `detect_contradiction_penalty(evidence)` — deterministisch, kein Embedder
- Wertet ausschliesslich strukturierte Felder aus:
  - Boolean-Flags: `contradicts_claim`, `is_contradiction`, `contradiction`
  - Stance-Konflikte: support/oppose, pro/contra, positive/negative
- Nur `supports_claim=True`-Items werden geprueft
- Gedeckelt auf 0.5

### Neue Tests
- `test_confidence_kalibrierung.py`: 16 Tests (4 Confidence + 12 Contradiction)
- Deckt ab: Medium-Cap, Verified-Quellen-Gate, Boolean-Flags, Stance-Konflikte, Integration

## Verifikation
- 960 passed, 2 skipped (Redis), 3 warnings
- Ruff-Check: clean
- Schemas: idempotent (kein Drift)
