---
description: Layer 1 - dekorative Evidence-Fallbacks entfernen, Confidence ehrlich machen
allowed-tools: Read, Edit, Grep, Bash
---

# /fix-task-04 — Anti-Dekorations-Fix

## Vorab (im Code verifiziert)

```bash
rg -n "deepcopy\(global_items\[:2\]\)" backend/app/services/report_agent.py
# → Z. 524: bound = deepcopy(global_items[:2])  # dekorative Evidence!
```

Das ist die kritische Stelle: bei leerem `bound` werden 2 globale Metriken (z. B.
`echo_chamber_index: 0.42`) als „Beleg" für jeden Claim eingespeist. Erklärt
exakt das 70%-Konzentrations-Problem aus dem Eingangs-Audit.

## Implementierung

`backend/app/services/report_agent.py` ab Z. 522:

```diff
 if embedder_ok:
-    if not bound:
-        bound = deepcopy(global_items[:2])
-    evidence_items = bound
+    evidence_items = bound
     direct_count = len(bound)
 else:
-    evidence_items = direct_items + global_items
+    evidence_items = direct_items
     direct_count = len(direct_items)

 confidence_score, confidence_label = compute_confidence(evidence_items)
+# Anti-Dekorations-Regel: kein "verified" / "high" ohne echte Evidence
+if not evidence_items:
+    confidence_score = 0.15
+    confidence_label = "low"
+    audit_trail.append({
+        "type": "model_generated_inference",
+        "source": "validator",
+        "tool_name": "evidence_validator",
+        "snippet": "no_direct_evidence_bound",
+        "raw": {"reason": "no_direct_evidence_bound"},
+    })
```

## Confidence-Hardening

`backend/app/services/confidence_calculator.py` — `compute_confidence()`:

- Wenn `len(evidence_items) == 0` → return `(0.15, "low")`.
- Wenn `max(match_score) < 0.55` → cap auf `medium`.
- `verified` nur bei top match >= 0.85 **und** mindestens 2 unabhängigen Quellen.

Die Regeln sind im Pydantic-Contract bereits enforced (`ReportClaimModel`-Validatoren).
Hier geht es nur darum, dass `compute_confidence` nicht überhebt.

## Test-Fixture

`backend/tests/services/test_evidence_dedup.py` (NEU):

```python
def test_orphan_claim_gets_low_confidence():
    """Wenn keine direkte Evidence vorliegt, darf Claim nicht 'high' sein."""
    # ... Setup ohne Embedder, kein direct_items
    # Erwartung: confidence_label == "low", score < 0.3
```

## Verifikation

```bash
cd backend && uv run pytest tests/ -x -q
# Smoke: ein echter Run gegen Sample-Doc
cd backend && uv run python scripts/check_evidence_quality.py \
    --fixtures tests/eval/fixtures \
    --orphan-claim-rate 0.10
```

## NICHT machen

- Keine `compute_confidence`-Formel-Refactor jetzt — separater Issue (#75 / EPIC-15-ST-02).
- Keine Schema-Migration v1→v2 (Issue #107 separat).
