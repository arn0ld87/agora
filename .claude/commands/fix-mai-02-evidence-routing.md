---
description: MAI-02 — Claims ohne Evidence landen aktiv in hypotheses[] (balanced) bzw. werden gedroppt (strict). Layer-1-Touch.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-02-evidence-routing — R4 Evidence-Routing aktivieren

## Ziel

Claims ohne Evidence werden nicht mehr stumm aus Section-Prosa generiert. Sie landen aktiv in `hypotheses[]` (mode=balanced) oder werden gedroppt (mode=strict). `ReportClaimModel.evidence == []` mit `confidence_label != "low"` ist ein ValidationError.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-02/`.
- Branch: `feat/mai-02-evidence-routing`.
- MAI-01 muss durch sein (Reihenfolge Block A → Block B).
- **Opus-Pre-Review-Pflicht** (Layer-1-Touch + Spec-ambig). Vor Subagent-Dispatch:
  `mcp__code-review-graph__get_impact_radius_tool` auf `ReportClaimModel`, `_finalize_section_claims`, `generate_section_metadata` ausführen, dann `sequential-thinking` mit mind. 3 Thoughts.

## Schritt-für-Schritt

### Schritt 1: Impact-Radius

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-02
rg -n "ReportClaimModel" backend/app/
rg -n "evidence.*default_factory=list" backend/app/contracts/report_contract.py
rg -n "_finalize_section_claims\|finalize_section" backend/app/services/report_agent/
```

### Schritt 2: Contract-Validator hinzufügen

`backend/app/contracts/report_contract.py` — `ReportClaimModel`:

```python
from pydantic import model_validator

class ReportClaimModel(BaseModel):
    # ... bestehende Felder ...
    evidence: list[EvidenceItemModel] = Field(default_factory=list, max_length=10)
    confidence_label: Literal["low", "medium", "high", "verified"] = "low"

    @model_validator(mode="after")
    def _require_evidence_for_non_low(self) -> "ReportClaimModel":
        """Claims mit confidence_label != 'low' brauchen mindestens 1 Evidence-Item."""
        if self.confidence_label not in {"low"} and not self.evidence:
            raise ValueError(
                f"Claim '{self.claim_id}' hat confidence_label={self.confidence_label!r} "
                f"aber keine Evidence — verstößt gegen Evidence-Gating (ADR-0002)."
            )
        return self
```

### Schritt 3: Routing-Hook in agent.py

`backend/app/services/report_agent/agent.py` — neue Methode:

```python
def _finalize_section_claims(
    self,
    section_meta: dict[str, Any],
    section_index: int,
    *,
    report_mode: ReportMode = DEFAULT_REPORT_MODE,
) -> dict[str, Any]:
    """Routet Claims ohne Evidence vor der Persistenz.

    - mode=balanced: Claim ohne Evidence + score<0.4 → wird zu ReportSectionHypothesisModel.
    - mode=strict: Claim ohne Evidence → wird komplett gedroppt.
    - mode=explorative: kein Routing, alles bleibt.

    Returns:
        Modifiziertes section_meta-dict mit aktualisierten claims[] und hypotheses[].
    """
    if report_mode == "explorative":
        return section_meta

    raw_claims = section_meta.get("claims") or []
    raw_hypotheses = section_meta.get("hypotheses") or []
    kept_claims: list[dict[str, Any]] = []
    new_hypotheses: list[dict[str, Any]] = list(raw_hypotheses)

    for claim in raw_claims:
        if not isinstance(claim, dict):
            continue
        evidence = claim.get("evidence") or []
        score = float(claim.get("confidence_score") or 0.0)

        if evidence:
            kept_claims.append(claim)
            continue

        # Keine Evidence — Mode-spezifisch routen.
        if report_mode == "strict":
            self.report_logger.log_claim_dropped(
                section_index=section_index,
                claim_id=claim.get("claim_id"),
                reason="strict_mode_no_evidence",
            )
            continue

        # balanced: zu Hypothese umwandeln, wenn Score niedrig.
        if score < 0.4:
            new_hypotheses.append({
                "hypothesis_id": f"hyp_{section_index:02d}_{len(new_hypotheses) + 1:02d}",
                "hypothesis_text": claim.get("claim_text", ""),
                "rationale": claim.get("rationale") or "Claim ohne Evidence-Anker — als Hypothese markiert.",
                "suggested_evidence": claim.get("suggested_evidence") or [],
                "origin_section_index": section_index,
            })
        else:
            # balanced + Score≥0.4 ohne Evidence ist ein Pipeline-Bug — log + drop.
            self.report_logger.log_claim_dropped(
                section_index=section_index,
                claim_id=claim.get("claim_id"),
                reason="balanced_no_evidence_high_score_pipeline_bug",
            )

    section_meta["claims"] = kept_claims
    section_meta["hypotheses"] = new_hypotheses
    return section_meta
```

