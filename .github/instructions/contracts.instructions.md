---
applyTo: "backend/app/contracts/**/*.py,schemas/**,frontend/src/contracts/**"
---

# Verträge und Schemas

Der Vertrag ist die Wahrheit. Backend-Pydantic-Modell, gerenderte JSON-Schemas unter
`schemas/` und die `zod`-Spiegel im Frontend beschreiben dasselbe — sie dürfen nicht
auseinanderlaufen.

## Reihenfolge

1. Pydantic-Modell in `backend/app/contracts/` ändern.
2. Contract-Tests anpassen oder ergänzen: `uv run pytest tests/contracts/ -x -q`.
3. Schemas neu rendern: `uv run python -m app.contracts.dump_schemas` (ohne `--check`).
4. Consumer nachziehen — Frontend-`zod`-Schema, Services, Fixtures.
5. Alles in **einen** Commit. Ein gerenderter Schema-Stand ohne das zugehörige Modell ist Drift.

## Verbindlich

- Keine Dataclasses und keine handgeschriebenen Inline-Schemas für API-Verträge.
- Breaking Changes am Vertrag brauchen ein CHANGELOG-Fragment unter `changelog.d/<pr-nr>-<slug>.md` (nie direkt `CHANGELOG.md`) und, bei Release-Wirkung, einen Eintrag in `ROADMAP.md`.
- Feldnamen und Enums nicht stillschweigend umbenennen; Consumer zuerst suchen.
- `EvidenceSourceKind` und die Evidence-Validatoren stehen unter ADR-0002 und sind gesperrt.

## Gate für diesen Scope

Nur Contract-Tests und Schema-Check — kein Ruff, kein mypy:

```bash
cd backend
uv run pytest tests/contracts/ -x -q
uv run python -m app.contracts.dump_schemas --check
```

Vor dem Push `bash scripts/pre-push-gate.sh schemas`.
