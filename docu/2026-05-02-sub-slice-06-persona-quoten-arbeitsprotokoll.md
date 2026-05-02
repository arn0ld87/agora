# Sub-Slice 06 — PersonaQuotaPlan-Verdrahtung: Arbeitsprotokoll

Datum: 2026-05-02
Layer: 1 (Backend-Hardening)
Refs: Issue #107, EPIC-Layer-1

## Was geändert

### `backend/app/services/oasis_profile_generator.py`

- **Zeile 56–58**: `OasisAgentProfile`-Dataclass erhält neues Feld `segment: Optional[str] = None`.
- **Zeile 88–89**: `to_reddit_format()` gibt `segment` aus (wie `source_entity_type`, nur wenn nicht None).
- **Zeile 124–125**: `to_twitter_format()` analog.
- **Zeile 149**: `to_dict()` enthält `segment` immer (auch als `None`), konsistent mit übrigen Feldern.
- **Zeile 308–313**: `generate_profile_from_entity()` setzt `segment = entity_type if entity_type != "Entity" else None` und übergibt es an `OasisAgentProfile(...)`. `entity_type` ist bereits als `entity.get_entity_type() or "Entity"` aufgelöst — kein neues Mapping nötig.

### `backend/app/services/prepare_service.py`

- **Zeile 26–27**: Neue Imports `Dict` (typing), `PersonaQuotaActual`, `PersonaQuotaPlan` aus `app.contracts`, `OasisAgentProfile` aus `.oasis_profile_generator`.
- **Zeile 276–298**: Neue Hilfsfunktion `_validate_persona_quota(plan, profiles) -> None`. Zählt Segment-Counts aus Profilliste, ruft `PersonaQuotaActual.model_validate(...)` mit `tolerance=0` auf. `ValidationError` propagiert unverändert.
- **Zeile 314**: `prepare_simulation`-Signatur erhält `quota_plan: Optional[PersonaQuotaPlan] = None` (Keyword-only, Default `None` — alle bestehenden Aufrufer unverändert).
- **Zeile 349**: `_phase_generate_profiles(...)` Rückgabewert wird in `profiles` gefangen (vorher verworfen).
- **Zeile 361–362**: Guard `if quota_plan is not None: _validate_persona_quota(quota_plan, profiles)` nach Phase 2.
- **`__all__`**: `_validate_persona_quota` ergänzt.

## Warum (Layer 1)

Persona-Erzeugung war bisher nicht an einen Soll-Plan gebunden (ChatGPT-Audit-Befund).
Ohne Constraint konnte `generate_profiles_from_entities` beliebig viele Personas eines
Segments produzieren. Mit `quota_plan` wird nach Phase 2 geprüft, ob die Ist-Verteilung
dem Plan entspricht — Toleranz 0, keine unbekannten Segmente. `ValidationError` propagiert
in `prepare_simulation`'s `except`-Block, setzt `state.error` und FSM → `FAILED`.
Backwards-Compat: ohne `quota_plan=...` ändert sich nichts.

## Tests

Neue Datei: `backend/tests/services/test_persona_quota_wiring.py`

15 Tests, alle grün:

```
tests/services/test_persona_quota_wiring.py::TestSegmentFieldOnProfile::test_segment_defaults_to_none PASSED
tests/services/test_persona_quota_wiring.py::TestSegmentFieldOnProfile::test_segment_set_explicitly PASSED
tests/services/test_persona_quota_wiring.py::TestSegmentFieldOnProfile::test_to_dict_includes_segment PASSED
tests/services/test_persona_quota_wiring.py::TestSegmentFieldOnProfile::test_to_dict_segment_none_when_not_set PASSED
tests/services/test_persona_quota_wiring.py::TestSegmentFieldOnProfile::test_to_reddit_format_includes_segment PASSED
tests/services/test_persona_quota_wiring.py::TestSegmentFieldOnProfile::test_to_reddit_format_omits_segment_when_none PASSED
tests/services/test_persona_quota_wiring.py::TestSegmentFieldOnProfile::test_to_twitter_format_includes_segment PASSED
tests/services/test_persona_quota_wiring.py::TestSegmentFieldOnProfile::test_to_twitter_format_omits_segment_when_none PASSED
tests/services/test_persona_quota_wiring.py::test_validate_quota_actual_matches PASSED
tests/services/test_persona_quota_wiring.py::test_validate_quota_drift_raises PASSED
tests/services/test_persona_quota_wiring.py::test_validate_quota_missing_segment_raises PASSED
tests/services/test_persona_quota_wiring.py::test_validate_quota_unknown_segment_raises PASSED
tests/services/test_persona_quota_wiring.py::test_validate_quota_not_called_when_plan_is_none PASSED
tests/services/test_persona_quota_wiring.py::test_segment_field_propagates_through_generator PASSED
tests/services/test_persona_quota_wiring.py::test_segment_is_none_for_generic_entity_type PASSED

15 passed in 0.82s
```

Volltest: `944 passed, 2 skipped` (Redis-Integration-Skips, erwartet).

## Verbleibende Lücken

- Kein Issue-Ref vorhanden — `quota_plan`-Eingabe im Frontend (Step3-Prepare-Formular) ist separater Slice (Layer 4).
- Keine Migration alter Profile-JSONs: `segment=null` ist backward-kompatibel, da Optional.
- Tolerance ist hardcoded auf 0 in `_validate_persona_quota`; falls konfigurierbar gewünscht, separates Ticket.
