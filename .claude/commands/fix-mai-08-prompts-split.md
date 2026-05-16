---
description: MAI-08 — backend/app/services/report_prompts.py (508 LOC) wird zu einem Paket mit 4 Modulen. Re-Export hält Imports kompatibel.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-08-prompts-split — `report_prompts.py` aufteilen

## Ziel

`backend/app/services/report_prompts.py` ist ein Paket `report_prompts/` mit `planning.py`, `sections.py`, `react.py`, `chat.py`. Alle bestehenden Imports (`from app.services.report_prompts import …`) bleiben kompatibel durch `__init__.py`-Re-Export.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-08/`.
- Branch: `refactor/mai-08-prompts-split`.

## Schritt-für-Schritt

### Schritt 1: Cluster identifizieren

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-08
wc -l backend/app/services/report_prompts.py
# Erwartet: ~508 LOC

# Konstanten auflisten
rg -n "^[A-Z_]+\s*=" backend/app/services/report_prompts.py | head -40
```

Cluster-Zuordnung:

| Cluster | Konstanten/Funktionen | Ziel-Datei |
|---|---|---|
| Planning | `PLAN_*`, `OUTLINE_*`, `DEFAULT_REPORT_SECTIONS` | `planning.py` |
| Sections | `SECTION_SYSTEM_PROMPT_TEMPLATE`, `SECTION_USER_PROMPT_TEMPLATE`, Hardstops | `sections.py` |
| ReACT | `REACT_*`, Observation/Force-Final-Templates | `react.py` |
| Chat | `CHAT_*` | `chat.py` |

### Schritt 2: Paket-Struktur anlegen

```bash
mkdir -p backend/app/services/report_prompts/
```

### Schritt 3: Module schreiben

`backend/app/services/report_prompts/planning.py`:

```python
"""MAI-08: Planning-Cluster aus dem ursprünglichen report_prompts.py.

Enthält:
- DEFAULT_REPORT_SECTIONS  (Vertrags-konstante für required_sections_validator)
- PLAN_SYSTEM_PROMPT, PLAN_USER_PROMPT, OUTLINE_*
"""

# (Inhalt aus dem alten File, nur Planning-Konstanten + Hilfsfunktionen)

DEFAULT_REPORT_SECTIONS: list[tuple[str, str]] = [
    ("Executive Summary", "..."),
    ("Segment-Tabelle", "..."),
    # ...
]
```

`backend/app/services/report_prompts/sections.py`:

```python
"""MAI-08: Section-Generation-Prompts."""

SECTION_SYSTEM_PROMPT_TEMPLATE = """..."""
SECTION_USER_PROMPT_TEMPLATE = """..."""

# Evidence-Gating-Block (ADR-0002 — nicht schwächen!)
EVIDENCE_GATING_BLOCK = """<evidence_gating priority="hard">
...
</evidence_gating>"""
```

`backend/app/services/report_prompts/react.py`:

```python
"""MAI-08: ReACT-Loop-Templates."""

REACT_OBSERVATION_TEMPLATE = """..."""
REACT_INSUFFICIENT_TOOLS_MSG = """..."""
REACT_TOOL_LIMIT_MSG = """..."""
REACT_FORCE_FINAL_MSG = """..."""
REACT_UNUSED_TOOLS_HINT = """..."""
```

`backend/app/services/report_prompts/chat.py`:

```python
"""MAI-08: Chat-Mode-Prompts (Step 4 → Agent-Chat)."""

CHAT_SYSTEM_PROMPT_TEMPLATE = """..."""
CHAT_OBSERVATION_SUFFIX = """..."""
```

`backend/app/services/report_prompts/__init__.py`:

