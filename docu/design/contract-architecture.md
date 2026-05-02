# Design-Doc: Contract-Architektur (Layer 0)

**Status:** Akzeptiert
**Erstellt:** 2026-05
**Bezug:** Issue #107 (Schema-Migration v1→v2), #75 (Confidence-Score), #71 (Frontend-TS-Modelle)

## Problem (Code-verifiziert)

Im echten Source-Code von v0.9.0 finden sich drei strukturelle Drift-Stellen:

| Ort | Beleg (Pfad:Zeile) | Symptom |
|---|---|---|
| Schema-Version inkonsistent | `backend/app/services/report_agent.py:184/567/1127` | Init `2`, später `1` zurückgezogen |
| Export-Pin auf v1 | `backend/app/api/report.py:379` | `EXPORT_SCHEMA_VERSION = 1` |
| Dataclasses statt Pydantic | `backend/app/models/report.py` | Reine `@dataclass`, keine Validierung |
| JSON-Mode statt Schema-Mode | `backend/app/utils/llm_client.py:274` | `response_format={"type": "json_object"}` |
| Toleranter Frontend-Renderer | `frontend/src/components/Step4Report.vue:323-324` | Fallback-Logik kaschiert Drift |
| Dekorative Evidence | `backend/app/services/report_agent.py:524` | `bound = deepcopy(global_items[:2])` |

## Optionen

| Option | Vorteil | Nachteil | Empfehlung |
|---|---|---|---|
| Status quo (Tests-only-Schemas) | Wenig Umbau | Drift bleibt | Nein |
| Nur Zod-Frontend | Gute UI-Sicherheit | Backend bleibt weich | Nein |
| Nur Pydantic-Backend | Starke Runtime-Validation | Frontend driftet | Teilweise |
| **Pydantic + JSON Schema 2020-12 + Zod-Spiegel** | Eine Quelle, alle Spiegel | Tooling-Aufwand klein | **Ja** |

## Architektur

```
backend/app/contracts/*.py  ← Pydantic v2 (BaseModel, extra=forbid)
   |
   |- model_json_schema() --→ schemas/*.schema.json (auto)
   |                             |- Zod-Spiegel: frontend/src/contracts/*.ts
   |                             '- chat_json strict response_format
   '- Flask-Routes: model_validate() bei Eingang, model_dump_json() beim Export
```

Ein Modell, drei Spiegel. Kein Drift mehr möglich, weil CI über
`git diff --exit-code schemas/` jede inkonsistente Änderung blockt.

## Versionsregel

`schema_version: Literal[2] = 2` — Pydantic kann nicht auf `1`
zurückfallen, weil Literal-Constraint es im Validator ablehnt. Damit ist
der report_agent.py:567/1127-Bug strukturell unmöglich, sobald die
Modelle benutzt werden.

## Migration v1 → v2 (hängt an Issue #107)

```python
def migrate_v1_to_v2(raw: dict) -> dict:
    """Liest alte v1-Reports, hebt auf v2 ohne Datenverlust."""
    if raw.get("schema_version", 1) == 2:
        return raw  # idempotent
    raw["schema_version"] = 2
    # weitere Mapping-Schritte je nach v1-Form
    return raw
```

Round-Trip-Test gegen 10 echte v1-Reports aus Backup.

## CI-Gates (siehe `.github/workflows/contract-gates.yml`)

1. **schema-drift:** Pydantic-Modelle → `dump_schemas` → `git diff schemas/` muss leer sein.
2. **contract-tests:** `pytest tests/contracts/` grün.
3. **evidence-quality:** `check_evidence_quality.py` Soft-Schwellen, später hart.
4. **zod-mirror-drift:** Frontend-Vitest parst Sample-Payload aus Backend strikt.

## Rückwirkungen auf bestehende Issues

| Issue | Status | Begründung |
|---|---|---|
| #107 Schema-Migration v1→v2 | wird Sub-Issue dieses Designs | Layer 0 erzwingt v2, Migration löst Altlasten |
| #75 EPIC-15-ST-02 Confidence-Score | erweitern | `ReportClaimModel`-Validator implementiert Großteil |
| #71 EPIC-14-ST-01 Frontend-TS-Modelle | hinfällig durch Zod-Spiegel | Zod liefert TS-Types via `z.infer` |
| #105 Contradiction-Detector | erweitern | Penalty als `model_validator` einhängen |

## Risiken

- **Strict-Schema-Mode bei Ollama-Cloud nicht universal supported.** Fallback:
  `chat_json(..., schema_class)` versucht strict, fällt nach Detection auf
  `json_object` plus lokale Pydantic-Validation. Loggt Warnung.
- **Pydantic-v2-Performance für große Reports.** Geringer Risiko —
  `extra="forbid"` ist schnell, Cython-Kern.
- **Migration-Aufwand bestehender Tests.** Vorgehen: Tests gegen Pydantic-Modelle
  umschreiben statt gegen Dicts. Sollte die Tests robuster machen, nicht fragiler.

## Entscheidung

Wird umgesetzt. Reihenfolge: 17 Tasks in 6 Layern, siehe `docu/design/refactor-roadmap.md`.
