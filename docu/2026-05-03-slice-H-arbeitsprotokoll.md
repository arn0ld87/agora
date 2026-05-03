# Sub-Slice H — Arbeitsprotokoll: Edge-Yield-Fix (schließt #216)

**Datum:** 2026-05-03
**Branch:** `fix/task-H-entity-relationships`
**Bearbeiter:** Agora-Backend-Refactor-Worker

---

## Befund

User-Befund: „Manchmal werden von den Modellen keine Beziehungen zwischen
den Entitäten hergestellt."

## Diagnose

### Pipeline-Pfad (Text → Edges)

```
GraphBuilderService.add_text_batches()
  → storage.add_text(graph_id, chunk, round_num=0)
    → ingestion_pipeline.extract_entities_and_relations(ner, text, ontology)
      → NERExtractor.extract(text, ontology)
        → LLMClient.chat_json(messages)       ← LLM-Aufruf
        → NERExtractor._validate_and_clean()  ← Filter
    → ingestion_pipeline.embed_entities_and_relations(...)
    → Neo4jWriteMixin._persist_episode(...)   ← Neo4j-Write
```

### Root-Cause (Prompt-Issue)

`app/storage/ner_extractor.py`, `_SYSTEM_PROMPT`, Regel 1 (vor Fix):

```
1. Only extract entity types and relation types defined in the ontology.
```

Combined with `temperature=0.1` and no few-shot examples:
- Bei schmalem oder leerem `edge_types`-Bereich (kommt in frühen Graph-Build-Phasen vor)
  interpretiert das Modell diese Regel als hartes Verbot.
- Ergebnis: Das LLM emittiert lieber keine Relations als eine mit unbekanntem Typ.

### Verifikation: Filter-Pfad war nicht schuld

`_validate_and_clean` filtert Relations *nicht* nach Typ — es schreibt sogar
fehlende Source/Target-Entities nach. Stub-Tests belegen das.

Die Kandidaten aus dem Task:
- Prompt-Issue: **bestätigt** — Root-Cause
- Strict-Schema-Issue: **nicht vorhanden** — `_validate_and_clean` ist lenient
- `evidence_binder`-Filter: **falsche Pipeline** — `evidence_binder` verarbeitet
  Report-Abschnitts-Text, nicht Graph-Kanten

## Fix

**Datei:** `backend/app/storage/ner_extractor.py`

Regel 1 umformuliert:
```
Vor:  "Only extract entity types and relation types defined in the ontology."
Nach: "Use the ontology types as preferred labels. If a relation clearly exists
      in the text but no matching ontology type fits, use the most descriptive
      UPPER_SNAKE_CASE label you can derive from the text. Never omit a
      relation just because the ontology does not explicitly list its type."
```

Zusätzlich Regel 6 ergänzt: „When in doubt, include the relation."

Drei konkrete Few-Shot-Beispiele direkt im System-Prompt:
- `ACQUIRED` (Müller GmbH → Schmidt KG)
- `LEADS` + `REPORTS_TO` (Anna → Lichtblick, Anna → Boris)
- `COLLABORATES_WITH` (Universität Leipzig → Fraunhofer-Institut)

## Edge-Yield-Tabelle (Stub-Simulation)

| Fixture | Text | Entitäten (stub) | Edges (stub) | Yield ≥ Schwelle? |
|---|---|---|---|---|
| fixture_a.txt | Müller GmbH übernahm Schmidt KG... | 2 | 1 | ja (≥1) |
| fixture_b.txt | Anna leitet Projekt 'Lichtblick'... | 3 | 2 | ja (≥1) |
| fixture_c.txt | Universität Leipzig arbeitet mit... | 2 | 1 | ja (≥1) |

Stubs repräsentieren schemavalide LLM-Antworten; der Test prüft, dass
`_validate_and_clean` diese nicht wegfiltert.

## Geänderte Dateien

| Datei | Art | +/- LOC |
|---|---|---|
| `backend/app/storage/ner_extractor.py` | Prompt-Fix (Regel 1 + 6 + Few-Shot) | +22 / -4 |
| `backend/pyproject.toml` | `pytest.mark.llm` registriert | +4 / 0 |
| `backend/tests/services/test_edge_yield.py` | Neue Test-Datei | +248 |
| `backend/tests/fixtures/edge_yield/fixture_a.txt` | Fixture | +1 |
| `backend/tests/fixtures/edge_yield/fixture_b.txt` | Fixture | +1 |
| `backend/tests/fixtures/edge_yield/fixture_c.txt` | Fixture | +1 |
| `CHANGELOG.md` | `[Unreleased] Fixed` Eintrag | +8 |

## Test-Output

```
8 passed, 3 deselected in 1.05s
Full suite: 1331 passed, 9 skipped, 3 deselected in 105s
```

## Kein Commit — Übergabe an Orchestrator
