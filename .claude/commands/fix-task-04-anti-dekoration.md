---
description: Layer 1 - dekorative Evidence-Fallbacks entfernen, Confidence ehrlich machen (Implementierung via Sonnet)
allowed-tools: Read, Bash, Grep, Agent
---

# /fix-task-04 — Anti-Dekorations-Fix (Sonnet-Dispatch)

## Vorab-Verifikation

```bash
cd /Volumes/T7/Projekte/agora
rg -n "deepcopy\\(global_items\\[:2\\]\\)" backend/app/services/report_agent.py
# Erwartet: Z. 524 (verifiziert)
```

Falls 0 Treffer: Stop — Task 04 ist durch.

## Worktree

```bash
WT=/Volumes/T7/Projekte/agora-worktrees/feat-layer-1-task-04-anti-deko
git -C /Volumes/T7/Projekte/agora fetch origin --quiet
git -C /Volumes/T7/Projekte/agora worktree add -b feat/layer-1-task-04-anti-deko "$WT" origin/main
```

## Sonnet-Dispatch (Agent-Tool)

`subagent_type: "agora-refactor-worker"`, `description: "fix-task-04 anti-dekoration"`, `prompt`:

```

Arbeite ausschließlich im Worktree <WT>. Sub-Slice: Layer 1 / Task 04 — Anti-Dekorations-Fix.

## Kontext

Z. 524 in backend/app/services/report_agent.py: bei leerem `bound` werden 2 globale Metriken (z. B. echo_chamber_index: 0.42) als „Beleg" für jeden Claim eingespeist. Erklärt das 70%-Konzentrations-Problem aus dem Eingangs-Audit.

## Edits

### 4.1 backend/app/services/report_agent.py ab Z. 522

Diff-Form:

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

### 4.2 backend/app/services/confidence_calculator.py — compute_confidence()

- Wenn len(evidence_items) == 0 → return (0.15, "low").
- Wenn max(match_score) < 0.55 → cap auf "medium".
- "verified" nur bei top match >= 0.85 UND mindestens 2 unabhängigen Quellen.
- Pydantic-Validatoren (ReportClaimModel) bleiben — hier nur die Funktion ehrlich machen.

### 4.3 Test-Fixture (NEU)

backend/tests/services/test_evidence_dedup.py:

def test_orphan_claim_gets_low_confidence():
    """Wenn keine direkte Evidence vorliegt, darf Claim nicht 'high' sein."""
    # Setup ohne Embedder, kein direct_items
    # Erwartung: confidence_label == "low", score < 0.3
    ...

## Akzeptanz

- rg -n "deepcopy\\(global_items\\[:2\\]\\)" backend/app/services/report_agent.py → leer
- cd backend && uv run pytest tests/services/test_evidence_dedup.py -v → grün
- cd backend && uv run pytest -x -q → grün
- (Smoke) cd backend && uv run python scripts/check_evidence_quality.py --fixtures tests/eval/fixtures --orphan-claim-rate 0.10 → exit 0

## Doku

- docs/archive/worklogs/<YYYY-MM-DD>-task-04-anti-deko-arbeitsprotokoll.md (kurz: Drift-Stellen, neue Tests, Smoke-Werte)
- CHANGELOG.md [Unreleased]: "Layer 1: Anti-Dekorations-Fix + Confidence-Hardening (Sub-Slice 04)"

## NICHT

- Keinen Refactor der compute_confidence-Formel jetzt — separater Issue (#75 / EPIC-15-ST-02).
- Keine Schema-Migration v1→v2 — Issue #107.
- NICHT committen.
```

## Verify

```bash
rg -n "deepcopy\\(global_items\\[:2\\]\\)" "$WT/backend/app/services/report_agent.py" || echo "clean"
cd "$WT/backend" && uv run pytest tests/services/test_evidence_dedup.py -v
cd "$WT/backend" && uv run pytest -x -q
cd "$WT/backend" && uv run python scripts/check_evidence_quality.py --fixtures tests/eval/fixtures --orphan-claim-rate 0.10
```

Commit via `/agora-next-task` oder manuell.
