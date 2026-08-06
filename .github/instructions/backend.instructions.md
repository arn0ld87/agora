---
applyTo: "backend/**/*.py"
---

# Backend (Flask + uv)

## Werkzeuge

- Abhängigkeiten und Läufe immer über `uv` (`uv run …`, `uv sync`), nie über `pip` oder ein aktiviertes venv.
- Arbeitsverzeichnis für alle Backend-Kommandos ist `backend/`.

## Verbindlich

- API-Verträge sind Pydantic-Modelle in `backend/app/contracts/`. Keine Dataclasses, keine handgeschriebenen Inline-Schemas.
- Verträge zuerst, Consumer danach. Ändert sich ein Contract, wandert der Schema-Dump in denselben Commit.
- Provider-Detection ausschließlich über die Registry. Keine lokalen Heuristiken daneben.
- Strukturiertes Logging statt `print()` in Produktivcode.
- Keine API-Keys oder Secrets in Code, Logs, Fixtures oder Docstrings.
- Keine neuen Query-Tokens `?token=`; URL-Auth nur über signierte Tickets.

## Evidence-Gating (ADR-0002) — nicht anfassen

Diese fünf Anker dürfen nicht geschwächt, umformuliert oder „aufgeräumt" werden ohne
`docs/decisions/0002-supersedes.md` und ausdrückliche Freigabe:

1. `<evidence_gating priority="hard">` in `backend/app/services/report_prompts/sections.py`
2. Hedge-Snapshot `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt`
3. Enum `EvidenceSourceKind` in `backend/app/contracts/report_contract.py`
4. Validator `cross_stakeholder_for_high`
5. Validator `reject_inferred_in_high_confidence`

## Vor dem Commit (sequentiell, Exit 0)

```bash
cd backend
uv run pytest tests/contracts/ -x -q
uv run python -m app.contracts.dump_schemas --check
uv run ruff check app/ tests/
uv run mypy app
```

Vor dem Push zusätzlich `bash scripts/pre-push-gate.sh backend`. Kein `--no-verify`.
