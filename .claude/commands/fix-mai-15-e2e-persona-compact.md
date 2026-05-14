---
description: MAI-15 — E2E-Stub-Mode nutzt persona_detail_level=compact. Kürzere Laufzeit, Coverage gleich.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-15-e2e-persona-compact — Compact-Personas in E2E

## Ziel

E2E-Smokes laufen mit `AGORA_PERSONA_DETAIL_LEVEL=compact` (Reduktion auf 8 Persona-Felder statt 30). Laufzeit pro E2E-Run sinkt ~20-30 %, ohne Coverage zu verlieren. Compact-Mode ist für Production weiterhin opt-in, nicht Default.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-15/`.
- Branch: `feat/mai-15-e2e-persona-compact`.

## Schritt-für-Schritt

### Schritt 1: Stub-Service prüfen

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-15
rg -n "persona_detail_level\|PERSONA_DETAIL_LEVEL" backend/
cat backend/app/utils/llm_e2e_stub.py | head -40
```

### Schritt 2: Compact-Persona-Schema im Stub

`backend/app/utils/llm_e2e_stub.py`:

```python
"""MAI-15: persona_detail_level=compact für E2E-Stub-Mode.

Reduziert Persona-Felder von ~30 auf 8 Pflicht-Felder.
Production-Default bleibt 'full'.
"""

import os

PERSONA_DETAIL_LEVEL = os.getenv("AGORA_PERSONA_DETAIL_LEVEL", "full")

COMPACT_PERSONA_FIELDS = {
    "persona_id",
    "name",
    "age",
    "occupation",
    "core_values",
    "communication_style",
    "current_concerns",
    "trust_anchors",
}


def stub_persona(persona_id: str, seed: int) -> dict:
    """Liefert deterministische Stub-Persona — bei compact nur Pflicht-Felder."""
    full_persona = {
        "persona_id": persona_id,
        "name": f"Stub-Persona-{seed:02d}",
        "age": 30 + (seed % 30),
        "occupation": f"Beruf-{seed % 10}",
        "core_values": ["Vertrauen", "Klarheit"],
        "communication_style": "direkt",
        "current_concerns": [f"Concern-{seed % 5}"],
        "trust_anchors": ["GP", "Heimwerker-Forum"],
        # Full-Felder (werden bei compact entfernt)
        "background_story": f"Lebenslauf {seed}…",
        "family_situation": "verheiratet, 2 Kinder",
        "income_bracket": "median",
        "media_consumption": ["Tagesschau", "ZEIT online"],
        "social_groups": ["Sportverein"],
        # ... weitere Full-Felder ...
    }
    if PERSONA_DETAIL_LEVEL == "compact":
        return {k: v for k, v in full_persona.items() if k in COMPACT_PERSONA_FIELDS}
    return full_persona
```

### Schritt 3: E2E-Workflow-ENV setzen

`.github/workflows/e2e-smokes.yml` — bei jedem der 4 Jobs den ENV-Block ergänzen:

```yaml
    env:
      AGORA_PROXY_PORT: '80'
      AGORA_E2E_BASE_URL: http://127.0.0.1:80
      AGORA_SKIP_EMBEDDING_PROBE: 'true'
      AGORA_E2E_LLM_MODE: 'stub'
      AGORA_PERSONA_DETAIL_LEVEL: 'compact'  # MAI-15: weniger Tokens, gleiche Coverage
```

### Schritt 4: Backend-Tests anpassen

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-15
rg -n "persona\." backend/tests/ | head -20
```

`backend/tests/test_e2e_stub.py` (neu, falls nicht da):

```python
"""MAI-15: Stub-Service-Tests für persona_detail_level."""

import os
from unittest.mock import patch
import pytest


def test_compact_persona_only_required_fields():
    with patch.dict(os.environ, {"AGORA_PERSONA_DETAIL_LEVEL": "compact"}):
        # Modul neu laden, damit ENV greift
        import importlib
        import app.utils.llm_e2e_stub as stub_mod
        importlib.reload(stub_mod)

        p = stub_mod.stub_persona("p01", 1)
        assert set(p.keys()) == stub_mod.COMPACT_PERSONA_FIELDS
        assert "background_story" not in p


def test_full_persona_default(monkeypatch):
    monkeypatch.delenv("AGORA_PERSONA_DETAIL_LEVEL", raising=False)
    import importlib
    import app.utils.llm_e2e_stub as stub_mod
    importlib.reload(stub_mod)

    p = stub_mod.stub_persona("p01", 1)
    assert "background_story" in p
    assert "family_situation" in p


def test_persona_id_stable_across_modes(monkeypatch):
    """Compact/Full müssen für selben seed dieselbe persona_id liefern."""
    monkeypatch.setenv("AGORA_PERSONA_DETAIL_LEVEL", "full")
    import importlib
    import app.utils.llm_e2e_stub as stub_mod
    importlib.reload(stub_mod)
    full = stub_mod.stub_persona("p01", 42)

    monkeypatch.setenv("AGORA_PERSONA_DETAIL_LEVEL", "compact")
    importlib.reload(stub_mod)
    compact = stub_mod.stub_persona("p01", 42)

    assert full["persona_id"] == compact["persona_id"] == "p01"
    assert full["name"] == compact["name"]
```

### Schritt 5: Laufzeit-Vergleich

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-15

# Laufzeit-Baseline (full) — eine lokale CI-Simulation
time AGORA_PERSONA_DETAIL_LEVEL=full \
  cd frontend && npx playwright test minimal-report.spec.ts --reporter=list

time AGORA_PERSONA_DETAIL_LEVEL=compact \
  cd frontend && npx playwright test minimal-report.spec.ts --reporter=list

# Erwartete Differenz: ~20-30% schneller mit compact
```

## Verifikation

```bash
# 1) Backend-Stub-Tests
cd backend && uv run pytest tests/test_e2e_stub.py -x -v

# 2) Voll-Test (kein Regression)
cd backend && uv run pytest -x -q

# 3) Workflow-Syntax
npx --yes @action-validator/cli@latest \
  .github/workflows/e2e-smokes.yml

# 4) Frontend-Build
cd frontend && npm run check
```

## Warum?

Issue #217 (CI-Pflicht-Optimierung): E2E-Stub generiert ~30 Felder pro Persona, davon nutzt die Smoke-Pipeline nur ~8. Compact-Mode entkoppelt Test-Laufzeit von Persona-Schema-Volumen und ist deterministisch (gleiche persona_id pro seed).

## Nächste Schritte

1. Worklog mit Laufzeit-Vergleich (full vs. compact, Sekunden).
2. CHANGELOG: `MAI-15 · E2E-Stub-Mode persona_detail_level=compact (~20-30% schneller).`
3. `/agora-mai-next-task` → Block F (`/fix-mai-16-status-sync-ci` oder `/fix-mai-17-radon-gate`).
