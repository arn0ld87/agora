---
description: Layer 0 - Pydantic-Contracts anlegen und Schema-Drift im echten Code fixen
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: (keine)
---

# /fix-task-01 — Pydantic-Contracts (Layer 0)

## Vorab-Verifikation

```bash
# Schema-Drift im echten Code (verifiziert: 184=2, 567=1, 1127=1)
rg -n '"schema_version"' backend/app/services/report_agent.py backend/app/api/report.py
# EXPORT_SCHEMA_VERSION (verifiziert: report.py:379 = 1)
rg -n "EXPORT_SCHEMA_VERSION" backend/app/api/
# Dataclasses zählen
rg -c "@dataclass" backend/app/models/ backend/app/services/
```

## Implementierung

1. **Contracts anlegen** (Files liegen schon im Plan, nur reinkopieren):
   - `backend/app/contracts/__init__.py`
   - `backend/app/contracts/report_contract.py`
   - `backend/app/contracts/persona_contract.py`
   - `backend/app/contracts/dump_schemas.py`
2. **Schema-Drift fixen** in `backend/app/services/report_agent.py`:
   - Z. 567: `"schema_version": 1` → `"schema_version": 2`
   - Z. 1127: `"schema_version": 1` → `"schema_version": 2`
3. **Export bumpen** in `backend/app/api/report.py:379`:
   - `EXPORT_SCHEMA_VERSION = 1` → `EXPORT_SCHEMA_VERSION = 2`
4. **Tests anlegen**:
   - `backend/tests/contracts/__init__.py` (leer)
   - `backend/tests/contracts/test_report_contract.py`
   - `backend/tests/contracts/test_persona_quota.py`
5. **Schemas regenerieren**:
   ```bash
   cd backend && uv run python -m app.contracts.dump_schemas
   ls ../schemas/
   ```

## Verifikation

```bash
cd backend && uv run pytest tests/contracts/ -v        # alle grün
cd backend && uv run python -m app.contracts.dump_schemas
cd .. && git diff schemas/    # nur erwartete Änderungen
rg -n '"schema_version".*1' backend/app/                # leer
```

## NICHT machen

- Existierende Dataclasses noch nicht löschen — werden in Task 02 deprecated.
- `chat_json` noch nicht anfassen — Task 04.
- Keine Frontend-Touch.
