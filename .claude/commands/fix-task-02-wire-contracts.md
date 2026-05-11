---
description: Verdrahtet Pydantic-Contracts in api/report.py und report_agent.py (Implementierung via Sonnet)
allowed-tools: Read, Bash, Grep, Glob, Agent
---

# /fix-task-02 — Contracts in API verdrahten (Sonnet-Dispatch)

Orchestrator-Pattern wie `/fix-task-01`: Vorab → Worktree → Sonnet-Dispatch → Verify. Implementer ist **Sonnet** via `agora-refactor-worker`.

## Vorab

`/fix-task-01` muss durch sein (Tests grün, Schemas existieren in `schemas/`).

```bash
ls /Volumes/T7/Projekte/agora/schemas/ | head
rg -n "from app.contracts" /Volumes/T7/Projekte/agora/backend/app/ || echo "noch nicht verdrahtet"
```

## Worktree

```bash
WT=/Volumes/T7/Projekte/agora-worktrees/feat-layer-0-task-02-wire
git -C /Volumes/T7/Projekte/agora fetch origin --quiet
git -C /Volumes/T7/Projekte/agora worktree add -b feat/layer-0-task-02-wire "$WT" origin/main
```

## Sonnet-Dispatch (Agent-Tool)

`subagent_type: "agora-refactor-worker"`, `description: "fix-task-02 wire contracts"`, `prompt`:

```

Arbeite ausschließlich im Worktree <WT>. Sub-Slice: Layer 0 / Task 02 — Contracts in API + Generator verdrahten.

## Edits

### 2.1 backend/app/api/report.py — Export auf Contract umstellen

Nach Z. 417 (rohes Dict) ersetzen durch Contract-Aufbau:

from datetime import datetime, timezone
from app.contracts import ReportContractModel, ReportModel, EvidenceMapModel

def export_report_v2(report_id: str):
    report_dict = ReportManager.get_report(report_id).to_dict()
    report = ReportModel.model_validate({**report_dict, "schema_version": 2})

    raw_evidence = ReportManager.get_evidence_map(report_id)
    evidence = (
        EvidenceMapModel.model_validate({**raw_evidence, "schema_version": 2})
        if raw_evidence else None
    )

    contract = ReportContractModel(
        schema_version=2,
        exported_at=datetime.now(timezone.utc),
        report=report,
        evidence=evidence,
    )
    return Response(
        contract.model_dump_json(indent=2),
        mimetype="application/json; charset=utf-8",
    )

### 2.2 backend/app/services/report_agent.py — Pydantic statt rohe Dicts

- Schema-Drift beseitigen (Z. 567 + 1127: "schema_version": 1 → 2).
- Refactor _save_evidence_section und ähnliche Stellen Schritt-für-Schritt zu EvidenceMapModel-Instanzen. Validation an der inneren Boundary.

### 2.3 Backwards-Compat-Reader

In report_agent.py: Funktion migrate_v1_to_v2(raw: dict) -> dict. Konvertiert v1-Reports beim Lesen, schreibt intern v2. Hängt an Issue #107.

## Akzeptanz

- cd backend && uv run pytest -x -q → grün
- cd backend && uv run python -m app.contracts.dump_schemas && cd .. && git diff --exit-code schemas/ → leer
- rg -n '"schema_version": 1' backend/app/ → leer
- rg -n "EXPORT_SCHEMA_VERSION" backend/app/ → nur "= 2"
- rg -n "ReportContractModel\.model_validate|EvidenceMapModel\.model_validate" backend/app/api/report.py → trifft

## Doku

- docs/archive/worklogs/<YYYY-MM-DD>-task-02-wire-contracts-arbeitsprotokoll.md
- CHANGELOG.md [Unreleased]: "Layer 0: Contracts in API verdrahtet (Sub-Slice 02)"

## NICHT

- Frontend nicht anfassen — Task 15.
- models/report.py-Dataclasses nicht löschen — nur als deprecated markieren (DeprecationWarning).
- NICHT committen, NICHT pushen.
```

## Verify

```bash
cd "$WT/backend" && uv run pytest -x -q
cd "$WT/backend" && uv run python -m app.contracts.dump_schemas
cd "$WT" && git diff --exit-code schemas/
rg -n '"schema_version": 1' "$WT/backend/app/" || echo "clean"
```

Commit + Push: via `/agora-next-task` Schritt 6 oder manuell.
