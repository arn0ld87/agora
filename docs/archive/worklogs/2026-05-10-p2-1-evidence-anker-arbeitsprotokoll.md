# Sub-Slice P2.1 — Evidence-Anker als Pflichtfeld: Arbeitsprotokoll

**Datum:** 2026-05-10
**Branch:** p2-1-evidence-anker
**Refs:** PLAN.md §3.1, ADR-0002

## Ziel

Jeder Claim mit `confidence_label` in {medium, high, verified} muss mindestens einen Evidence-Anker tragen. Claims ohne Anker werden:
- bei `confidence_score < 0.4` (low) → `hypotheses[]` + `data_gaps[]`
- bei medium/high/verified → nur `data_gaps[]` (nicht in `claims[]`)

Bestehende `evidence-map.json`-Dateien beim Reload nicht durch Validator abbrechen lassen.

## Analyse (vor Änderungen)

### Bereits vorhanden
- `ReportClaimModel.non_low_claims_need_evidence` (`report_contract.py:147`): wirft `ValidationError` wenn `evidence=[]` und Label != low.
- `_finalize_section_claims` (`agent.py:510`): routet `score < 0.4 AND evidence=[]` korrekt in hypotheses + data_gaps.
- Tests: `test_medium_claim_without_evidence_is_rejected`, `test_low_claim_without_evidence_remains_legacy_readable` in `test_report_contract.py`.
- `test_orphan_claim_routing.py`: prüft nur low-Orphans (score < 0.4).

### Lücken
1. `_finalize_section_claims` hatte keinen expliziten Pfad für medium/high/verified ohne Evidence — diese landeten in `finalized_claims`, wo der Pydantic-Validator dann abbrechen würde.
2. `evidence_migrations.py::migrate_v1_to_v2` migriert nur `schema_version`, keine Claim-Routing-Migration.
3. Kein Eval-Test für medium/high-Orphan-Routing.

## Änderungen

### 1. `backend/app/services/report_agent/agent.py`

`_finalize_section_claims` (Z. 518-545 → 518-560): zweiter Guard-Ast ergänzt:

```python
if not evidence and label in ("medium", "high", "verified"):
    # P2.1: medium/high/verified ohne Evidence → data_gap only
    index = len(data_gaps) + 1
    ...
    data_gaps.append({...})
    continue
```

Low-Claims (score >= 0.4 aber label=low) gehen weiterhin in `finalized_claims` — der Validator erlaubt das.

### 2. `backend/app/services/evidence_migrations.py`

`migrate_legacy_claims_to_anchored(raw)` hinzugefügt. Logik:
- iteriert über `sections[].claims[]`
- Claims mit `confidence_label in {medium, high, verified}` und leerem `evidence[]` → entfernen aus `claims[]`, in `data_gaps[]` mit `gap_reason="no_evidence_bound"`
- Low-Confidence-Claims ohne Evidence → unverändert (Validator erlaubt das)
- Initialisiert `hypotheses` und `data_gaps` auf Section-Ebene, falls fehlend

### 3. `backend/tests/eval/fixtures/bad/orphan_medium_high_claims.json`

Neues Fixture mit 3 Claims: medium (score 0.55), high (score 0.72), low (score 0.18) — alle ohne Evidence.

### 4. `backend/tests/eval/test_evidence_routing.py`

10 neue Tests:
- `test_medium_high_orphans_route_to_data_gaps`: Routing-Verhalten prüfen
- `test_medium_high_orphan_section_validates`: Pydantic-Validierung nach Routing
- `test_claim_model_rejects_evidence_empty_for_non_low[medium/high]`: Validator direkt
- `test_claim_model_allows_empty_evidence_for_low`: Legacy-Kompatibilität
- `test_migrate_legacy_*`: 5 Tests für `migrate_legacy_claims_to_anchored`

## Tests

```
cd backend && uv run pytest tests/contracts/test_report_contract.py tests/eval/ -x -v
```

Ergebnis: 21 + 10 = 31 Tests grün.

Voller Backend-Test: **1778 passed, 9 skipped, 0 failures** (3m01s).

## Akzeptanz-Output

```
# 1. Validator-Auslösung
$ cd backend && uv run python -c "from app.contracts import ReportClaimModel; m = ReportClaimModel(claim_text='x', confidence_label='high', confidence_score=0.8, evidence=[]); print('FAIL: Validator hat nicht ausgelöst')" 2>&1 | grep -E "ValidationError|Evidence-Anker" || echo "FAIL"
pydantic_core._pydantic_core.ValidationError: 2 validation errors for ReportClaimModel

# 2. Schema-Drift
$ cd .. && git diff --stat schemas/
(kein Output — keine Schema-Änderung; Validator war bereits implementiert)

# 3. Contract-Tests
$ cd backend && uv run pytest tests/contracts/test_report_contract.py -x -v
21 passed

# 4. Voller Backend-Test
$ cd backend && uv run pytest -x -q
1778 passed, 9 skipped, 7 deselected

# 5. Eval-Tests
$ cd backend && uv run pytest tests/eval/ -x -v
(enthält test_evidence_routing.py mit 10 neuen Tests) — alle grün
```

## Statische Analyse

```
ruff check --fix app/ tests/ → All checks passed!
mypy app → Success: no issues found in 135 source files
```

## Geänderte Dateien

| Datei | +LOC | -LOC | Art |
|---|---|---|---|
| `backend/app/services/report_agent/agent.py` | +16 | 0 | feature |
| `backend/app/services/evidence_migrations.py` | +62 | 0 | feature |
| `backend/tests/eval/fixtures/bad/orphan_medium_high_claims.json` | +32 | 0 | fixture |
| `backend/tests/eval/test_evidence_routing.py` | +145 | 0 | tests |
| `CHANGELOG.md` | +2 | +1 | docs |
| `docs/2026-05-10-p2-1-evidence-anker-arbeitsprotokoll.md` | neu | - | docs |
