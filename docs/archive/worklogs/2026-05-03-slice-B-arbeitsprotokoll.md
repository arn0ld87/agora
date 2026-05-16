# Sub-Slice B — Arbeitsprotokoll: Manuell hinzugefügte Personas (Issue #210)

**Branch:** `fix/task-B-manuelle-personas`
**Datum:** 2026-05-03
**Worktree:** `/Volumes/T7/Projekte/agora-wt-task-B`

## Aufgabe

Bug-Report: "Wenn ich nach dem Personas-Erstellen noch manuell welche hinzufüge,
werden diese ignoriert." (Issue #210)

## Phase 1 — Verify-First

### Verifizierte Falsthesen

Zwei initiale Hypothesen des Orchestrators wurden widerlegt:

1. **"Frontend schickt nur die generierten Profile beim Start"** — falsch.
   `handleStart()` in `Step2EnvSetup.vue` schickt `{maxRounds, simulationDays, simulationId}`,
   kein Persona-Payload. Das Script `run_parallel_simulation.py` liest
   `reddit_profiles.json` direkt von Disk (Zeile 1516). Kein Payload-Problem.

2. **"prepare_service filtert manuelle Personas heraus"** — falsch.
   `_expand_entities_for_quota()` operiert auf Graph-Entities, nicht auf der
   Profile-Liste. Der "Persona hinzufügen"-Button ist per `v-if="phase >= 2"`
   UI-seitig gesperrt bis `_phase_generate_profiles` bereits abgeschlossen ist.
   Re-Prepare wird durch `_check_simulation_prepared()` verhindert
   (`force_regenerate` ist standardmässig `False`).

### Tatsächliche Ursache (Root Cause)

Schema-Mismatch zwischen generierten und manuellen Profilen:

| Feld | `_save_reddit_json` (generiert) | `add_simulation_profile` (manuell, vor Fix) |
|------|----------------------------------|---------------------------------------------|
| `karma` | `profile.karma or 1000` | **fehlte komplett** |
| `created_at` | `profile.created_at` | **fehlte komplett** |
| `bio` | `profile.bio[:150] or f"{profile.name}"` | `data.get('bio', '')` — leer wenn nicht ausgefüllt |
| `persona` | `profile.persona or f"{name} is a participant..."` | `data.get('persona', '')` — leer wenn nicht ausgefüllt |

OASIS's `generate_reddit_agent_graph` (im Subprozess) erwartet vollständige
Profil-Dicts. Fehlende Pflichtfelder führen zu stillschweigendem Skip oder
Absturz des Agenten-Initialisierers.

### Pfad-Verifikation (kein Path-Mismatch-Bug)

`Config.OASIS_SIMULATION_DATA_DIR`, `ArtifactLocator.simulations_dir()`,
`SimulationRunner.RUN_STATE_DIR` und das Script's `simulation_dir` zeigen
alle auf denselben physischen Pfad `backend/uploads/simulations`.

## Phase 2 — TDD RED

**Test-Datei:** `backend/tests/api/test_simulation_profiles_manual_persistence.py`

Testlauf vor Fix (RED, Auszug):
```
FAILED tests/api/test_simulation_profiles_manual_persistence.py::test_manual_profile_has_karma
AssertionError: Fehlendes Feld: karma
assert 'karma' in {'age': None, 'bio': '', 'country': 'DE', 'gender': 'other', ...}
```

## Phase 3 — GREEN Implementation

### Geänderte Datei

**`backend/app/api/simulation_profiles.py`**

Änderungen in `add_simulation_profile` (Funktion, nicht Vertrag):

1. `from datetime import datetime, timezone` hinzugefügt.
2. `next_id` startet bei `1` statt `0` wenn keine Profile existieren (defensive
   ID-Kollisionsvermeidung, Nebenfix).
3. `bio`-Fallback: `(data.get('bio') or '').strip() or display_name`
4. `persona`-Fallback: `(data.get('persona') or '').strip() or f"{display_name} is a participant in social discussions."`
5. `karma` in `new_profile`: `int(data['karma']) if data.get('karma') is not None else 1000`
6. `created_at` in `new_profile`: User-Wert wenn vorhanden, sonst UTC-ISO-String

### Nicht geändert (Hardstops eingehalten)

- `frontend/src/components/Step2EnvSetup.vue` — kein Eingriff (Hot-Spot F8, Issue #203)
- `backend/app/services/prepare_service.py` — kein Eingriff
- `backend/app/contracts/` — keine Layer-0-Änderungen
- `schemas/` — kein Schema-Drift (`git diff --exit-code schemas/` grün)

### Frontend-Test-Entscheidung

Ein Frontend-Unit-Test für `submitNewPersona` wurde ursprünglich geplant,
dann bewusst gestrichen: Der Vue-Payload ist korrekt (POST mit den Formfeldern),
der Bug lag ausschliesslich in der serverseitigen Persistierung. Ein Test, der
beweist, dass das Frontend `karma`/`created_at` sendet, wäre falsch positiv
(das Frontend soll diese Felder gar nicht senden — das Backend befüllt Defaults).

## Phase 4 — Verifikation

### Testlauf nach Fix (GREEN)

```
7 passed in 1.46s

tests/api/test_simulation_profiles_manual_persistence.py::test_manual_profile_has_karma PASSED
tests/api/test_simulation_profiles_manual_persistence.py::test_manual_profile_has_created_at PASSED
tests/api/test_simulation_profiles_manual_persistence.py::test_manual_profile_bio_nonempty_when_not_provided PASSED
tests/api/test_simulation_profiles_manual_persistence.py::test_manual_profile_persona_nonempty_when_not_provided PASSED
tests/api/test_simulation_profiles_manual_persistence.py::test_manual_profile_user_id_unique_and_nonzero_when_profiles_exist PASSED
tests/api/test_simulation_profiles_manual_persistence.py::test_manual_profile_user_id_starts_at_1_when_no_profiles_exist PASSED
tests/api/test_simulation_profiles_manual_persistence.py::test_provided_bio_and_persona_are_kept PASSED
```

### Full Suite

```
1329 passed, 9 skipped in 10.01s
```
(9 skipped = Redis + Docker-Compose-Skips, environment-bedingt, kein Regression)

### Ruff

`ruff check app/api/simulation_profiles.py tests/api/test_simulation_profiles_manual_persistence.py`
→ All checks passed!

### Mypy

`uv run mypy app` vor und nach dem Fix: identisch 161 errors in 27 files.
Kein neuer Error durch diesen Slice eingeführt. Die pre-existing Errors liegen
in `app/api/runs.py`, `app/api/report.py` und anderen Dateien ausserhalb
des Scope dieses Slices.

### Schemas

`uv run python -m app.contracts.dump_schemas && git diff --exit-code schemas/`
→ SCHEMAS OK - no drift (alle 10 Schema-Dateien unverändert)

## Diff-Summary

| Datei | Typ | +LOC | -LOC |
|-------|-----|------|------|
| `backend/app/api/simulation_profiles.py` | fix | +14 | -5 |
| `backend/tests/api/test_simulation_profiles_manual_persistence.py` | neu | +182 | 0 |
| `docu/2026-05-03-slice-B-arbeitsprotokoll.md` | neu | dieses Dokument | |
| `CHANGELOG.md` | ergänzt | +8 | 0 |