```python
"""MAI-08: Re-Export für Backward-Compatibility.

Alle Aufrufer importieren weiterhin via:
    from app.services.report_prompts import DEFAULT_REPORT_SECTIONS, SECTION_SYSTEM_PROMPT_TEMPLATE
"""

from .planning import (
    DEFAULT_REPORT_SECTIONS,
    PLAN_SYSTEM_PROMPT,
    PLAN_USER_PROMPT,
    OUTLINE_FORMAT_HINT,
)
from .sections import (
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    SECTION_USER_PROMPT_TEMPLATE,
    EVIDENCE_GATING_BLOCK,
)
from .react import (
    REACT_OBSERVATION_TEMPLATE,
    REACT_INSUFFICIENT_TOOLS_MSG,
    REACT_INSUFFICIENT_TOOLS_MSG_ALT,
    REACT_TOOL_LIMIT_MSG,
    REACT_FORCE_FINAL_MSG,
    REACT_UNUSED_TOOLS_HINT,
)
from .chat import (
    CHAT_SYSTEM_PROMPT_TEMPLATE,
    CHAT_OBSERVATION_SUFFIX,
)

__all__ = [
    "CHAT_OBSERVATION_SUFFIX",
    "CHAT_SYSTEM_PROMPT_TEMPLATE",
    "DEFAULT_REPORT_SECTIONS",
    "EVIDENCE_GATING_BLOCK",
    "OUTLINE_FORMAT_HINT",
    "PLAN_SYSTEM_PROMPT",
    "PLAN_USER_PROMPT",
    "REACT_FORCE_FINAL_MSG",
    "REACT_INSUFFICIENT_TOOLS_MSG",
    "REACT_INSUFFICIENT_TOOLS_MSG_ALT",
    "REACT_OBSERVATION_TEMPLATE",
    "REACT_TOOL_LIMIT_MSG",
    "REACT_UNUSED_TOOLS_HINT",
    "SECTION_SYSTEM_PROMPT_TEMPLATE",
    "SECTION_USER_PROMPT_TEMPLATE",
]
```

### Schritt 4: Aufrufer-Inventar VOR Löschung

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-08
rg -n "from .report_prompts import|from app.services.report_prompts import" \
   backend/ > /tmp/mai-08-callers.txt
cat /tmp/mai-08-callers.txt
# Jede Zeile muss nach Re-Export noch funktionieren — Test sichert das ab.
```

### Schritt 5: Altes File löschen

```bash
# Erst NACH grünem Test (Schritt 6) — hier nur Plan.
git rm backend/app/services/report_prompts.py
```

### Schritt 6: Tests

```bash
cd backend && uv run pytest -x -q
# Erwartung: 0 Regressionen, alle Imports lösen über __init__.py auf.

# Konkreter Re-Export-Test:
cd backend && uv run python -c "
from app.services.report_prompts import (
    DEFAULT_REPORT_SECTIONS,
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    REACT_OBSERVATION_TEMPLATE,
    CHAT_SYSTEM_PROMPT_TEMPLATE,
    EVIDENCE_GATING_BLOCK,
)
assert isinstance(DEFAULT_REPORT_SECTIONS, list)
assert 'evidence_gating' in EVIDENCE_GATING_BLOCK
print('OK: Re-Export funktioniert')
"
```

## Verifikation

```bash
# 1) Voll-Test
cd backend && uv run pytest -x -q

# 2) Linter + Types
cd backend && uv run ruff check . && uv run mypy app

# 3) ADR-0002 nicht verletzt — EVIDENCE_GATING_BLOCK enthält priority="hard"
rg -n 'priority="hard"' backend/app/services/report_prompts/sections.py

# 4) Keine Call-Site geändert
rg -n "from .report_prompts import|from app.services.report_prompts import" backend/ \
   > /tmp/mai-08-callers-after.txt
diff /tmp/mai-08-callers.txt /tmp/mai-08-callers-after.txt
# Erwartet: keine Diff
```

## Warum?

REFACTORING_PLAN (1).md §R13: „508 LOC mit 4 semantischen Clustern — Komplexität konzentriert." Reines Hygiene-Refactoring, kein User-Facing-Effekt. Aufteilung reduziert die Wahrscheinlichkeit, dass ein Subagent beim Editieren eines Cluster-Bereichs versehentlich einen anderen Cluster mit-faßt.

## Nächste Schritte

1. Worklog `docs/2026-05-14-mai-08-arbeitsprotokoll.md`.
2. CHANGELOG: `MAI-08 · report_prompts.py zu Paket aufgesplittet (planning/sections/react/chat).`
3. `/fix-mai-09-markdown-ts` (Block C, parallel zu B).
