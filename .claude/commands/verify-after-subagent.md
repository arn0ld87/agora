---
description: Pflicht-Verifikation nach jedem Subagent-Run. Sequential Gate.
allowed-tools: Bash
---

# /verify-after-subagent

Führe nach jedem Subagent-Output diese Checks aus, in dieser Reihenfolge.
Brich bei erstem Fehler ab — kein Auto-Fix.

## 1. Pydantic-Contracts kompilieren

```bash
cd backend && uv run python -c "
from app.contracts import (
    ReportContractModel, ReportModel, EvidenceMapModel,
    PersonaModel, PersonaQuotaPlan, PersonaQuotaActual
)
print('OK: alle Contracts importierbar')
"
```

## 2. Schema-Dump idempotent

```bash
cd backend && uv run python -m app.contracts.dump_schemas
cd .. && git diff --exit-code schemas/ \
  || { echo "::error::Schemas gedriftet"; exit 1; }
```

## 3. Contract-Tests

```bash
cd backend && uv run pytest tests/contracts/ -x -v
```

## 4. Voller Backend-Test (Regressions)

```bash
cd backend && uv run pytest -x -q
```

## 5. Lint

```bash
cd backend && uv run ruff check . && uv run mypy app
```

## 6. Frontend (wenn Layer 4 berührt)

```bash
cd frontend && npm run check && npm run test
```

## 7. Schema-Drift im Code (kein Rückzug auf v1)

```bash
rg -n '"schema_version": 1' backend/app/  # muss leer sein nach Task 02
rg -n "EXPORT_SCHEMA_VERSION = 1" backend/app/  # muss leer sein
```

## 8. Anti-Dekorations-Check

```bash
rg -n "deepcopy\(global_items\[:2\]\)" backend/app/services/report_agent.py
# Nach Task 04: leer
```

Wenn alle 8 grün: ✅ Subagent-Output kann committet werden.
Sonst: ❌ Fehler explizit reporten, NICHT auto-fixen.
