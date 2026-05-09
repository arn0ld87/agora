# M11.8d Arbeitsprotokoll — chat_json strict-schema-Mode in report_agent

**Datum:** 2026-05-09
**Branch:** feat/m11-8d-chat-json-strict-schema
**Worktree:** /Volumes/T7/Projekte/agora-worktrees/m11-8d

---

## Ausgangslage

- `llm_client.py::chat_json` unterstützt seit M11.8c bereits strict `response_format={"type":"json_schema", ...}` per `schema=`-Argument, mit Fallback auf `json_object` bei nicht-strict-fähigen Providern.
- ReportV3 + 11 Pflichtabschnitt-DTOs (`Persona`, `Segment`, `Claim`, `Multiplier`, `FrictionPoint`, `TrustSignal`, `ChangeRecommendation`, `ProjectImpact`, `PositioningVariant`, `ContentIdea`, `DataGap`) leben in `backend/app/contracts/report_v3.py`, re-exportiert via `schemas.py`.
- `planning.py:47` rief `chat_json` **ohne** `schema=` auf → json_object-Mode, kein Forced-Output.
- `workflow.py` hatte **keinen** `chat_json`-Aufruf — nur freie `chat()`-ReACT-Loops.

---

## Edits

### 1. `backend/app/services/report_agent/schemas.py` (komplett umgeschrieben)

- **PlanSection** (Zeilen ~29–38): Pydantic-Modell mit `title`, `description=„—"`, `extra="forbid"`.
- **PlanResponse** (Zeilen ~40–60): Pydantic-Modell mit `title`, `summary`, `sections: list[PlanSection]`, `extra="forbid"`. Docstring erklärt strict-json_schema-Pfad + Fallback-Verhalten.
- **SectionKeyTakeaway** (Zeilen ~65–74): Einzel-Takeaway mit `statement`, `confidence`.
- **SectionMetadata** (Zeilen ~76–90): Allgemeines Metadaten-DTO für Fallback-Fälle, `extra="forbid"`.
- **`_SECTION_KEYWORD_MAP`** (Zeilen ~100–135): 28 Schlüsselwort-Einträge (DE + EN) → je ReportV3-DTO.
- **`_section_schema_for()`** (Zeilen ~138–158): Mapper-Funktion; case-insensitiv; Fallback → `SectionMetadata`.
- **`__all__`** erweitert um alle neuen Symbole.

### 2. `backend/app/services/report_agent/planning.py`

- **Import** (Zeile 14): `from .schemas import PlanResponse` hinzugefügt.
- **`chat_json`-Aufruf** (Zeilen 52–59): `schema=PlanResponse, schema_name="report_plan"` ergänzt. Kommentar erklärt M11.8d-Semantik.
- Response-Parsing unverändert (robustes `.get()`-Parsing bleibt, da `chat_json` bei Validierungsfehler werfen kann und dann in den Fallback geht).

### 3. `backend/app/services/report_agent/workflow.py`

- **Imports** (Zeilen 12–17): `SectionMetadata` und `_section_schema_for` aus `schemas` importiert.
- **`generate_section_metadata()`** (Zeilen 253–312, neu): 
  - Wählt DTO via `_section_schema_for(section_title)`.
  - Ruft `chat_json(schema=schema_cls, schema_name=..., context="report")` auf.
  - Fehler → leeres `{}` zurückgegeben (Hauptgenerierung nicht blockiert).
- **`generate_report()`**: Nach jedem `generate_section_react()` wird `generate_section_metadata()` aufgerufen. Ergebnis wird an `report_logger.log_section_metadata()` weitergegeben (mit `hasattr`-Guard, da Methode optional ist).
- **`__all__`**: `generate_section_metadata` ergänzt.

---

## Neue Dateien

- `backend/tests/services/test_report_agent_strict_schema.py` — 34 Tests in 5 Klassen:
  - `TestPlanResponse`: Struktur, extra-forbid, Default-Description, JSON-Schema-Output.
  - `TestPlanOutlineStrictSchema`: schema=PlanResponse im chat_json-Call, korrekte Verarbeitung, Fallback-Stabilität.
  - `TestSectionSchemaFor`: 19 parametrisierte Titel-DTO-Mappings, Fallback, Case-Insensitivität.
  - `TestGenerateSectionMetadata`: schema= für bekannte/unbekannte Titel, Fehler → `{}`, context='report'.
  - `TestNoJsonObjectInReportAgent`: Regressions-Guard gegen `"json_object"`-Literal in planning/workflow.

---

## Test-Results

```
1656 passed, 9 skipped, 7 deselected, 3 warnings
(davon 34 neue Tests in test_report_agent_strict_schema.py)
```

---

## Akzeptanz-Checks

| Check | Status |
|---|---|
| 1. `rg 'chat_json(' ... | grep 'schema='` → 2 Treffer (planning + workflow) | GRÜN |
| 2. `rg '"json_object"' report_agent/` → leer | GRÜN |
| 3. `dump_schemas` + `git diff schemas/` → kein Drift | GRÜN |
| 4. `pytest -x -q` → 1656 passed | GRÜN |
| 5. `pytest tests/contracts/ -x -v` → 88 passed | GRÜN |
| 6. `ruff check app/ tests/` → 0 Errors; `mypy app` → clean | GRÜN |

Alle 6 Checks grün.

---

## Offene Followups

- `report_logger.log_section_metadata()` existiert noch nicht in `report_logger.py` — Methode ist optional (hasattr-Guard). Kann in M11.8e oder späterem Slice ergänzt werden, wenn Provenance-Tracking der Metadaten gewünscht wird.
- `_section_schema_for()` ist keyword-basiert und kann bei ambigen Titeln (z. B. "Auswirkungen auf Segmente" → trifft "segment" statt "auswirkung") unerwartete DTOs liefern. Längerer-Match-first oder Priority-Tabelle als Verbesserung in einem späteren Slice.
- `PlanResponse.sections` hat keinen `min_length`-Constraint (LLM-seitig nicht erzwingbar via strict-schema). Der downstream `ReportOutlineModel`-Validator prüft Min 2 / Max 5 weiterhin serverseitig.
