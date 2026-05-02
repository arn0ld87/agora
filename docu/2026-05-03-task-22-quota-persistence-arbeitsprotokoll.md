# Sub-Slice 22 — PersonaQuotaPlan-Persistenz + Gemini-Followup

**Datum:** 2026-05-03
**Branch:** `feat/task-22-quota-persistence`
**Layer:** 1 (Service-Boundary) + Hygiene
**Refs:** Followup auf Sub-Slice 20a / [PR #181](https://github.com/arn0ld87/agora/pull/181)
— Gemini-Code-Review hatte drei Findings.

## Findings (Gemini auf PR #181)

| Schwere | Ort | Befund |
|---|---|---|
| HIGH | [`backend/app/api/runs.py:382`](backend/app/api/runs.py:382) | `quota_plan` wurde im Restart-Pfad aus `simulation_config.json` gelesen, aber nirgends gespeichert — Restart bekam immer `None`, Plan-Drift ohne Warnung |
| MEDIUM | [`backend/app/api/simulation_prepare.py:240`](backend/app/api/simulation_prepare.py:240) | `except Exception` maskierte echte 500er als 400 |
| MEDIUM | [`backend/app/api/simulation_prepare.py:7`](backend/app/api/simulation_prepare.py:7) | `pydantic.ValidationError`-Import fehlte |

## Fix

### 1. Persistenz im `_phase_generate_config`

[`backend/app/services/prepare_service.py`](backend/app/services/prepare_service.py)
`_phase_generate_config(...)` bekommt einen optionalen
`quota_plan: PersonaQuotaPlan = None`-kwarg. Wenn gesetzt, wird er als
Top-Level-Key `quota_plan` ins persistierte `simulation_config.json`
geschrieben (`config_payload["quota_plan"] = quota_plan.model_dump()`).
`prepare_simulation` reicht den Plan an Phase 3 durch.

Damit liest der Restart-Pfad in
[`backend/app/api/runs.py`](backend/app/api/runs.py) (`config = manager.get_simulation_config(...)`)
den Plan über `_parse_quota_plan(config)` korrekt wieder ein. Der
Helper akzeptierte bereits `dict`-Payload via `model_validate` —
Roundtrip ohne Schema-Drift.

### 2. Spezifisches Exception-Handling

```python
# vorher
try:
    quota_plan = _parse_quota_plan(data)
except Exception as exc:
    return json_error(...)

# nachher
try:
    quota_plan = _parse_quota_plan(data)
except (ValidationError, ValueError, TypeError) as exc:
    return json_error(...)
```

Andere unerwartete Fehler (DB-Glitch, OOM, Disk-Full im Pydantic-Stack)
propagieren jetzt korrekt als 500 statt als 400 mit irreführender
„Invalid quota_plan"-Message.

### 3. ValidationError-Import

`from pydantic import ValidationError` zu den Top-Level-Imports.

## Tests

Neu: [`backend/tests/test_quota_persistence.py`](backend/tests/test_quota_persistence.py)
— 5 Cases:

| Case | Erwartung |
|---|---|
| `_phase_generate_config(quota_plan=plan)` | `simulation_config["quota_plan"]` enthält `model_dump()` |
| `_phase_generate_config(quota_plan=None)` | kein `quota_plan`-Key (Backwards-Compat) |
| Roundtrip Persisted-Dict → `_parse_quota_plan` | sauber als `PersonaQuotaPlan` zurück |
| `_parse_quota_plan` → `ValidationError` (total mismatch) | spezifischer Exception-Typ verfügbar |
| `_parse_quota_plan` → `ValidationError` (non-dict) | dito |

## Verifikation

```
$ uv run pytest tests/test_quota_persistence.py \
                tests/api/test_simulation_prepare_quota.py \
                tests/services/test_persona_quota_wiring.py -x -q
29 passed in 0.81s

$ uv run pytest -x -q
1276 passed, 2 skipped in 52.05s

$ uv run ruff check app/ tests/
All checks passed!

$ uv run python -m app.contracts.dump_schemas && git diff --stat schemas/
✓ alle Schemas
(kein Drift)
```

## Out of Scope (Sub-Slice 20b)

- **Generator-Erzwingung** ist weiterhin offen. Bei 16 Entitäten +
  `quota_plan.total=50` failt der Run weiterhin im post-generation
  `_validate_persona_quota`. 22 fixt nur die Persistenz-Lücke; das
  Auffüllen kommt in 20b.

## Geänderte Dateien

- `backend/app/services/prepare_service.py` — `_phase_generate_config`
  kwarg + Persist-Patch + Pass-Through aus `prepare_simulation`
- `backend/app/api/simulation_prepare.py` — `ValidationError`-Import +
  spezifisches Exception-Handling
- `backend/tests/test_quota_persistence.py` (neu)
- `CHANGELOG.md` — `[Unreleased]` / Fixed-Block
