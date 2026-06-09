# Sub-Slice 32 — Contradiction-Penalty Verdrahtung (Closes #105, Layer 1)

**Datum:** 2026-05-03
**Branch:** `feat/layer-1-task-08-contradiction-wiring`

## Problem

In `backend/app/services/report_agent.py` Zeile 637 wurde `compute_confidence(evidence_items)`
ohne `contradiction_penalty`-Argument aufgerufen. Der Hook in `compute_confidence` existierte
bereits (Default `0.0`), aber `detect_contradiction_penalty` aus `evidence_binder.py` speiste
ihn nie. Claims mit widersprüchlicher Evidence konnten damit `verified` werden, solange
`match_score` und Source-Quality stimmten.

## Änderungen

### `backend/app/services/report_agent.py`

- **Zeile 23 (Import):** `bind_evidence_to_claim` um `detect_contradiction_penalty` ergänzt.
- **Zeile 637 (Patch):** `compute_confidence(evidence_items)` ersetzt durch:

  ```python
  penalty = detect_contradiction_penalty(evidence_items)
  confidence_score, confidence_label = compute_confidence(
      evidence_items,
      contradiction_penalty=penalty,
  )
  if penalty > 0.0:
      audit_trail.append({
          "type": "contradiction_penalty_applied",
          "value": penalty,
          "source": "evidence_binder.detect_contradiction_penalty",
      })
  ```

### `backend/tests/test_report_agent_contradiction_wiring.py` (neu)

4 neue Tests:

- **Test A** (`test_no_contradiction_no_penalty_no_audit_entry`): Evidence ohne Flags → Penalty=0.0, kein Audit-Eintrag.
- **Test B** (`test_contradicts_claim_flag_triggers_penalty_and_audit_entry`): `contradicts_claim=True` → Penalty>0, Audit-Trail-Eintrag vorhanden, Score niedriger.
- **Test C** (`test_stance_conflict_flips_confidence_label`): Pro/Contra-Stance-Mix → Penalty schlägt zu, Label schlechter als ohne Penalty.
- **Test D** (`test_report_agent_calls_detect_contradiction_penalty_with_evidence_items`): Integration via `patch` — `detect_contradiction_penalty` wird in `_build_claims_for_section` aufgerufen (mindestens 1 Call), Output enthält `confidence_score` und `confidence_label`.

## Verifikation

```
uv run pytest tests/test_report_agent_contradiction_wiring.py -x -v  → 4/4 passed
uv run pytest tests/test_evidence_binder.py -x -v                    → 5/5 passed (keine Regression)
uv run pytest -x -q                                                   → 1286 passed, 9 skipped
uv run ruff check app/services/report_agent.py tests/test_report_agent_contradiction_wiring.py → All checks passed!
uv run python -m app.contracts.dump_schemas + git diff schemas/        → NO_SCHEMA_DRIFT
```

## Schema-Drift

Keine. Es wurden keine Pydantic-Modelle in `app/contracts/` berührt.

## Out of Scope

- Funktions-Signatur von `compute_confidence` unverändert (Default `contradiction_penalty=0.0` bleibt).
- Kein Logging-Spam: kein `logger.info` pro Claim — Audit-Trail-Eintrag reicht.
- Frontend: separater Worker.
