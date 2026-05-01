# Arbeitsprotokoll — Issue #51: Ingestion-Pipeline in Schritte zerlegen

**Datum:** 2026-05-01
**Branch:** `claude/eloquent-chandrasekhar-9ef8ff`
**Slice:** v0.9.0 → EPIC-08-ST-02 — **schließt Issue #51**
**Issue:** [#51 — Ingestion-Pipeline in Schritte zerlegen](https://github.com/arn0ld87/agora/issues/51)
**Vorgänger-Commit:** `d337e94` (PR #115, Issue #48 Prompt-Modularisierung)

## Ziel

Akzeptanzkriterien:
- [x] `add_text()` ist nicht mehr ein großer Block
- [x] NER / Embedding / Persistenz getrennt

Die 197-LOC-monolithische Methode `Neo4jStorage.add_text` (`backend/app/storage/neo4j_storage.py` Z.318–514) in drei klar abgegrenzte Phasen zerlegen — zwei davon als reine, unit-testbare Funktionen außerhalb des Storage-Moduls.

## Schnitt-Strategie

Die drei Phasen haben unterschiedliche Kopplungsmuster:

- **Phase 1 (NER + RE)** — nutzt nur den NER-Service. Pure Funktion möglich.
- **Phase 2 (Batch-Embedding)** — nutzt nur den Embedding-Service. Pure Funktion möglich.
- **Phase 3 (Persist)** — nutzt Driver, Cypher und Retry-Logik des Storage. Bleibt storage-intern.

Daher: Phase 1 + 2 ins neue `services/ingestion_pipeline.py`, Phase 3 als private Methode `Neo4jStorage._persist_episode`. `add_text` orchestriert die drei Phasen.

## Änderungen

### Neu: `backend/app/services/ingestion_pipeline.py` (97 LOC)

- `extract_entities_and_relations(ner, text, ontology) -> dict` — Phase 1.
  Delegiert an `ner.extract`, loggt Counter, gibt das Schema-vollständige
  Extraction-Dict zurück (Pass-Through für ggf. zusätzliche Keys —
  Wire-Identity zum NER-Vertrag).
- `embed_entities_and_relations(embedding, entities, relations) ->
  (entity_embeddings, relation_embeddings)` — Phase 2. Konkateniert
  Entity-Summaries (`"{name} ({type})"`) und Fact-Texts (mit Fallback
  `"{source} {type} {target}"` für Relations ohne `fact`-Key) in einen
  einzigen `embed_batch`-Call. Bei Crash: Liste von `[]`-Vektoren in
  passender Länge — Persist-Pfad bleibt robust.
- Eigener Logger `agora.ingestion_pipeline`.

### Geändert: `backend/app/storage/neo4j_storage.py` (1106 → 1127 LOC, +21)

- `add_text` (Z.322–369): **47 LOC** statt vorher 197 — ein
  3-Phasen-Orchestrator mit klar lesbaren Section-Kommentaren und
  Delegation an die neuen Pipeline-Funktionen.
- Neu: `_persist_episode(*, graph_id, episode_id, text, now,
  entities, relations, entity_embeddings, relation_embeddings,
  round_num) -> None` (Z.371–534, 163 LOC). Kwargs-only-Signatur,
  enthält Episode-Node-Erstellung, Entity-MERGE inkl. Label-Sanitization,
  und Relation-Erstellung. Cypher 1:1 portiert.
- Import-Block: `from ..services.ingestion_pipeline import (...)`.

Die LOC-Bilanz steigt leicht (+21), weil `_persist_episode` einen eigenen
Docstring und eine getypte Pflicht-kwargs-Signatur bekommt — das ist
keine Regression, sondern explizite Schnittstellen-Dokumentation. Der
**eigentliche `add_text`-Block** ist von 197 auf 47 LOC geschrumpft
(−76 %), womit das Akzeptanzkriterium „nicht mehr ein großer Block"
deutlich erfüllt ist.

### Neu: `backend/tests/test_ingestion_pipeline.py` (11 Tests, 3 Test-Klassen)

- **TestExtractEntitiesAndRelations** (3 Tests):
  - Delegation an `ner.extract(text, ontology)`.
  - Pass-Through zusätzlicher Schema-Keys (z. B. Meta-Felder).
  - Empty-Extraction.
- **TestEmbedEntitiesAndRelations** (7 Tests):
  - Empty-Inputs überspringen `embed_batch`-Call (Performance).
  - Konkatenation Entities-vor-Relations in einer Batch — geprüft mit
    Argument-Inspection.
  - Fallback-Text-Synthese für Relations ohne `fact`-Key.
  - Nur-Entities und Nur-Relations.
  - Embedding-Crash → leere Vektoren in passender Länge (kein Re-raise).
  - Ungerader Split (3 Entities + 1 Relation): Position-Alignment.
- **TestPipelineComposition** (1 Test): End-to-End-Komposition Phase
  1 → Phase 2 — sichert den Vertrag, den `add_text` heute orchestriert.

## Verifikation

```bash
npm run check
```

- `lint:backend` → All checks passed (Ruff)
- `test:backend` → **648 passed, 2 skipped** (vorher 637 → +11 pipeline-Tests)
- `lint:frontend` → 1 warning, 0 errors (Vorzustand)
- `test:frontend` → 40 passed
- `build:frontend` → ✓ built in 3.26s

Bestehende Neo4j-Tests (`test_neo4j_resilience`, `test_neo4j_filtered_entities`,
`test_neo4j_ontology_wiring` — 18 Tests) unverändert grün — Phase-3-Cypher
ist 1:1 portiert, Phase 1+2 verhalten sich identisch zur Inline-Variante.

## Akzeptanzkriterien Issue #51

- [x] `add_text()` ist nicht mehr ein großer Block — 197 → 47 LOC (−76 %)
- [x] NER / Embedding / Persistenz getrennt — Phase 1 + 2 als
  Top-Level-Funktionen in `services/ingestion_pipeline.py`,
  Phase 3 als private Methode `_persist_episode`

## LOC-Bilanz

- `add_text` selbst: **197 → 47 LOC** (−76 %, Akzeptanz-Kern)
- `neo4j_storage.py` gesamt: 1106 → 1127 LOC (+21, durch Method-Boundary
  und Docstring von `_persist_episode`)
- `services/ingestion_pipeline.py`: 0 → 97 LOC (neu)

Domain-Logik (NER, Embedding) liegt jetzt in `services/`, Persistenz
weiter in `storage/`. Saubere Schichtentrennung als Vorbereitung für
**#50** (Read/Write/Search-Split).

## EPIC-08 Stand

Mit #51 closed: 2/4 Stories durch (#52 ✓, #51 ✓).
Offen: nur noch **#50 — Neo4jStorage Read/Write/Search splitten** (Boss-Fight).

## v0.9.0 Stand nach diesem Slice

- **11/12 Issues closed (92 %)**
- EPIC-06 ✓ (4/4) · EPIC-07 ✓ (5/5) · EPIC-08 zu 50 % (2/4)
- Verbleibend: nur noch **#50** auf `neo4j_storage.py`

## Test-Counter

- Backend: **648** (Baseline 531 → 648, +117 in v0.9.0-Pfad-A)
- Frontend: 40 (unverändert)
- Total: **688**
