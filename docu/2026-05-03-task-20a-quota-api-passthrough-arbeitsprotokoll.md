# Sub-Slice 20a — PersonaQuotaPlan API-Pass-Through

**Datum:** 2026-05-03
**Branch:** `feat/task-20a-quota-api`
**Layer:** 1 (API-Boundary)
**Refs:** Folge zu Sub-Slice 06 (Plan-Datenstruktur), führt zu 20b (Generator-Erzwingung), 20c (Frontend).

## Symptom

Die Persona-Generation extrahiert „1 Profil pro Entity" aus dem Knowledge-Graph.
Der HTTP-`POST /api/simulations/<id>/prepare`-Body kennt zwar bereits
`max_agents` (Cap), aber **keinen `quota_plan`** — User-seitig führt das
zu „erwarte 50 Personas, bekomme 16", weil
[`ONTOLOGY_MAX_ENTITY_TYPES = 16`](backend/app/services/settings_schema.py:115)
die Ontology-Stage cappt und der Cap-Modus auf der Persona-Stage nichts
auffüllen kann.

## Root Cause

Die Plan-Datenstruktur `PersonaQuotaPlan` existiert seit Sub-Slice 06
([`backend/app/contracts/persona_contract.py:67`](backend/app/contracts/persona_contract.py:67))
und der Service-Layer akzeptiert sie bereits über
[`prepare_simulation(..., quota_plan=…)`](backend/app/services/prepare_service.py:317).
Validiert wird sie nach der Generation
([`_validate_persona_quota`](backend/app/services/prepare_service.py:279)),
also als Drift-Detektor. **Was fehlte: API-Boundary.** Weder
`simulation_prepare.py` noch `runs.py` haben den Body-Key gelesen oder
durchgereicht — der gesamte Service-Layer-Pfad war für externe Caller
unerreichbar.

## Fix (eine Datei API + Manager-Signatur erweitert)

### 1. [`backend/app/api/simulation_prepare.py`](backend/app/api/simulation_prepare.py)

Neuer Helper `_parse_quota_plan(data) -> Optional[PersonaQuotaPlan]`:

- `data["quota_plan"]` fehlt oder ist `None` → `None` (Backwards-Compat).
- `data["quota_plan"] == {}` → `None` (Frontend kann den Eintrag mit `{}`
  defaulten ohne 400; ein leerer Plan hat keine Aussagekraft).
- Strukturell vorhandener, aber inkonsistenter Plan
  (`total != sum(targets)`, `count<1`, nicht-Dict) → `pydantic.ValidationError`
  propagiert; der Caller übersetzt das in HTTP 400 mit
  `ApiErrorCode.VALIDATION_FAILED` und der Pydantic-Error-Message als
  `message`.

Im View-Handler `prepare_simulation_view` wird `quota_plan` direkt nach
dem `max_agents`-Parsing gelesen und an `manager.prepare_simulation(...)`
durchgereicht.

### 2. [`backend/app/services/simulation_manager.py`](backend/app/services/simulation_manager.py)

`SimulationManager.prepare_simulation` bekommt
`quota_plan: Optional[PersonaQuotaPlan] = None` und reicht es an den
Service. Import via `TYPE_CHECKING`-Block, damit es zur Runtime keinen
Circular-Import gibt.

### 3. [`backend/app/api/runs.py`](backend/app/api/runs.py)

Restart-Pfad (`run_prepare()`) liest `quota_plan` über denselben
Helper aus dem persistierten Run-Config-Snapshot. Bewusste Entscheidung:
**kein Silent-Fallback auf „ohne Plan"**, wenn der persistierte Snapshot
inkonsistent ist — die ValidationError propagiert in den Restart und
markiert ihn als `FAILED`. Sonst würde ein Restart einen Plan stillschweigend
ignorieren, der ursprünglich beim Prepare gesetzt war.

## Tests

Neu: [`backend/tests/api/test_simulation_prepare_quota.py`](backend/tests/api/test_simulation_prepare_quota.py)
— 9 Cases:

| Case | Erwartung |
|---|---|
| `_parse_quota_plan({})` | `None` |
| `_parse_quota_plan({"quota_plan": None})` | `None` |
| `_parse_quota_plan({"quota_plan": {}})` | `None` (leerer Plan = nicht gesetzt) |
| `_parse_quota_plan({"quota_plan": valid})` | `PersonaQuotaPlan`-Instanz |
| `total != sum(targets)` | `ValidationError` |
| `targets[x] = 0` (min ge=1) | `ValidationError` |
| `quota_plan = "string"` | `ValidationError` |
| `manager.prepare_simulation(quota_plan=plan)` | wird durchgereicht |
| `manager.prepare_simulation()` ohne quota_plan | Service kriegt `None` |

## Verifikation

```
$ uv run pytest tests/api/test_simulation_prepare_quota.py -x -q
9 passed in 1.15s

$ uv run pytest tests/api/test_simulation_prepare_quota.py \
                tests/services/test_persona_quota_wiring.py \
                tests/contracts/test_persona_quota.py -x -q
40 passed in 1.43s

$ uv run ruff check app/ tests/
All checks passed!

$ uv run pytest -x -q
1267 passed, 2 skipped in 70.61s

$ uv run python -m app.contracts.dump_schemas
✓ schemas/persona-quota-plan.schema.json   (kein Drift gegen main)
$ git diff --stat schemas/
(leer)
```

## Was 20a NICHT tut

- **Keine Generator-Erzwingung.** Wenn `quota_plan.total = 50` aber nur
  16 Entitäten im Graph sind, läuft Phase 2 weiterhin „1 Persona pro
  Entity" und produziert 16 Profile; dann schlägt
  `_validate_persona_quota` mit `ValidationError("Soll=50, Ist=16")`
  zu, der gesamte Run failt mit FSM-Status `FAILED`. Das ist
  **gewollt** als sauberer Drift-Marker, aber kein Fix. Generator-Modus
  „Auffüllen bis Soll-Quote" ist Sub-Slice 20b.
- **Kein Frontend.** Quoten-Eingabe in Step 2 + LocalStorage-Persistenz
  ist Sub-Slice 20c.

## Geänderte Dateien

- `backend/app/api/simulation_prepare.py` — `_parse_quota_plan` Helper +
  View-Pass-Through
- `backend/app/api/runs.py` — Restart-Pfad reicht persistierten Plan durch
- `backend/app/services/simulation_manager.py` — `quota_plan`-kwarg
- `backend/tests/api/test_simulation_prepare_quota.py` (neu)
- `CHANGELOG.md` — `[Unreleased]` / Added-Block
