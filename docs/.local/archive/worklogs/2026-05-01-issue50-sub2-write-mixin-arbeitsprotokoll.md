# Arbeitsprotokoll — Issue #50, Sub-Slice 2: Write-Mixin extrahieren

**Datum:** 2026-05-01
**Branch:** `claude/eloquent-chandrasekhar-9ef8ff`
**Slice:** v0.9.0 → EPIC-08-ST-01 → Sub-Slice 2 (von 3)
**Issue:** [#50 — Neo4jStorage in Read/Write/Search schneiden](https://github.com/arn0ld87/agora/issues/50)
**Vorgänger-Commit:** `9134ee0` (Sub-Slice 1, Mappings + Read-Mixin)

## Ziel

Zweite Etappe des EPIC-08-Boss-Fights: alle mutierenden Methoden aus
`neo4j_storage.py` in ein eigenes `Neo4jWriteMixin` ziehen. Damit ist
die Akzeptanzbedingung „Schreiblogik, Leselogik und Suche liegen nicht
mehr in einer Datei" zur Hälfte erfüllt — Read und Write getrennt;
Search folgt in Sub-Slice 3.

## Änderungen

### Neu: `backend/app/storage/neo4j_write.py` (513 LOC)

`Neo4jWriteMixin`-Klasse mit 11 Methoden:

- **Graph-Lifecycle**: `create_graph`, `delete_graph`, `set_ontology`
- **Add-Data**: `add_text` (3-Phasen-Orchestrator), `_persist_episode`
  (Phase 3, 163 LOC mit Cypher), `add_text_batch`, `wait_for_processing`
- **Temporal-Edges (Issue #10)**: `reinforce_relation`,
  `tombstone_relation`, `backfill_temporal_defaults`
- **Helper**: `_evaluate_ontology_mutations` (Best-Effort, swallowt
  Exceptions; mitgewandert weil von `add_text` aufgerufen)

Imports zentral aus den neuen Modulen:

- `services.ingestion_pipeline` (`extract_entities_and_relations`,
  `embed_entities_and_relations` für Phase 1+2)
- `storage.neo4j_mappings` (`edge_to_dict` für `reinforce_relation`,
  `sanitize_label` für Phase 3)

Mixin-Voraussetzungen am konkreten Storage:
`self._driver`, `self._call_with_retry`, `self._ner`, `self._embedding`,
`self._ontology_mutation_service`, `self.get_ontology` (vom
`Neo4jReadMixin`).

### Geändert: `backend/app/storage/neo4j_storage.py` (701 → 228 LOC, **−473**)

- Klassen-Definition: `class Neo4jStorage(Neo4jReadMixin,
  Neo4jWriteMixin, GraphStorage)`.
- Alle 11 Write-Methoden gelöscht (inkl. `_persist_episode` und
  `_evaluate_ontology_mutations`).
- Imports `uuid`, `json`, `typing.List`, `typing.Callable` und
  `services.ingestion_pipeline.*` entfallen — nicht mehr genutzt.
- Die übrig bleibenden Bestandteile sind:
  - **Constants**: `MAX_RETRIES`, `RETRY_DELAY_BASE`
  - **Konstruktor + Lifecycle**: `__init__`, `close`,
    `set_ontology_mutation_service`, `_verify_connectivity`,
    `_ensure_schema`
  - **Health-Status**: `is_connected`, `last_error`, `last_success_ts`
  - **Retry-Wrapper**: `_call_with_retry`
  - **Search**: `search` (wandert in Sub-Slice 3 raus)
  - **Re-Export-Aliasse**: `_node_to_dict`, `_edge_to_dict` als
    `staticmethod`

## Verifikation

```bash
npm run check
```

- `lint:backend` → All checks passed (Ruff)
- `test:backend` → **671 passed, 2 skipped** (unverändert zu Sub-Slice 1)
- `lint:frontend` → 1 warning, 0 errors (Vorzustand)
- `test:frontend` → 40 passed
- `build:frontend` → ✓ built in 3.23s

Keine neuen Tests für diesen Sub-Slice — das Verhalten der
Write-Methoden ist Wire-Identical zur Vorher-Variante, und sie sind
bereits über bestehende Suiten gedeckt:

- `test_neo4j_resilience.py` (6 Tests): MAX_RETRIES, Retry-Backoff,
  Health-State-Tracking — feuert via `add_text`-/`create_graph`-Pfade.
- `test_neo4j_ontology_wiring.py` (8 Tests): Late-Binding und
  Modus-Verhalten von `_evaluate_ontology_mutations`.
- `test_ingestion_pipeline.py` (11 Tests): Phase 1 + 2 Wire-Identical
  mit Mock-Backends.
- `test_neo4j_filtered_entities.py` (4 Tests): Read-Pfad nach
  Mixin-MRO.

## Akzeptanzkriterien Issue #50 (Stand)

- [x] Mappings sind zentral wiederverwendbar — Sub-Slice 1 ✓
- [ ] Schreiblogik, Leselogik und Suche liegen nicht mehr in einer
  Datei — **Schreib + Lese ✓** (`neo4j_write.py`, `neo4j_read.py`),
  Suche folgt in Sub-Slice 3.

## LOC-Bilanz

- `neo4j_storage.py`: **701 → 228 LOC** (−473, −67,5 %)
- **Seit Sub-Slice 1: 1127 → 228 LOC (−899, −79,8 %, vier Fünftel weg)**
- `neo4j_write.py`: 0 → 513 LOC (neu, davon 163 LOC Phase-3-Cypher)

## Folge-Sub-Slice

- **Sub-Slice 3**: `Neo4jSearchMixin` in `neo4j_search.py` (`search` —
  ~32 LOC). Klassen-Komposition mit `(Neo4jReadMixin, Neo4jWriteMixin,
  Neo4jSearchMixin, GraphStorage)`. Schließt #50, schließt EPIC-08,
  schließt v0.9.0 (12/12).
