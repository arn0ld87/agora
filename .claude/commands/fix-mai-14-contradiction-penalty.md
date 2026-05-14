---
description: MAI-14 — confidence_calculator senkt Score, wenn Evidence-Quellen widersprüchliche Sentiments tragen.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-14-contradiction-penalty — Confidence-Contradiction-Penalty

## Ziel

`confidence_calculator.compute()` zieht 0.2 vom Confidence-Score ab, wenn mehrere Evidence-Items derselben Claim widersprüchliche Sentiment-Polaritäten haben (z. B. `sentiment_score=+0.7` und `-0.6` im selben Claim-Evidence-Set). Damit fällt eine Behauptung auf `low`, sobald Quellen sich widersprechen.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-14/`.
- Branch: `feat/mai-14-contradiction-penalty`.
- **MAI-03 muss durch sein** — sonst landen widersprüchliche Claims nicht in Hypotheses, sondern verschwinden.

## Schritt-für-Schritt

### Schritt 1: Calculator inspizieren

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-14
cat backend/app/services/confidence_calculator.py
rg -n "sentiment_score" backend/app/contracts/
```

### Schritt 2: Heuristik einbauen

`backend/app/services/confidence_calculator.py`:

```python
"""MAI-14: Contradiction-Penalty.

Wenn Evidence-Items derselben Claim auseinandergehende Sentiments tragen,
ist die Behauptung weniger belastbar. Konkret:
- Wenn std(sentiment_scores) > 0.6 → Penalty -0.2.
- Wenn min<-0.3 und max>+0.3 → Penalty -0.2 (gemischter Tenor).
"""

from __future__ import annotations

import statistics
from typing import Iterable

CONTRADICTION_PENALTY = 0.2
CONTRADICTION_STD_THRESHOLD = 0.6
CONTRADICTION_RANGE_LOW = -0.3
CONTRADICTION_RANGE_HIGH = 0.3


def _has_contradiction(sentiment_scores: list[float]) -> bool:
    """Erkennt widersprüchliche Sentiment-Vektoren in einem Evidence-Set."""
    if len(sentiment_scores) < 2:
        return False

    # Std-Dev-Check
    stddev = statistics.pstdev(sentiment_scores)
    if stddev > CONTRADICTION_STD_THRESHOLD:
        return True

    # Range-Check
    low = min(sentiment_scores)
    high = max(sentiment_scores)
    if low < CONTRADICTION_RANGE_LOW and high > CONTRADICTION_RANGE_HIGH:
        return True

    return False


def compute_claim_confidence(
    evidence: Iterable[dict],
    *,
    base_score: float = 0.5,
) -> tuple[float, str, list[str]]:
    """Berechnet Confidence-Score und Label aus einer Evidence-Liste.

    Returns:
        (score, label, applied_penalties)
        score: 0.0-1.0
        label: "low" | "medium" | "high" | "verified"
        applied_penalties: Liste der angewandten Penalty-Namen für Audit.
    """
    evidence_list = list(evidence)
    score = base_score
    penalties: list[str] = []

    # ... bestehende Penalty-Logik (Quellenanzahl, Quellentyp, Aktualität) ...

    # MAI-14: Contradiction-Penalty
    sentiments = [
        float(e.get("sentiment_score"))
        for e in evidence_list
        if isinstance(e, dict)
        and e.get("sentiment_score") is not None
        and isinstance(e.get("sentiment_score"), (int, float))
    ]
    if _has_contradiction(sentiments):
        score -= CONTRADICTION_PENALTY
        penalties.append("contradiction_penalty")

    score = max(0.0, min(1.0, score))

    # Label-Mapping (bestehende Schwellen)
    if score >= 0.85:
        label = "verified"
    elif score >= 0.65:
        label = "high"
    elif score >= 0.40:
        label = "medium"
    else:
        label = "low"

    return score, label, penalties
```

### Schritt 3: ReportClaimModel.evidence Sentiment-Feld

Falls noch nicht vorhanden — `backend/app/contracts/evidence.py`:

