# Sub-Slice F — Demographische Namensverteilung (Issue #214)

**Datum:** 2026-05-03  
**Branch:** `fix/task-F-demographie-namen`  
**Bearbeiter:** Agora-Backend-Refactor-Worker (Sonnet)

---

## Problem

Alle generierten Personas trugen ausschließlich deutschsprachige Namen. Die
DACH-Bevölkerung hat laut Destatis Mikrozensus 2024 rund 26 % Anteil mit
Migrationshintergrund. Unglaubwürdige Simulation.

---

## Phase 1 — Verify-First (rg-Output)

```
backend/app/services/oasis_profile_generator.py:197:    DACH_FIRST_NAMES = [...]  # 34 rein deutsche Namen
backend/app/services/oasis_profile_generator.py:204:    DACH_LAST_NAMES = [...]   # 30 rein deutsche Namen
backend/app/services/oasis_profile_generator.py:819:    display_name: "Lena Hoffmann", "Marcel Schmitz" (Beispiele rein deutsch)
backend/app/services/oasis_profile_generator.py:923:    display_name: "Lena Hoffmann", "Marcel Schmitz" (Beispiele rein deutsch)
```

Befund: Zwei Punkte erzwingen Deutsch-only-Namen:
1. `DACH_FIRST_NAMES` / `DACH_LAST_NAMES` Klassenvariablen (Fallback-Pfad)
2. Prompt-Beispiele in DE- und EN-Varianten (LLM-Pfad)

---

## Änderungen

### Neu: `backend/app/services/persona_demographics.py`

- Pydantic-Modell `NameOriginQuota` (`ConfigDict(extra="forbid")`)
- `DACH_NAME_ORIGIN_QUOTAS`: 10 Buckets nach Destatis Mikrozensus 2024
  (aggregiert mit BFS Schweiz, Statistik Austria)
- Assert: Summen-Check `abs(sum - 1.0) < 0.01` bei Import
- `classify_name_origin(full_name)`: regelbasiert, kein LLM, fail-soft zu
  `german_native`. Erkennung via Unicode-Zeichen-Muster (türkisch: İ/ı/Ş/ş/Ğ/ğ,
  ex-YU: ć/č/š/ž/đ, polnisch: ą/ę/ł/ń/ś/ź/ż) + Lookup-Listen.
  Wichtig: `Ü/ü` und `Ö/ö` aus Türkisch-Pattern entfernt (auch deutsch).
- `build_name_quota_prompt_block()` / `build_name_quota_prompt_block_en()`:
  DRY-Helper, erzeugen Quota-Block aus Single Source of Truth

### Geändert: `backend/app/services/oasis_profile_generator.py`

- Import: `from .persona_demographics import DACH_NAME_ORIGIN_QUOTAS, build_name_quota_prompt_block, build_name_quota_prompt_block_en`
- `DACH_FIRST_NAMES` / `DACH_LAST_NAMES` Klassenvariablen entfernt
- `_pick_dach_name()`: von statischem deutschen Pool auf gewichteten `random.choices`
  aus `DACH_NAME_ORIGIN_QUOTAS` (Single Source of Truth)
- DE-Individual-Prompt: `build_name_quota_prompt_block()` eingebettet, Beispiele
  aus "Lena Hoffmann / Marcel Schmitz" auf "obige Namensverteilung" geändert
- EN-Individual-Prompt: `build_name_quota_prompt_block_en()` eingebettet
- DE-Group-Prompt: `build_name_quota_prompt_block()` eingebettet
- EN-Group-Prompt: `build_name_quota_prompt_block_en()` eingebettet
- `print()`-Statements (4 Stellen) durch `logger.info()` / `logger.debug()` ersetzt

### Neu: `backend/tests/eval/test_persona_name_distribution.py`

6 `@pytest.mark.eval`-Tests + 1 `@pytest.mark.llm`-Test (CI-exkludiert):
- `test_demographics_quota_sums_to_one`
- `test_all_buckets_have_names`
- `test_classify_name_origin_basics` (Yılmaz/Haddad/Müller)
- `test_classify_name_origin_extended` (Petrović, Wiśniewski, Nguyen, Okafor, Rossi)
- `test_classify_name_origin_fallback`
- `test_migration_share_in_quotas` (Destatis ~26 %, Check 24–28 %)

### Geändert: `backend/pyproject.toml`

Pytest-Marker `eval` und `llm` registriert.

---

## Daten-Quellen

Alle Werte sind **explizite Konstanten im Code** — nicht aus dem Internet gezogen.

| Quelle | Nutzung |
|---|---|
| Destatis Mikrozensus 2024, Tab. 1 | Hauptbevölkerungsanteil 26 % MH |
| BFS Schweiz Statistisches Jahrbuch 2024 | CH-Anteil (Ausländer ~26 %) |
| Statistik Austria Mikrozensus 2023 | AT-Anteil (MH ~24 %) |

Buckets-Gewichtung ist DACH-aggregierte Schätzung, keine offizielle Statistik-Tabelle.
Genauigkeit ausreichend für Plausibilitäts-Ziel; kein wissenschaftlicher Anspruch.

---

## Verify-Output

```
# Eval-Tests
cd backend && uv run pytest -x tests/eval/test_persona_name_distribution.py -v -m eval
→ 6 passed, 1 deselected

# Volltest ohne LLM
cd backend && uv run pytest -x -q -m "not llm"
→ 1329 passed, 9 skipped, 1 deselected

# Ruff app/
cd backend && uv run ruff check app/
→ All checks passed!

# Mypy persona_demographics.py
cd backend && uv run mypy app/services/persona_demographics.py
→ Success: no issues found in 1 source file

# Glossar-Check
rg "prediction|rehearsal|god.s eye view" backend/app/services/oasis_profile_generator.py
→ (leer — kein Treffer)
```

---

## Wording-Glossar-Compliance

Geprüft: Kein Vorkommen von `prediction`, `rehearsal`, `god's eye view`,
`high-fidelity digital world`, `public opinion prediction`,
`Agentic-Prediction-Engine` in den geänderten Dateien.

---

## Hardstops eingehalten

- Quoten-Konstanten NICHT aus dem Internet: alle Werte sind hart kodiert
- Kein LLM im Test-Pfad: `@pytest.mark.llm` ist CI-exkludiert
- Keine Halb-Migration: Fallback-Pfad (`_pick_dach_name`) und alle 4
  Prompt-Varianten (DE+EN, Individual+Group) vollständig migriert
- Kein Commit — Diff liegt für Orchestrator bereit
