# Arbeitsprotokoll — Issue #50, Sub-Slice 1: Mappings + Read-Mixin extrahieren

**Datum:** 2026-05-01
**Branch:** `claude/eloquent-chandrasekhar-9ef8ff`
**Slice:** v0.9.0 → EPIC-08-ST-01 → Sub-Slice 1 (von 3)
**Issue:** [#50 — Neo4jStorage in Read/Write/Search schneiden](https://github.com/arn0ld87/agora/issues/50)
**Vorgänger-Commit:** `3a74daa` (PR #116, Issue #51 Ingestion-Pipeline)

## Ziel

Erste Etappe des EPIC-08-Boss-Fights: zentrale Storage-Helfer
(`node_to_dict`, `edge_to_dict`, `sanitize_label`) und alle 10
Read-Methoden aus `neo4j_storage.py` herausziehen, ohne das Verhalten
der bestehenden Storage-Klasse zu ändern.

## Strategie: Mixin-Pattern statt Komposition

`Neo4jStorage` enthält ~30 Methoden, die alle auf gemeinsamen Zustand
zugreifen (`self._driver`, `self._call_with_retry`, `self._search_service`,
`self._embedding`, `self._ner`). Komposition würde Driver-Sharing und
Caller-Anpassungen erzwingen — Mixin-Pattern hält State-Sharing über
Python-MRO trivial. Risiko (Diamond-Inheritance) liegt nicht vor:
`GraphStorage` (ABC) und `Neo4jReadMixin` haben kein gemeinsames
Mixin-Vorgängerset.

## Änderungen

### Neu: `backend/app/storage/neo4j_mappings.py` (118 LOC)

- `node_to_dict(node, labels) -> dict` — Pure Funktion, baut das
  Standard-Node-Dict (uuid, name, labels ohne `Entity`, summary,
  attributes, created_at). Internfelder (`embedding`, `name_lower`)
  werden verworfen.
- `edge_to_dict(rel, source_uuid, target_uuid) -> dict` — Pure Funktion,
  baut das Standard-Edge-Dict inkl. der Issue-#10-Temporalfelder
  (`valid_from_round`, `valid_to_round`, `reinforced_count`). Internfeld
  `fact_embedding` weg. Driver-Edge-Case: `episode_ids` als Skalar wird
  zu Single-Element-Liste gewrappt.
- `_safe_attributes(props)` — gemeinsamer Robust-Parser für
  `attributes_json` (defekt → `{}`).
- `sanitize_label(value) -> Optional[str]` — Cypher-Identifier-Whitelist
  für LLM-erzeugte Labels. Mit-extrahiert (war modul-lokal in
  `neo4j_storage.py`), weil Read-Pfad (`get_nodes_by_label`) und
  Write-Pfad (`_persist_episode`) sie beide brauchen — zirkuläre Imports
  vermieden.

### Neu: `backend/app/storage/neo4j_read.py` (381 LOC)

`Neo4jReadMixin`-Klasse mit allen 10 Read-Methoden:

- `get_ontology(graph_id)`
- `get_all_nodes(graph_id, limit)`
- `get_node(uuid)`
- `get_node_edges(node_uuid)`
- `get_nodes_by_label(graph_id, label)`
- `get_filtered_entities_with_edges(graph_id, defined_entity_types, enrich_with_edges)`
- `get_all_edges(graph_id)`
- `get_edges_at_round(graph_id, round_num)`
- `get_graph_info(graph_id)`
- `get_graph_data(graph_id)` (mit Frontend-Enrichment fact_type, source/target_node_name, episodes-Legacy-Alias)

Mixin-Voraussetzungen am konkreten Storage:
`self._driver`, `self._call_with_retry`. Mappings werden direkt aus
`neo4j_mappings` importiert — kein `self.`-Lookup, keine
Static-Method-Indirektion mehr.

### Geändert: `backend/app/storage/neo4j_storage.py` (1127 → 701 LOC, **−426**)

- Klassen-Definition: `class Neo4jStorage(Neo4jReadMixin, GraphStorage)`.
- Alle 10 Read-Methoden gelöscht.
- `_node_to_dict` und `_edge_to_dict` als `staticmethod`-Re-Export der
  Modul-Funktionen erhalten (Wire-Identity für ggf. externe Subklassen).
- `_sanitize_label` kommt jetzt aus `neo4j_mappings` (Import-Alias auf
  alten Modul-Namen, damit `_persist_episode` ohne Code-Änderung
  weiterläuft).
- Modul-Konstanten `_LABEL_SAFE_RE` und Modul-Funktion
  `_sanitize_label` aus `neo4j_storage.py` entfernt; `import re`
  entfällt — wird hier nicht mehr genutzt.

### Neu: `backend/tests/test_neo4j_mappings.py` (23 Tests, 3 Test-Klassen)

- **TestNodeToDict** (7 Tests): Minimal-Schema, JSON-Parsing,
  defekter JSON-Fallback, Internal-Field-Stripping (`embedding`,
  `name_lower`), Empty-Label-Liste, Entity-Only-Labels, fehlende
  Optional-Properties.
- **TestEdgeToDict** (6 Tests): Minimal-Schema mit Temporalfeldern,
  `fact_embedding`-Stripping, `episode_ids`-Skalar-Wrapping, fehlende
  episode_ids → `[]`, Default-`reinforced_count = 1`, defekter JSON.
- **TestSanitizeLabel** (10 Tests): ASCII-Pass, Underscore, Whitespace
  → `_`, Umlaute weg, `Entity` reject, Empty/Whitespace reject,
  Non-String reject, Starting-Digit reject, **Backtick-Injection-Versuch
  durch Whitelist neutralisiert**, 50-Zeichen-Limit.

## Verifikation

```bash
npm run check
```

- `lint:backend` → All checks passed (Ruff)
- `test:backend` → **671 passed, 2 skipped** (vorher 648 → +23 mapping-Tests)
- `lint:frontend` → 1 warning, 0 errors (Vorzustand)
- `test:frontend` → 40 passed
- `build:frontend` → ✓ built in 3.34s

Bestehende Neo4j-Tests (`test_neo4j_resilience`, `test_neo4j_filtered_entities`,
`test_neo4j_ontology_wiring`, 18 Tests) und alle anderen Test-Suiten
unverändert grün — Verhalten der `Neo4jStorage`-Klasse identisch zur
Vorher-Variante via Mixin-MRO.

## LOC-Bilanz

- `neo4j_storage.py`: **1127 → 701 LOC (−426, −37,8 %)** — größter
  Cut in v0.9.0-Pfad-A bisher
- `neo4j_read.py`: 0 → 381 LOC (neu)
- `neo4j_mappings.py`: 0 → 118 LOC (neu, davon ~30 LOC sanitize_label-
  Logik mit-portiert)

## Akzeptanzkriterien Issue #50 (Stand)

- [x] **Mappings sind zentral wiederverwendbar** — `node_to_dict`,
  `edge_to_dict`, `sanitize_label` in `neo4j_mappings.py`, importiert
  von Read/Write/Search-Pfaden.
- [ ] Schreiblogik, Leselogik und Suche liegen nicht mehr in einer
  Datei — Lese-Pfad ✓, Schreiblogik (Sub-Slice 2) und Suche
  (Sub-Slice 3) folgen.

## Folge-Sub-Slices

- **Sub-Slice 2**: `Neo4jWriteMixin` in `neo4j_write.py` mit
  `create_graph`, `delete_graph`, `set_ontology`, `add_text`,
  `_persist_episode`, `add_text_batch`, `wait_for_processing`,
  `reinforce_relation`, `tombstone_relation`,
  `backfill_temporal_defaults`.
- **Sub-Slice 3**: `Neo4jSearchMixin` in `neo4j_search.py` mit
  `search`. Klassen-Komposition `class Neo4jStorage(Neo4jReadMixin,
  Neo4jWriteMixin, Neo4jSearchMixin, GraphStorage)`. Schließt #50.
