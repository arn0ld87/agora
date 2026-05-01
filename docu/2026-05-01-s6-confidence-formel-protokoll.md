# S6 — Confidence-Formel + Label-Mapping · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** S6

## Implementierung

Neuer Service `backend/app/services/confidence_calculator.py` mit `compute_confidence(evidence, *, contradiction_penalty=0.0) -> (score, label)`.

Formel:

```
score = 0.40 * relevance
      + 0.25 * source_quality
      + 0.20 * specificity
      + 0.15 * consistency
      - contradiction_penalty
```

Komponenten:

- **relevance** — mean von `match_score`-Feldern; ohne Scores Default 0.5
- **source_quality** — Typ-gewichteter Mittelwert (graph_fact 1.0, graph_metric 0.85, agent_action 0.7, audit_trail-Typen 0.0)
- **specificity** — Top-`match_score` → 1.0/0.8/0.6/0.4 nach Schwellen
- **consistency** — 1.0/0.8/0.6/0.0 nach Anzahl unique `(type, source)`-Paaren

Labels: low (<0.40), medium (<0.70), high (<0.90), **verified (≥0.90, nur wenn Top-`match_score` ≥ 0.85)**. Verified gedeckelt auf 0.89 falls keine starke direkte Evidence.

Im `report_agent` ersetzt der Calculator das alte `min(0.95, 0.25 + support_count * 0.12)`.

## Tests (7 neu)

- `test_no_evidence_yields_low`
- `test_single_unmatched_graph_fact_yields_medium`
- `test_strong_match_score_unlocks_verified`
- `test_high_score_without_strong_match_caps_at_high`
- `test_off_topic_low_match_score_yields_low_or_medium`
- `test_audit_trail_types_get_zero_source_weight`
- `test_contradiction_penalty_lowers_score`

Bestehender Test `test_report_claim_model_keeps_legacy_fields_and_numeric_score` aktualisiert: Score 0.49 → 0.65 (formelbasiert), Label bleibt medium.

517 Backend-Tests grün, 40 Frontend, Build clean.
