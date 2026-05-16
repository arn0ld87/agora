# Arbeitsprotokoll: Sub-Slice S1 — Evidence-Coverage-Floor

**Datum:** 2026-05-17
**Branch:** slice-1-evidence-floor
**Reviewer-Feedback:** report_4fe2dacd80ba
**Issue:** #493

## Was geändert

- `backend/app/contracts/report_v3.py`: Konstante `CLAIM_MIN_EVIDENCE_FOR_CLAIM = 2` ergänzt (Reviewer-Floor-Anker).
- `backend/app/services/report_agent/manager.py`: Floor in `build_report_v3` — Claims mit <2 Evidence-Refs werden zur `Hypothesis` geroutet (kein DataGap).
- `backend/app/services/report_agent/agent.py`: Floor in `_finalize_section_claims` — Claims mit <2 Evidence-Items werden zur Hypothesis geroutet, bevor Low-Confidence-Branch greift.
- `backend/app/services/confidence_calculator.py`: Cap bei <2 Evidence-Items auf 0.59 (kein "high" möglich).
- `frontend/src/contracts/reportContract.ts`: Konstante `CLAIM_MIN_EVIDENCE_FOR_CLAIM = 2` als rein dokumentarischer Spiegel; Schema bleibt permissive (`min 1`) für Bestandsreports.
- `backend/tests/contracts/test_report_v3_contract.py`: `test_persisted_v3_validates` aktualisiert — 1-Evidence-Claim darf nicht mehr als Claim persistieren.
- `backend/tests/services/test_report_modes_workflow.py`: `_make_evidence_map` auf 2 Evidence-Items für `claim_high_ev` angehoben; `test_explorative_mode_keeps_all_with_evidence` an neue Invariante angepasst; 2 neue Tests `TestEvidenceFloorS1` ergänzt.

## Warum

Reviewer-Feedback report_4fe2dacd80ba: Claims mit nur 1 Evidence-Item waren methodisch zu schwach — "Claim" impliziert harte Beleglage. ADR-0002-konform: Verschärfung, keine Schwächung. Die fünf Hartanker (evidence_gating-Block, Hedge-Snapshot, EvidenceSourceKind, cross_stakeholder_for_high, reject_inferred_in_high_confidence) wurden nicht berührt.

## Akzeptanz-Output

- `pytest tests/contracts/test_report_v3_contract.py tests/services/test_report_modes_workflow.py`: **43 passed, 0 failed**
- `ruff check app/ tests/`: **All checks passed**
- `python -m app.contracts.dump_schemas`: alle OK
- `git diff --exit-code schemas/`: **kein Drift** (Konstante ist kein Pydantic-Feld)
- Frontend typecheck: additiver `const`-Export, kein Typ-Impact

## Regression-Fix

- Floor-Branch in `_finalize_section_claims` trennt jetzt `evidence_count == 0` (fällt durch zum Bestands-Low-Confidence-Branch, der Hypothesis **und** `data_gap` mit `gap_reason="no_evidence_bound"` erzeugt) vs. `0 < evidence_count < CLAIM_MIN_EVIDENCE_FOR_CLAIM` (Floor-Hypothesis ohne data_gap, da Evidence vorhanden; Rationale-Wording auf Standard-Format geschärft).
- `test_contradiction_penalty_lowers_score` und `test_report_claim_model_keeps_legacy_fields_and_numeric_score`: Setup auf 2 Evidence-Items hochgezogen, damit der Reviewer-Floor-Cap (`min(score, 0.59)` bei `len < 2`) nicht greift und die Tests die jeweiligen Eigenschaften (Penalty-Messbarkeit, Score-Formel) deterministisch prüfen können.

## Bekannte Limitierungen

- Der Floor in `agent.py` (`_finalize_section_claims`) wirkt auf die gespeicherte Evidence-Map. Der Floor in `manager.py` (`build_report_v3`) wirkt beim Lesen/Bauen der ReportV3. Beide Pfade sind nötig, da Tests den Manager-Pfad direkt testen.
- `confidence_calculator.py`-Cap (0.59) wirkt nur auf den Score des aktuellen Runs; bereits gespeicherte Evidence-Maps mit alten Scores werden beim Re-Build durch den Manager-Floor abgefangen.
- Frontend-`node_modules` im Worktree fehlen (kein Lockfile); Typecheck wurde über diff-Verifikation (rein additiver `const`-Export) abgesichert.
