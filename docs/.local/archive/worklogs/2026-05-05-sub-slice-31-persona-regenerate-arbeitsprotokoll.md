# Sub-Slice 31 — Persona Regenerate-Endpoint Backend

**Datum:** 2026-05-05
**Branch:** `feat/layer-8-task-30-persona-regenerate`
**Refs:** #70 (EPIC-13-ST-03 Approve/Reject/Regenerate)
**Status:** Implementiert, Tests gruen

---

## Was wurde gemacht

Backend-Ergaenzung um den dritten Zweig der Persona-Review-State-Machine: `regenerating`.

### Geaenderte Dateien

1. `backend/app/services/persona_review_service.py`
   - Neue Konstante `REVIEW_STATUS_REGENERATING = "regenerating"` und Export in `__all__`
   - `_VALID_STATUSES` um `"regenerating"` erweitert
   - Neue Hilfsmenge `_BLOCKING_STATUSES` (dokumentiert, nicht direkt im Code genutzt)
   - Neue Service-Methode `regenerate(simulation_id, username, *, requested_by, notes)`
   - Neuer statischer Mutator `_apply_regenerate` (analog zu `_apply_status`)
   - `evaluate_start_gate` liefert jetzt auch `regenerating`-Liste; blockt die Sim-Start-Gate solange `regenerating`-Personas vorhanden
   - `_with_review_defaults` setzt `review_requested_by` als Defaults-Feld

2. `backend/app/api/simulation_profiles.py`
   - Neue Route `POST /<simulation_id>/profiles/<username>/regenerate`
   - Nutzt denselben `_handle_review_action`-Helper wie `approve` und `reject`
   - Akzeptiert `notes`, `reason` (Alias) und `requested_by` aus dem Request-Body

### State-Machine-Diagramm

```
pending ──────────────────────┐
   ↑                          ↓
   │            approved ──→ regenerating
   │            rejected ──→ regenerating
   │          regenerating ──→ regenerating  (idempotent)
   │
   └──── (nach Re-Generierung durch Generator-Pipeline)
```

Erlaubte Vorgaenger-Stati fuer `regenerate`: `pending`, `approved`, `rejected`, `regenerating`.
Die Methode wirft nie `InvalidReviewStatusError` — alle bestehenden Stati sind erlaubt.

### Was NICHT gemacht wurde (bewusst)

- Kein Trigger der tatsaechlichen Neugenerierung — dieser Endpoint setzt nur den Status.
  Die Generierungslogik bleibt im bestehenden Generator-Pfad (Sim-Reset oder Operator-Aktion).
- Kein Frontend-Wiring — kommt in Folgeslices.
- Keine Pydantic-Contract-Aenderungen — Layer 0 bleibt stabil.

---

## Neue Tests

### `backend/tests/test_persona_review_service.py` (9 neue Faelle)

- `test_regenerate_from_pending_sets_regenerating` — Status-Transition von `pending`
- `test_regenerate_from_approved_sets_regenerating` — Status-Transition von `approved`
- `test_regenerate_from_rejected_sets_regenerating` — Status-Transition von `rejected`
- `test_regenerate_from_regenerating_is_idempotent` — Re-Request ist erlaubt
- `test_regenerate_unknown_username_raises_not_found` — `PersonaNotFoundError`
- `test_regenerate_sets_notes_and_requested_by` — Audit-Felder gesetzt
- `test_start_gate_blocks_when_any_persona_regenerating` — Gate blockt
- `test_start_gate_allows_when_no_regenerating_pending_rejected` — Gate frei

### `backend/tests/test_simulation_api_routes.py` (4 neue Faelle)

- `test_regenerate_returns_regenerating_status` — 200 + `review_status: "regenerating"`
- `test_regenerate_with_notes_sets_review_notes` — Notes-Wiring
- `test_regenerate_unknown_username_returns_404` — 404 fuer unbekannten Username
- `test_regenerate_invalid_simulation_id_returns_400` — 400 fuer invalides Format

---

## Test-Output-Snippet

```
tests/test_persona_review_service.py::test_regenerate_from_pending_sets_regenerating PASSED
tests/test_persona_review_service.py::test_regenerate_from_approved_sets_regenerating PASSED
tests/test_persona_review_service.py::test_regenerate_from_rejected_sets_regenerating PASSED
tests/test_persona_review_service.py::test_regenerate_from_regenerating_is_idempotent PASSED
tests/test_persona_review_service.py::test_regenerate_unknown_username_raises_not_found PASSED
tests/test_persona_review_service.py::test_regenerate_sets_notes_and_requested_by PASSED
tests/test_persona_review_service.py::test_start_gate_blocks_when_any_persona_regenerating PASSED
tests/test_persona_review_service.py::test_start_gate_allows_when_no_regenerating_pending_rejected PASSED
tests/test_simulation_api_routes.py::test_regenerate_returns_regenerating_status PASSED
tests/test_simulation_api_routes.py::test_regenerate_with_notes_sets_review_notes PASSED
tests/test_simulation_api_routes.py::test_regenerate_unknown_username_returns_404 PASSED
tests/test_simulation_api_routes.py::test_regenerate_invalid_simulation_id_returns_400 PASSED

1541 passed, 9 skipped in 92.57s
```

---

## Verifikation

| Pruefpunkt | Ergebnis |
|---|---|
| `pytest tests/test_persona_review_service.py tests/test_simulation_api_routes.py -v` | 51/51 passed |
| `pytest -x -q` (komplett) | 1541 passed, 9 skipped |
| `ruff check app/ tests/` | All checks passed |
| `mypy app` | Keine neuen Fehler in geaenderten Dateien (163 vorbestehende Fehler in anderen Dateien) |
| `python -m app.contracts.dump_schemas` + `git diff schemas/` | schemas clean |

---

## Folgeslices

- Frontend-Wiring: Regenerate-Button in der Persona-Review-UI (Folgeslice #70)
- Tatsaechliche Generator-Triggerlogik (setzt `regenerating` -> `pending` nach Abschluss)
