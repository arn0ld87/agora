---
description: Verdrahtet Pydantic-Contracts in api/report.py und report_agent.py - ersetzt rohe Dicts durch Modelle
allowed-tools: Read, Edit, Write, Grep, Bash
---

# /fix-task-02 — Contracts in API verdrahten

## Vorab

Stelle sicher, dass `/fix-task-01` durch ist (Tests grün, Schemas existieren).

## Implementierung

### 2.1 `backend/app/api/report.py` — Export auf Contract umstellen

Nach Z. 417 wurde bisher rohes Dict gebaut. Ersetze durch:

```python
from datetime import datetime, timezone
from app.contracts import (
    ReportContractModel, ReportModel, EvidenceMapModel,
)

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
```

### 2.2 `backend/app/services/report_agent.py` — schema_version-Drift fixen

```bash
# Drei Stellen, im Zip verifiziert:
sed -i 's/"schema_version": 1,/"schema_version": 2,/' backend/app/services/report_agent.py
# Vorher: Z. 567 und 1127
# Z. 184 ist schon korrekt (init=2)
```

Aber besser: Pydantic-Modelle nutzen statt rohe Dicts. Refactor `_save_evidence_section`
und ähnliche Stellen Schritt-für-Schritt zu `EvidenceMapModel`-Instanzen.

### 2.3 Backwards-Compat-Reader

In `backend/app/services/report_agent.py`: alte v1-Reports einlesen können, aber
intern auf v2 hochmigrieren. Kleine Funktion `migrate_v1_to_v2(raw: dict) -> dict`.
Hängt an Issue #107.

## Verifikation

```bash
cd backend && uv run pytest -x -q
cd backend && uv run python -m app.contracts.dump_schemas
git diff schemas/                              # leer
rg -n '"schema_version": 1' backend/app/      # leer
rg -n "EXPORT_SCHEMA_VERSION" backend/app/    # nur "= 2"
```

## NICHT machen

- Frontend noch nicht (Task 04).
- Keine `models/report.py`-Dataclasses löschen, nur als deprecated markieren.
