# Arbeitsprotokoll — Sub-Slice 11 · Task 11 · Voice-Lint CI-Check

**Datum:** 2026-05-03
**Layer:** 2
**Subagent:** agora-test-worker (Sonnet, direkt via Orchestrator)
**Branch:** feat/layer-2-task-11-voice-lint
**Refs:** #11 (Voice-Lint CI-Check — kein dediziertes GitHub-Issue, Teil der Heuristik-Tabelle)

## Ist-Stand vor dem Slice

- DACH-Voice-Constraints (Task 10) bereits implementiert in `oasis_profile_generator.py`
- `voice_register` Feld mit 4 Werten (`formal-de`, `neutral-de`, `technical-de`, `skeptisch-de`)
- `_rule_based_voice_register` Heuristik vorhanden
- Keine dedizierten Tests, die diese Constraints automatisiert pinnen
- Kein CI-Check, der Voice-Register-Verstöße abfängt

## Änderungen

### Neu: `backend/tests/contracts/test_voice_register.py`

9 Testfälle in 2 Klassen:

1. `TestVoiceRegisterContract` — Contract-Validation
   - `test_valid_voice_register_accepted[formal-de|neutral-de|skeptisch-de|technical-de]` — alle 4 Werte parametrisiert
   - `test_invalid_voice_register_rejected` — `casual-de` muss von `PersonaModel` rejected werden
   - `test_voice_register_default_is_neutral_de` — Default prüfen
   - `test_voice_register_none_allowed` — Legacy-Compat (`None`)

2. `TestVoiceRegisterGeneration` — Heuristik-Validation
   - `test_rule_based_returns_only_valid_values` — 9 Input-Kombinationen (Student, Expert, Journalist, Company, GovernmentAgency, NGO, Developer, Random, leer) → immer erlaubter Output
   - `test_rule_based_is_deterministic` — 5 Iterationen, gleicher Input → gleicher Output

## Verifikation

```bash
cd backend && uv run pytest tests/contracts/test_voice_register.py -x -v
# 9 passed in 1.39s

cd backend && uv run pytest tests/contracts/ -x -v
# 62 passed in 0.95s (alle Contract-Tests)

cd backend && uv run pytest -x -q
# 1340 passed, 9 skipped, 3 deselected, 3 warnings in 55.90s

cd backend && uv run python -m app.contracts.dump_schemas
# idempotent — keine Änderungen

cd backend && uv run ruff check tests/contracts/test_voice_register.py
# All checks passed!
```

## Akzeptanzkriterien

- [x] Alle 4 erlaubten Voice-Register-Werte werden vom Contract akzeptiert
- [x] Ungültige Werte werden rejected
- [x] `_rule_based_voice_register` liefert nur erlaubte Werte
- [x] Heuristik ist deterministisch
- [x] Kein Schema-Drift
- [x] Keine Regression im vollen Test-Suite (1340 passed)
- [x] Lint clean

## Nächster Slice

Reihe 10 → Task 13 · Time-Series-Sampling + Section-Dedup · Aufwand M · `agora-refactor-worker` (Sonnet)
