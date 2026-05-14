---
description: MAI-05 — Wording-Glossar-Verstöße blockieren CI via scripts/check_voice.py --strict.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-05-voice-lint-ci — Voice-Lint als CI-Pflicht

## Ziel

`backend/scripts/check_voice.py --strict` läuft als CI-Job in `contract-gates.yml` und blockiert merge bei Wording-Glossar-Verstößen (`prediction`, `rehearsal`, `god's eye view`, `high-fidelity digital world`, `public opinion prediction`, `Agentic-Prediction-Engine`).

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-05/`.
- Branch: `feat/mai-05-voice-lint-ci`.

## Schritt-für-Schritt

### Schritt 1: Status check_voice.py

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-05
cat backend/scripts/check_voice.py
```

### Schritt 2: --strict-Modus + jsonl-Output ergänzen

`backend/scripts/check_voice.py`:

```python
#!/usr/bin/env python3
"""Voice-Lint: Wording-Glossar v1 Enforcement (Task 11 PLAN.md).

Modi:
  python check_voice.py            # Findings als Text, exit 0
  python check_voice.py --strict   # Findings als jsonl auf stdout, exit 1 bei Treffer
  python check_voice.py --jsonl    # Findings als jsonl auf stdout, exit 0 (für Reports)

Quelle: docu/glossary-wording.md.
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Hard-Block-Terme (case-insensitive). Quelle: docu/glossary-wording.md Issue #175.
FORBIDDEN_TERMS = [
    r"\bfuture prediction\b",
    r"\brehearsal of the future\b",
    r"\bgod's eye view\b",
    r"\bhigh-fidelity digital world\b",
    r"\bpublic opinion prediction\b",
    r"\bAgentic-Prediction-Engine\b",
    # US-Marketing-Phrasen
    r"\brevolutionary\b",
    r"\bseamless(ly)?\b",
    r"\bgame-?changer\b",
]

# Scan-Pfade (Runtime-Code + Prompts + Doku; Tests dürfen die Terme zitieren).
SCAN_PATHS = [
    "backend/app/services/report_prompts.py",
    "backend/app/services/report_agent/",
    "backend/app/services/",
    "frontend/src/",
    "prompts/",
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
]

# Tests dürfen die Terme als Snapshot enthalten (z.B. tests/test_wording_glossary.py).
EXCLUDE_PATTERNS = [
    r"^backend/tests/",
    r"^frontend/tests/",
    r"^docu/glossary-wording\.md$",
    r"^docu/history/",
    r"\.snapshot\b",
]


def scan_file(path: Path) -> list[dict]:
    findings: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return findings
    for line_no, line in enumerate(text.splitlines(), 1):
        for pattern in FORBIDDEN_TERMS:
            if re.search(pattern, line, re.IGNORECASE):
                findings.append({
                    "file": str(path.relative_to(REPO_ROOT)),
                    "line": line_no,
                    "term": pattern,
                    "context": line.strip()[:200],
                })
    return findings


def should_exclude(rel_path: str) -> bool:
    return any(re.search(p, rel_path) for p in EXCLUDE_PATTERNS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="exit 1 bei Findings")
    parser.add_argument("--jsonl", action="store_true", help="jsonl output statt human")
    args = parser.parse_args()

    all_findings: list[dict] = []
    for scan in SCAN_PATHS:
        scan_path = REPO_ROOT / scan
        if not scan_path.exists():
            continue
        if scan_path.is_file():
            files = [scan_path]
        else:
            files = list(scan_path.rglob("*"))
        for f in files:
            if not f.is_file():
                continue
            rel = str(f.relative_to(REPO_ROOT))
            if should_exclude(rel):
                continue
            if f.suffix not in {".py", ".ts", ".js", ".vue", ".md"}:
                continue
            all_findings.extend(scan_file(f))

    if args.jsonl or args.strict:
        for finding in all_findings:
            print(json.dumps(finding, ensure_ascii=False))
    else:
        if not all_findings:
            print("OK: keine Wording-Glossar-Verstöße gefunden.")
        else:
            for f in all_findings:
                print(f"{f['file']}:{f['line']}  {f['term']}\n    {f['context']}")

    if args.strict and all_findings:
        print(f"::error::{len(all_findings)} Wording-Glossar-Verstöße — bitte fixen.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Schritt 3: CI-Job

`.github/workflows/contract-gates.yml` — neuer Step:

```yaml
      - name: Voice-Lint (MAI-05, Task 11)
        run: |
          cd backend && uv run python scripts/check_voice.py --strict
        # exit 1 bei Wording-Glossar-Verstößen
```

### Schritt 4: Lokal test-run

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-05/backend
uv run python scripts/check_voice.py
# Sollte leer sein bei sauberem Repo.

uv run python scripts/check_voice.py --strict
echo "Exit: $?"

# Triggern testen
echo "# This is a revolutionary feature" > /tmp/test-voice.md
cp /tmp/test-voice.md ../README.md.bak
echo "revolutionary" >> ../README.md
uv run python scripts/check_voice.py --strict
echo "Exit: $?"  # Erwartet 1
mv ../README.md.bak ../README.md 2>/dev/null || git checkout -- ../README.md
```

## Verifikation

```bash
# 1) Bestehender Glossar-Test bleibt grün
cd backend && uv run pytest tests/test_wording_glossary.py -x -v

# 2) Skript exit 0 auf sauberem Repo
cd backend && uv run python scripts/check_voice.py --strict
echo "Exit: $?"  # Erwartet 0

# 3) Workflow-Syntax
cd .. && npx --yes @action-validator/cli@latest \
  .github/workflows/contract-gates.yml
```

## Warum?

PLAN.md Heuristik-Tabelle Reihe 9 (Task 11): „Voice-Lint CI-Check". Heute existiert `check_voice.py`, läuft aber nicht zwingend in CI. Damit kann ein PR mit „revolutionary seamless prediction engine" durchrutschen — das Wording-Glossar v1 ist nicht erzwungen.

## Nächste Schritte

1. Worklog `docu/2026-05-14-mai-05-arbeitsprotokoll.md`.
2. CHANGELOG: `MAI-05 · Voice-Lint (check_voice.py --strict) als CI-Pflichtschritt.`
3. `/fix-mai-07-quote-marker-css` für Block-E-Polish.
