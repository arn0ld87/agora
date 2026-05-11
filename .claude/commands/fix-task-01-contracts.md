---
description: Layer 0 - Pydantic-Contracts anlegen und Schema-Drift im echten Code fixen (Implementierung via Sonnet)
allowed-tools: Read, Bash, Grep, Glob, Agent
argument-hint: (keine)
---

# /fix-task-01 — Pydantic-Contracts (Layer 0, Sonnet-Dispatch)

Du bist Orchestrator. **Sonnet** macht die Implementierung via `agora-refactor-worker`. Du machst Vorab-Check, Worktree, Dispatch, Verify.

## Schritt 1: Vorab-Verifikation (Haupt-Claude, Bash)

```bash
cd /Volumes/T7/Projekte/agora
# Schema-Drift im echten Code (verifiziert: 184=2, 567=1, 1127=1)
rg -n '"schema_version"' backend/app/services/report_agent.py backend/app/api/report.py
# EXPORT_SCHEMA_VERSION (verifiziert: report.py:379 = 1)
rg -n "EXPORT_SCHEMA_VERSION" backend/app/api/
# Dataclasses zählen
rg -c "@dataclass" backend/app/models/ backend/app/services/
```

Wenn alles bereits clean ist (kein `: 1` mehr): Stop, melden „Task 01 ist bereits durch."

## Schritt 2: Worktree

```bash
WT=/Volumes/T7/Projekte/agora-worktrees/feat-layer-0-task-01-contracts
git -C /Volumes/T7/Projekte/agora fetch origin --quiet
git -C /Volumes/T7/Projekte/agora worktree add -b feat/layer-0-task-01-contracts "$WT" origin/main
echo "WT=$WT"
```

## Schritt 3: Sonnet-Dispatch (Agent-Tool)

`subagent_type: "agora-refactor-worker"`, `description: "fix-task-01 contracts"`, `prompt`:

```

Arbeite ausschließlich im Worktree <WT>. Sub-Slice: Layer 0 / Task 01 — Pydantic-Contracts anlegen + Schema-Drift fixen.

## Edits

1. Contracts anlegen (neue Dateien):
   - backend/app/contracts/__init__.py
   - backend/app/contracts/report_contract.py
   - backend/app/contracts/persona_contract.py
   - backend/app/contracts/dump_schemas.py
   Nutze die Pydantic-Modelle gemäß PLAN.md Teil C (ReportContractModel, ReportModel, EvidenceMapModel, PersonaModel, PersonaQuotaPlan, PersonaQuotaActual). Strict-Mode (extra="forbid"), v2-Syntax.

2. Schema-Drift fixen in backend/app/services/report_agent.py:
   - Z. 567: "schema_version": 1 → "schema_version": 2
   - Z. 1127: "schema_version": 1 → "schema_version": 2

3. Export bumpen in backend/app/api/report.py:379:
   - EXPORT_SCHEMA_VERSION = 1 → EXPORT_SCHEMA_VERSION = 2

4. Tests anlegen:
   - backend/tests/contracts/__init__.py (leer)
   - backend/tests/contracts/test_report_contract.py
   - backend/tests/contracts/test_persona_quota.py
   Tests: model_validate auf Sample-Dicts, schema_version=2 erzwungen, extra-Felder werfen.

5. Schemas regenerieren:
   cd backend && uv run python -m app.contracts.dump_schemas
   ls ../schemas/ → muss Files enthalten

## Akzeptanz nach Run

- cd backend && uv run pytest tests/contracts/ -v → alle grün
- cd backend && uv run python -m app.contracts.dump_schemas → idempotent
- git diff schemas/ → nur erwartete neue/geänderte Dateien
- rg -n '"schema_version".*1' backend/app/ → leer
- rg -n "EXPORT_SCHEMA_VERSION = 1" backend/ → leer

## Doku

- docs/archive/worklogs/<YYYY-MM-DD>-task-01-contracts-arbeitsprotokoll.md (knapp: Files, Drift-Stellen, Tests)
- CHANGELOG.md [Unreleased]: "Layer 0: Pydantic-Contracts (Sub-Slice 01)"

## NICHT

- Keine bestehenden @dataclass aus models/ löschen — werden in Task 02 deprecated.
- chat_json nicht anfassen — Task 04.
- Keine Frontend-Touch.
- NICHT committen, NICHT pushen — Edits unstaged/staged liegen lassen.
```

## Schritt 4: Verify (Haupt-Claude, im Worktree)

```bash
cd "$WT/backend"
uv run pytest tests/contracts/ -v
uv run python -m app.contracts.dump_schemas
cd "$WT" && git diff --stat schemas/
rg -n '"schema_version".*1' backend/app/ || echo "clean"
```

Bei rot: Fehler an User reporten, optional einmaligen Re-Dispatch an `agora-refactor-worker` mit konkretem Fehler-Brief.

## Schritt 5: Commit (manuell oder via /agora-next-task)

Diesen Slash-Command nicht selbst committen lassen. Übergib an User oder an `/agora-next-task` Schritt 6.