```python
class EvidenceItemModel(BaseModel):
    # ... bestehende Felder ...
    sentiment_score: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description="Sentiment des Quellen-Snippets (-1 negativ, 0 neutral, +1 positiv).",
    )
```

### Schritt 4: Tests

`backend/tests/test_confidence_calculator.py` (erweitern):

```python
def test_contradiction_penalty_via_stddev():
    """MAI-14: Std-Dev>0.6 löst Penalty aus."""
    evidence = [
        {"source_id": "s1", "sentiment_score": 0.9},
        {"source_id": "s2", "sentiment_score": -0.8},
        {"source_id": "s3", "sentiment_score": 0.7},
    ]
    score, label, penalties = compute_claim_confidence(evidence, base_score=0.7)
    assert "contradiction_penalty" in penalties
    assert score <= 0.5


def test_contradiction_penalty_via_range():
    """MAI-14: min<-0.3 + max>+0.3 löst Penalty aus."""
    evidence = [
        {"source_id": "s1", "sentiment_score": 0.5},
        {"source_id": "s2", "sentiment_score": -0.5},
    ]
    score, label, penalties = compute_claim_confidence(evidence, base_score=0.6)
    assert "contradiction_penalty" in penalties


def test_no_penalty_when_aligned():
    """Konsistente Sentiments → keine Penalty."""
    evidence = [
        {"source_id": "s1", "sentiment_score": 0.4},
        {"source_id": "s2", "sentiment_score": 0.5},
        {"source_id": "s3", "sentiment_score": 0.6},
    ]
    score, label, penalties = compute_claim_confidence(evidence, base_score=0.7)
    assert "contradiction_penalty" not in penalties


def test_single_evidence_no_contradiction():
    """1 Item kann nicht widersprüchlich sein."""
    evidence = [{"source_id": "s1", "sentiment_score": 0.9}]
    score, label, penalties = compute_claim_confidence(evidence, base_score=0.7)
    assert "contradiction_penalty" not in penalties


def test_missing_sentiment_ignored():
    """Items ohne sentiment_score werden übersprungen, kein Crash."""
    evidence = [
        {"source_id": "s1"},  # kein sentiment_score
        {"source_id": "s2", "sentiment_score": 0.4},
    ]
    score, label, penalties = compute_claim_confidence(evidence, base_score=0.7)
    # Kein Contradiction-Penalty, da nur 1 valider Sentiment
    assert "contradiction_penalty" not in penalties
```

### Schritt 5: Snapshot-Update prüfen

```bash
# Falls bestehende Eval-Snapshots widersprüchliche Evidence enthalten,
# wandert deren Confidence von medium → low. Diff anschauen, dann committen.
cd backend && uv run pytest tests/eval/ --snapshot-update
git diff tests/eval/snapshots/ | head -50
```

## Verifikation

```bash
# 1) Calculator-Tests
cd backend && uv run pytest tests/test_confidence_calculator.py -x -v

# 2) Voll-Test
cd backend && uv run pytest -x -q

# 3) Lint + Types
cd backend && uv run ruff check . && uv run mypy app

# 4) Schema-Drift (Evidence-Model evtl. neu, falls sentiment_score ergänzt)
cd backend && uv run python -m app.contracts.dump_schemas
cd .. && git diff --exit-code schemas/
```

## Warum?

Bewertung §10: „Confidence-Score muss Widerspruch belohnen — sonst hat eine Quelle gleichen Wert wie zwei widersprechende." Mit Penalty erkennt das System „Stimmen geteilt" und der Calculator gibt Low-Confidence-Banner aus statt einer hübschen High-Behauptung.

## Nächste Schritte

1. Worklog mit Snapshot-Diff-Erläuterung.
2. CHANGELOG: `MAI-14 · Confidence-Contradiction-Penalty (Std-Dev>0.6 ODER Range>0.6 ⇒ -0.2).`
3. `/agora-mai-next-task` → Block C (`/fix-mai-08-prompts-split`).
