# Arbeitsprotokoll M11.8e — simulated_quote XML-Tag + validate_quote_anchors

**Datum:** 2026-05-09
**Branch:** feat/m11-8e-quote-evidence-anchors
**Sub-Slice:** M11.8e (Layer 1, Aufwand M, Refs PLAN.md PR 10, M11.8)

## Ausgangslage (verifiziert vor Beginn)

- `simulated_quote`-XML-Tag existierte NICHT im Code (rg-Suche leer).
- `Claim.evidence_refs` bereits `min_length=1`-Pflichtfeld in `report_v3.py:60`.
- Andere DTOs (`Persona`, `Segment`, `FrictionPoint`, …) haben `evidence_refs: list[str] = Field(default_factory=list)` (optional, explizit außerhalb dieses Slices).
- `EvidenceMapModel` nutzt `source_id_anchor` als Anker-Feld (NICHT `evidence_id` wie in der Spec angedeutet — verifiziert via `rg`).

## Edits (Datei:Zeile)

### 1. `backend/app/services/report_prompts.py`

- **Zeile 168–200 (neu):** Block `5. [Mandatory Quote Format for Simulated Persona Statements — MUST FOLLOW]` in `SECTION_SYSTEM_PROMPT_TEMPLATE` eingefügt. Beschreibt XML-Tag-Format mit `persona_id` und `seed_anchor`, gibt korrekte und fehlerhafte Beispiele, erklärt `seed_doc:`-Prefix als opaque OK.
- **Zeile 323–326 (neu, in `SECTION_USER_PROMPT_TEMPLATE`):** Kurzer `[⚠️ Quote Format Reminder — Mandatory]`-Block als Format-Erinnerung.

### 2. `backend/app/services/report_agent/evidence.py`

- **Zeile 1–7 (Header-Imports):** `re`, `dataclasses.dataclass/field`, `Union` hinzugefügt.
- **Zeile 10–180 (neu):** `QuoteValidationResult`-Dataclass + `_extract_known_anchors()`-Hilfsfunktion + `validate_quote_anchors()`-Validator eingefügt.
  - Tag-Parser: `re.compile(r'<simulated_quote\s+([^>]+)>(.*?)</simulated_quote>', re.DOTALL)` — kein lxml/bs4.
  - Attribut-Parser: `re.findall(r'(\w+)="([^"]*)"', attrs)`.
  - `seed_anchor` wird gegen `source_id_anchor`-Werte in `global_evidence` geprüft (NICHT `evidence_id` — rg-verifiziert).
  - `seed_doc:`-Prefix ist opaque OK (kein Map-Lookup erforderlich).
  - `persona_id` wird nur gegen Whitelist geprüft wenn `persona_ids` nicht leer ist (leere Liste = unkonfiguriert → Whitelist-Check übersprungen).
- **`__all__`:** `QuoteValidationResult` und `validate_quote_anchors` hinzugefügt.

### 3. `backend/app/services/report_agent/workflow.py`

- **Zeile 10 (neu):** `from .evidence import validate_quote_anchors` Import.
- **Zeile 21–39 (neu):** `_QUOTE_REQUIRED_SECTION_KEYWORDS` frozenset + `_section_expects_quotes()`-Hilfsfunktion.
- **Zeile 445–499 (neu, in `generate_report()`):** Quote-Anchor-Validierungs-Hook nach `section_content = generate_section_react(...)`:
  - Nur für Sections mit `_section_expects_quotes(section.title) == True`.
  - Bei `valid=False`: einmaliger Repair-Retry via erneuten `generate_section_react()`-Aufruf.
  - Bei persistentem Fehler: `logger.error(...)` + `section.metadata["quote_validation_failed"] = True`.
  - `persona_ids` via `getattr(agent, "persona_ids", [])` — unkonfiguriert → leere Liste → kein Whitelist-Check.

## Neue Test-Dateien

| Datei | Tests | Status |
|---|---|---|
| `tests/services/test_report_agent_quote_anchors.py` | 11 Tests | grün |
| `tests/services/test_report_agent_workflow_quote_validation.py` | 2 Tests | grün |

## Test-Results

```
1669 passed, 9 skipped, 7 deselected in 21.05s
```

Volltest grün (9 skipped = Redis + Docker-Compose-Umgebungsbedingungen, unverändert).

## Akzeptanz-Checks

| Check | Status |
|---|---|
| `rg 'simulated_quote' report_prompts.py` — mind. 2 Treffer | ✓ (6 Treffer) |
| `rg 'def validate_quote_anchors' evidence.py` — 1 Treffer | ✓ |
| `rg 'validate_quote_anchors' workflow.py` — mind. 1 Treffer | ✓ (4 Treffer) |
| Wording-Glossar-Check (kein Verstoß) | ✓ grün (rg exit=1) |
| Schema-Drift (`git diff --exit-code schemas/`) | ✓ kein Drift |
| Volltest Backend | ✓ 1669 passed |
| Contract-Tests (`tests/contracts/`) | ✓ 88 passed |
| Ruff + mypy | ✓ 0 Issues |

## Wording-Glossar-Compliance (Check 4)

`rg -nci 'future prediction|rehearsal of the future|god.s eye view|public opinion prediction|agentic.prediction.engine' backend/app/services/report_prompts.py` → exit 1 (kein Match).

Neue Prompt-Formulierungen verwenden: „simulated persona reactions", „simulation data", „scenario evaluation", „analytical observer perspective" — konform mit Glossar v1.

## Spezifikations-Abweichungen (verifiziert)

1. **`evidence_id` → `source_id_anchor`**: Die Spec referenziert `evidence_map["global_evidence"][*]["evidence_id"]`. Dieses Feld existiert NICHT im tatsächlichen Datenmodell (rg: keine Treffer). Tatsächliches Anker-Feld ist `source_id_anchor` aus `EvidenceItemModel` (`report_contract.py:86`). Validator nutzt `source_id_anchor`.

2. **`persona_ids` aus Plan**: Die Spec sagt „persona_ids (vom Plan)" ohne Angabe, woher diese kommen. Im aktuellen Workflow gibt es keine pre-built Persona-ID-Liste. Implementiert als: `getattr(agent, "persona_ids", [])` — optionales Attribut. Wenn leer, wird Whitelist-Check übersprungen (nur Anwesenheit von `persona_id` geprüft). Agent-Klasse kann später `persona_ids` aus Graph-Context befüllen.

## Offene Followups

- **Persona-IDs aus Graph-Context:** Wenn `agent.persona_ids` befüllt wird (z. B. aus `graph_tools.get_simulation_context()` extrahiert), greift der Whitelist-Check automatisch. Kein Slice-Blocker.
- **`seed_doc:`-Anchors im Frontend-Render:** `quote_validation_failed`-Flag ist gesetzt, Frontend-Render- und PDF-Schritte können darauf reagieren (separater Slice für Render-Blocking).
- **Tolerant-Mode:** Nicht in diesem Slice. Strict-Mode (default) ist implementiert.
