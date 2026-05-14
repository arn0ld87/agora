---
description: MAI-17 — radon cc --min C als CI-Step. Neue Funktionen mit cyclomatic complexity > 15 werden blockiert.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-17-radon-gate — `radon` Komplexitäts-Gate

## Ziel

`uv run radon cc app --min C --total-average -nc` läuft in CI. Funktionen mit Rang D oder schlechter (Cyclomatic Complexity > 20) blockieren den merge. Bestehende Hotspots werden in einer Allowlist gepinnt, neue Funktionen müssen sauber sein.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-17/`.
- Branch: `feat/mai-17-radon-gate`.

## Schritt-für-Schritt

### Schritt 1: Baseline messen

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-17/backend

# radon installieren (dev-dep, falls nicht da)
uv add --dev radon

# Baseline-Report
uv run radon cc app --min C --no-assert --total-average | tee /tmp/radon-baseline.txt
```

### Schritt 2: Allowlist anlegen

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-17/backend

# Bestehende C/D/E/F-Ranks ausziehen — pinnt heutige Hotspots
uv run radon cc app --min C --no-assert -j > /tmp/radon.json
python3 -c "
import json
data = json.load(open('/tmp/radon.json'))
allow = []
for path, blocks in data.items():
    for block in blocks:
        if block.get('rank', 'A') in ('C', 'D', 'E', 'F'):
            allow.append(f'{path}::{block[\"name\"]}')
open('radon-allowlist.txt', 'w').write('\n'.join(sorted(allow)) + '\n')
print(f'Allowlist mit {len(allow)} Einträgen erzeugt.')
"

cat radon-allowlist.txt | head -20
```

`backend/radon-allowlist.txt` (Beispiel-Inhalt):

```
app/services/report_agent/agent.py::generate_report
app/services/simulation_runner.py::run_simulation_step
# ...
```

### Schritt 3: Wrapper-Skript für CI

`backend/scripts/check_complexity.py`:

```python
"""MAI-17: radon-Komplexitäts-Gate mit Allowlist.

Liest radon-Output und failt bei Rank≥D, wenn die Funktion nicht in
radon-allowlist.txt steht. Erlaubt damit Bestand, blockiert neue Hotspots.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = REPO_ROOT / "radon-allowlist.txt"
SEVERITY_FAIL = {"D", "E", "F"}


def load_allowlist() -> set[str]:
    if not ALLOWLIST.exists():
        return set()
    return {
        line.strip()
        for line in ALLOWLIST.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def main() -> int:
    result = subprocess.run(
        ["radon", "cc", "app", "--min", "C", "--no-assert", "-j"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return 1

    data = json.loads(result.stdout or "{}")
    allowed = load_allowlist()
    violations: list[str] = []

    for path, blocks in data.items():
        for block in blocks:
            rank = block.get("rank", "A")
            if rank not in SEVERITY_FAIL:
                continue
            key = f"{path}::{block['name']}"
            if key in allowed:
                continue
            violations.append(
                f"{path}:{block.get('lineno')}  {block['name']}  rank={rank} "
                f"complexity={block.get('complexity')}"
            )

    if violations:
        print("::error::Neue Komplexitäts-Hotspots (rank D+) gefunden:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nFix-Optionen:\n"
            "  1) Funktion refactorn (presser-Schnitt, Sub-Funktionen).\n"
            "  2) Falls bewusst akzeptiert: in backend/radon-allowlist.txt eintragen\n"
            "     mit Kommentar # WARUM-Erlaubt.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: keine neuen Komplexitäts-Hotspots ({len(allowed)} pre-existing allowed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Schritt 4: CI-Step

`.github/workflows/contract-gates.yml` — neuer Step im bestehenden Job:

```yaml
      - name: Cyclomatic-Complexity-Gate (MAI-17)
        run: |
          cd backend && uv run python scripts/check_complexity.py
```

### Schritt 5: Lokal test-run

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-17/backend

# Sollte clean sein (alle bestehenden D+ sind in der Allowlist)
uv run python scripts/check_complexity.py
echo "Exit: $?"

# Drift-Demo — neue komplexe Funktion einfügen
cat >> app/services/test_radon_demo.py <<'EOT'
def demo_complex(x):
    if x == 1: return 1
    elif x == 2: return 2
    elif x == 3: return 3
    elif x == 4: return 4
    elif x == 5: return 5
    elif x == 6: return 6
    elif x == 7: return 7
    elif x == 8: return 8
    elif x == 9: return 9
    elif x == 10: return 10
    elif x == 11: return 11
    elif x == 12: return 12
    elif x == 13: return 13
    elif x == 14: return 14
    elif x == 15: return 15
    elif x == 16: return 16
    elif x == 17: return 17
    elif x == 18: return 18
    elif x == 19: return 19
    elif x == 20: return 20
    elif x == 21: return 21
    elif x == 22: return 22
    return 0
EOT

uv run python scripts/check_complexity.py
echo "Exit: $?"  # Erwartet 1

# Rückgängig
rm app/services/test_radon_demo.py
```

### Schritt 6: Doku ergänzen

`AGENTS.md` — neuer Abschnitt im Subagent-Knigge:

```markdown
### Komplexitäts-Budget (MAI-17)

Neue oder geänderte Funktionen müssen Rank C oder besser haben
(Cyclomatic Complexity ≤ 15). Subagent prüft mit:

    cd backend && uv run python scripts/check_complexity.py

Falls eine komplexe Funktion bewusst akzeptiert wird, Eintrag in
`backend/radon-allowlist.txt` mit Begründungs-Kommentar.
```

## Verifikation

```bash
# 1) Skript läuft clean
cd backend && uv run python scripts/check_complexity.py
echo "Exit: $?"  # Erwartet 0

# 2) Allowlist nicht leer (Migrationsschutz)
wc -l backend/radon-allowlist.txt

# 3) Drift-Demo funktioniert (siehe Schritt 5)

# 4) Workflow-Syntax
npx --yes @action-validator/cli@latest .github/workflows/contract-gates.yml
```

## Warum?

REFACTORING_PLAN (1).md M11.5: „Komplexitäts-Hotspots ohne dauerhafte Gate-Logik bauen sich nach jedem Sprint neu auf." Mit radon-Gate + Allowlist sind bestehende Hotspots nicht blockiert (Pragmatismus), aber neue müssen vom Subagent in saubere Sub-Funktionen geschnitten werden — bevor sie reviewfähig sind.

## Nächste Schritte

1. Worklog mit Allowlist-Counter (vor/nach).
2. CHANGELOG: `MAI-17 · radon-Komplexitäts-Gate (rank D+ blockiert, allowlist-basiert).`
3. **Mai-Welle abgeschlossen** — neuen Plan für Coverage-Sprint anlegen oder ADR-0004 (camel-oasis-Upgrade) öffnen.