### Schritt 4: Workflow-Verdrahtung

`backend/app/services/report_agent/workflow.py` — nach `generate_section_metadata()`-Aufruf in `generate_report()`:

```python
section_meta = generate_section_metadata(agent, section_title=section.title, ...)
section_meta = agent._finalize_section_claims(
    section_meta,
    section_index=section_num,
    report_mode=report_mode,
)
if section_meta and agent.report_logger:
    agent.report_logger.log_section_metadata(...)
```

### Schritt 5: Tests

`backend/tests/services/test_evidence_routing.py` (neu):

```python
"""MAI-02: Tests für _finalize_section_claims (R4 Evidence-Routing)."""

import pytest
from unittest.mock import MagicMock

from app.services.report_agent.agent import ReportAgent


@pytest.fixture
def agent_stub():
    agent = MagicMock(spec=ReportAgent)
    agent._finalize_section_claims = ReportAgent._finalize_section_claims.__get__(agent)
    agent.report_logger = MagicMock()
    return agent


def test_low_confidence_no_evidence_becomes_hypothesis_balanced(agent_stub):
    section_meta = {
        "claims": [
            {"claim_id": "c1", "claim_text": "Test-Claim", "evidence": [], "confidence_score": 0.2}
        ],
        "hypotheses": [],
    }
    result = agent_stub._finalize_section_claims(section_meta, section_index=1, report_mode="balanced")
    assert len(result["claims"]) == 0
    assert len(result["hypotheses"]) == 1
    assert result["hypotheses"][0]["hypothesis_text"] == "Test-Claim"


def test_low_confidence_no_evidence_dropped_strict(agent_stub):
    section_meta = {
        "claims": [
            {"claim_id": "c1", "claim_text": "Test-Claim", "evidence": [], "confidence_score": 0.2}
        ],
        "hypotheses": [],
    }
    result = agent_stub._finalize_section_claims(section_meta, section_index=1, report_mode="strict")
    assert len(result["claims"]) == 0
    assert len(result["hypotheses"]) == 0


def test_explorative_keeps_all(agent_stub):
    section_meta = {
        "claims": [
            {"claim_id": "c1", "claim_text": "Test", "evidence": [], "confidence_score": 0.2}
        ],
        "hypotheses": [],
    }
    result = agent_stub._finalize_section_claims(section_meta, section_index=1, report_mode="explorative")
    assert len(result["claims"]) == 1


def test_high_confidence_no_evidence_raises_validation_error():
    from pydantic import ValidationError
    from app.contracts.report_contract import ReportClaimModel

    with pytest.raises(ValidationError) as exc_info:
        ReportClaimModel(
            claim_id="c1",
            claim_text="Behauptung ohne Beleg",
            confidence_label="high",
            evidence=[],
        )
    assert "Evidence-Gating" in str(exc_info.value)
```

### Schritt 6: Snapshot-Update

```bash
# Bestehende Section-Snapshots werden kürzer (R4-Drop ist sichtbar).
cd backend && uv run pytest tests/eval/ --snapshot-update
# Diff manuell prüfen, dann committen.
git diff tests/eval/snapshots/
```

## Verifikation

```bash
# 1) Contract-Tests
cd backend && uv run pytest tests/contracts/ -x -v

# 2) Neuer Routing-Test
cd backend && uv run pytest tests/services/test_evidence_routing.py -x -v

# 3) Voll-Test
cd backend && uv run pytest -x -q

# 4) Lint + Types
cd backend && uv run ruff check . && uv run mypy app

# 5) Schema-Dump idempotent
cd backend && uv run python -m app.contracts.dump_schemas
cd .. && git diff --exit-code schemas/
```

## Warum?

Bewertung §6.2 und §13 Punkt 2: „Claim-Evidence-Binding erzwingen — verhindert hübsches Halluzinieren." Heute wird der Claim trotzdem in Markdown geschrieben, der Calculator gibt nur low-Confidence aus. Mit R4 wandert er sichtbar in den Hypothesen-Slot (Blockaccept für MAI-03).

## Nächste Schritte

1. Worklog `docs/2026-05-14-mai-02-arbeitsprotokoll.md` schreiben — Section-Snapshot-Diff erläutern.
2. CHANGELOG: `MAI-02 · R4 Evidence-Routing aktiviert (balanced→Hypothesen, strict→Drop).`
3. `/fix-mai-03-hypotheses-slot` direkt im Anschluss — MAI-03 hängt an MAI-02.
