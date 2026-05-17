# Sub-Slice 20b — PersonaQuotaPlan Generator-Erzwingung

**Datum:** 2026-05-03
**Branch:** `feat/task-20b-quota-generator`
**Layer:** 1 (Service-Pipeline)
**Refs:** Folge zu Sub-Slices 06 (Plan-Datenstruktur), 20a (API-Boundary),
22 (Persistenz). Vollendet die Quoten-Pipeline serverseitig; 20c (Frontend)
folgt.

## Symptom

Nach 20a + 22 konnte ein Caller einen `PersonaQuotaPlan` über die API
setzen — der wurde sauber persistiert und beim Restart wieder gelesen.
Aber der Generator selbst respektierte den Plan nicht: bei 16 Entitäten
+ `quota_plan.total = 50` lief Phase 2 weiter „1 Persona pro Entity" und
produzierte 16 Profile. Der nachgelagerte `_validate_persona_quota`-Check
(Sub-Slice 06) failte mit `ValidationError("Soll=50, Ist=16")` und der
gesamte Run ging in `FAILED` — sauberer Drift-Marker, aber kein Fix.

Praktische Konsequenz: Alex' Wahrnehmungsanalyse-Prompt mit 10 Segmenten
und 54 Personas konnte nicht laufen, weil die Ontology nur 16 Entity-Types
liefert (siehe [`ONTOLOGY_MAX_ENTITY_TYPES = 16`](backend/app/services/settings_schema.py:115)).

## Fix

Neuer Helper [`_expand_entities_for_quota`](backend/app/services/prepare_service.py)
erweitert den Entity-Pool **vor** der Generation auf den Soll-Plan:

```python
def _expand_entities_for_quota(entities, plan):
    if plan is None:
        return entities  # Backwards-Compat

    by_segment = {}
    for e in entities:
        seg = e.get_entity_type() or "Entity"
        by_segment.setdefault(seg, []).append(e)

    expanded = []
    for segment, target in plan.targets.items():
        pool = by_segment.get(segment, [])
        if not pool:
            raise ValueError(
                f"PersonaQuotaPlan verlangt {target} Personas im Segment "
                f"'{segment}', aber der Entity-Pool enthält keine Entity "
                f"mit entity_type='{segment}'. Verfügbare Segmente: "
                f"{sorted(by_segment.keys()) or '(leer)'}. ..."
            )
        for i in range(target):
            expanded.append(pool[i % len(pool)])
    return expanded
```

### Strategie-Entscheidungen

- **Round-Robin statt Synth-Entities.** Bei zu kleinem Segment-Pool wird
  derselbe `EntityNode` mehrfach verwendet — jeder Generator-Aufruf
  bekommt einen eigenen `user_id` (per `enumerate`-Index in der Generator-
  Loop), der LLM erzeugt unterschiedliche Personas. Bestehende
  Display-Name-/User-Name-Dedup-Logik im Generator
  ([`oasis_profile_generator.py` Z. 1269+](backend/app/services/oasis_profile_generator.py))
  fängt LLM-Name-Kollisionen ab.

  Synth-Entities ohne KG-Verankerung wären die Alternative, wären aber
  semantisch dünner — keine `summary`, keine Edges, kein Embedding —
  und würden den Generator-Fallback-Pfad in `OasisAgentProfile` triggern.

- **Hartes Fail bei fehlendem Segment.** Wenn der Plan ein Segment
  vorschreibt, das die Ontology nicht liefert, propagiert der
  `ValueError` mit Liste der verfügbaren Segmente. Kein heimliches
  Reduzieren des Plans. Zwei Wege für den User: Plan an Ontology
  anpassen, oder Ontology um den fehlenden `entity_type` erweitern.

- **Pool-Segmente ohne Plan-Eintrag werden gedroppt.** Wenn der Plan
  nur `kmu` will, der Pool aber zusätzlich `extra` enthält, fliegt
  `extra` raus. Plan ist Source of Truth.

### Wiring

`_phase_generate_profiles(...)` bekommt
`quota_plan: Optional[PersonaQuotaPlan] = None`-kwarg, ruft den
Expander direkt vor `generator.generate_profiles_from_entities(...)`
auf. `prepare_simulation` reicht den Plan an Phase 2 durch. Die
`_validate_persona_quota`-Check nach Phase 2 (Sub-Slice 06) läuft
weiter — sollte aber jetzt immer durchgehen, weil der Pool exakt auf
die Quote expandiert wurde.

## Tests

Neu: [`backend/tests/test_quota_generator_expansion.py`](backend/tests/test_quota_generator_expansion.py)
— 7 Cases:

| Case | Erwartung |
|---|---|
| Pool > Quota (4 KMU, Quote 2) | erste 2 |
| Pool < Quota (2 KMU, Quote 5) | Round-Robin: e0, e1, e0, e1, e0 |
| Plan-Segment fehlt im Pool | `ValueError` mit Segment-Liste |
| Mehrere Segmente unabhängig | jedes Segment auf eigene Quote |
| Pool hat extra Segment, Plan nicht | extra-Entities gedroppt |
| `plan=None` | Pool unverändert (Backwards-Compat) |
| Plan-Segment ohne Pool-Match | `ValueError` |

## Verifikation

```
$ uv run pytest tests/test_quota_generator_expansion.py \
                tests/test_quota_persistence.py \
                tests/api/test_simulation_prepare_quota.py \
                tests/services/test_persona_quota_wiring.py \
                tests/contracts/test_persona_quota.py -x -q
52 passed in 2.52s

$ uv run pytest -x -q
1283 passed, 2 skipped in 73.34s

$ uv run ruff check app/ tests/
All checks passed!

$ uv run python -m app.contracts.dump_schemas && git diff --stat schemas/
✓ alle Schemas
(kein Drift)
```

End-to-End-Verifikation ist nutzerseitig: mit dem Wahrnehmungsanalyse-Prompt
(50 + 4 Personas in 10 Segmenten) und entsprechend hohem
`ONTOLOGY_MAX_ENTITY_TYPES` sollte die Sim 54 Personas erzeugen, wenn die
Ontology die 10 Segment-Types liefert.

## Out of Scope (Sub-Slice 20c)

- **Frontend-Quoten-Editor in Step 2** — UI fehlt, User muss Plan
  weiterhin per `quota_plan`-JSON-Body im API-Call setzen oder über
  ein Dev-Tool wie Postman / `curl`.
- **Plan-Vorschlag aus Prompt parsen** — nice-to-have für 20c oder später.

## Geänderte Dateien

- `backend/app/services/prepare_service.py` — `_expand_entities_for_quota`
  Helper + `_phase_generate_profiles`-kwarg + `prepare_simulation` Pass-Through
- `backend/tests/test_quota_generator_expansion.py` (neu)
- `CHANGELOG.md` — `[Unreleased]` / Added-Block
