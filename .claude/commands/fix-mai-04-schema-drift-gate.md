---
description: MAI-04 — dump_schemas.py --check regeneriert und vergleicht byte-genau gegen schemas/. CI failt bei Drift.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-04-schema-drift-gate — Schema-Drift-Gate hart in CI

## Ziel

`uv run python -m app.contracts.dump_schemas --check` regeneriert die JSON-Schemas in einen Temp-Pfad und vergleicht byte-genau gegen `schemas/`. Drift → exit 1. CI-Job in `contract-gates.yml` blockiert merge bei nicht-committeten Schema-Änderungen.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-04/`.
- Branch: `feat/mai-04-schema-drift-gate`.

## Schritt-für-Schritt

### Schritt 1: Aktuelles dump_schemas.py lesen

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-04
cat backend/app/contracts/dump_schemas.py
```

### Schritt 2: --check-Flag implementieren

`backend/app/contracts/dump_schemas.py`:

```python
"""Dump JSON schemas of all Pydantic contracts.

Modi:
  python -m app.contracts.dump_schemas          # schreibt schemas/
  python -m app.contracts.dump_schemas --check  # vergleicht byte-genau, exit 1 bei Drift
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

# bestehende Imports der Contract-Klassen ...

SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "schemas"

# (CONTRACTS-Mapping bleibt unverändert)
CONTRACTS = {
    "persona.schema.json": PersonaModel,
    "report.schema.json": ReportModel,
    # ...
}


def dump_to(target_dir: Path) -> dict[str, str]:
    """Schreibt alle Schemas nach target_dir und liefert {filename: content_str}."""
    target_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for filename, model in CONTRACTS.items():
        schema = model.model_json_schema()
        text = json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        (target_dir / filename).write_text(text, encoding="utf-8")
        written[filename] = text
    return written


def check_drift() -> int:
    """Regeneriert in tmpdir und vergleicht byte-genau gegen schemas/.

    Returns:
        0 wenn clean, 1 wenn Drift entdeckt.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        regenerated = dump_to(tmp_dir)

        drift: list[str] = []
        for filename, regen_text in regenerated.items():
            existing = SCHEMAS_DIR / filename
            if not existing.exists():
                drift.append(f"FEHLT auf disk: schemas/{filename}")
                continue
            existing_text = existing.read_text(encoding="utf-8")
            if existing_text != regen_text:
                drift.append(f"DRIFT in schemas/{filename}")

        if drift:
            print("::error::Schema-Drift entdeckt — bitte regenerieren:")
            for line in drift:
                print(f"  - {line}")
            print("\nFix: cd backend && uv run python -m app.contracts.dump_schemas && git add schemas/")
            return 1
        print(f"OK: alle {len(regenerated)} Schemas matchen schemas/")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump or check Pydantic JSON schemas.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Vergleicht regenerierte Schemas byte-genau gegen schemas/ (exit 1 bei Drift).",
    )
    args = parser.parse_args()

    if args.check:
        return check_drift()

    dump_to(SCHEMAS_DIR)
    print(f"OK: {len(CONTRACTS)} Schemas in schemas/ aktualisiert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Schritt 3: CI-Job in contract-gates.yml

`.github/workflows/contract-gates.yml` — neuer Step im bestehenden `contract-gates`-Job:

```yaml
      - name: Schema-Drift-Check (MAI-04)
        run: |
          cd backend && uv run python -m app.contracts.dump_schemas --check
        # exit 1 bei nicht-committeten Schema-Änderungen → blockiert merge.
```

### Schritt 4: Lokal verifizieren

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-04

# Sollte clean sein
cd backend && uv run python -m app.contracts.dump_schemas --check
# Erwartet: OK: alle N Schemas matchen schemas/

# Drift künstlich erzeugen
echo '{"test": 1}' >> ../schemas/persona.schema.json
uv run python -m app.contracts.dump_schemas --check
# Erwartet: exit 1, "DRIFT in schemas/persona.schema.json"

# Rückgängig machen
cd .. && git checkout -- schemas/persona.schema.json
```

## Verifikation

```bash
# 1) --check ohne Drift exit 0
cd backend && uv run python -m app.contracts.dump_schemas --check
echo "Exit: $?"  # Erwartet 0

# 2) Workflow-Syntax
npx --yes @action-validator/cli@latest \
  .github/workflows/contract-gates.yml

# 3) Voll-Test (Schemas-Tests dürfen nicht regressieren)
cd backend && uv run pytest tests/contracts/ -x -v
```

## Warum?

Refactoring-Plan R12 fordert ein CI-Gate, das Zod-Spiegel und Pydantic-Contracts byte-genau synchron hält. Heute regeneriert der Workflow nur — er prüft nicht. Damit ist die Sicherheit „Schemas können nicht driften" nicht erzwungen.

## Nächste Schritte

1. Worklog `docu/2026-05-14-mai-04-arbeitsprotokoll.md`.
2. CHANGELOG: `MAI-04 · Schema-Drift-Gate (dump_schemas --check) als CI-Pflichtschritt.`
3. `/fix-mai-13-dependabot-cleanup` (Block A Abschluss).
