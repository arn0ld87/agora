# Slice C1 — Backend-Graph-DTOs (Closes #52)

**Datum:** 2026-05-01
**Sprint:** v0.9.0 — Domain Cleanup
**Issue:** #52 (EPIC-08-ST-03) — Frontend-taugliche Graph-DTOs definieren

## Inventur

`backend/app/api/graph.py:get_graph_data` (`/data/<graph_id>`) lieferte bisher das raw Dict aus `Neo4jStorage.get_graph_data` (Z. 995-1045) zurück — kein dokumentiertes Wire-Schema, kein Schutz gegen Storage-Drift.

Frontend hat seit Issue #36 ViewModels in `frontend/src/components/graph/graphPanelData.js` (`GraphNodeViewModel`, `GraphEdgeViewModel`) plus den `normalizeEdgeAliases`-Mapper, der die Backend-Aliasse `fact_type` (= `name`) und `episodes` (= `episode_ids`) auflöst.

Das Storage-Output-Schema:
- **Nodes:** `uuid`, `name`, `labels`, `summary`, `attributes`, `created_at`
- **Edges (Property):** `uuid`, `name`, `fact`, `source_node_uuid`, `target_node_uuid`, `attributes`, `created_at`, `valid_at`, `invalid_at`, `expired_at`, `valid_from_round`, `valid_to_round`, `reinforced_count`, `episode_ids`
- **Edges (Enriched beim JOIN in `get_graph_data`):** `fact_type`, `source_node_name`, `target_node_name`, `episodes`
- **Top-Level:** `graph_id`, `nodes`, `edges`, `node_count`, `edge_count`

## Schnittentscheidung

**Drei dataclasses in `backend/app/models/graph.py`** mit `to_dict()` und `from_dict()`/`from_storage_dict()`. Pattern folgt `models/report.py` (Slice A3) und `models/task.py`/`models/project.py`.

**Wire-Identity-Garantie:** `GraphDataDTO.from_storage_dict(d).to_dict() == d` für gültige Storage-Outputs. Das ist explizit getestet, sodass jede künftige Storage-Änderung am Schema (Property hinzugefügt, Alias entfernt) die Tests rot färbt, bevor das Frontend bricht.

**API-Anpassung minimal:** `get_graph_data` schickt das Storage-Dict erst durch `GraphDataDTO.from_storage_dict()` und dann `to_dict()` zurück in `json_success`. Wire-Format bit-identisch zu vorher; das DTO wird zur dokumentierten zentralen Wahrheitsquelle.

**Out-of-scope:** `/snapshot/<graph_id>/<round>` und `/diff/<graph_id>` (Z. 592-640) liefern eigene `to_dict()`-Outputs aus `temporal_graph` — das sind separate Wire-Formate und gehören eher zu einem eigenen `TemporalSnapshotDTO`-Slice (außerhalb #52-Scope, vermutlich bei #51 Pipeline-Aufgabe relevant).

## Änderungen

### `backend/app/models/graph.py` (+170 LOC, neu)
- `GraphNodeDTO` (dataclass): 6 Felder, `to_dict`/`from_dict`
- `GraphEdgeDTO` (dataclass): 14 Property-Felder + 4 Enriched-Fields, `to_dict`/`from_dict` mit Alias-Fallbacks (`fact_type ← name`, `episodes ← episode_ids`)
- `GraphDataDTO` (dataclass): `graph_id`, `nodes`, `edges`, `node_count`, `edge_count`, `to_dict`, `from_storage_dict` mit Count-Fallback auf Listen-Länge

### `backend/app/models/__init__.py`
- DTOs in `__all__` exportiert (Paket-Ebene)

### `backend/app/api/graph.py` (+5 / −2 LOC)
- Neuer Import `from ..models.graph import GraphDataDTO`
- `get_graph_data` schickt Response durch DTO-Round-Trip mit Issue-#52-Kommentar

### `backend/tests/test_graph_dtos.py` (+128 LOC, neu)
- 6 Tests:
  - `test_graph_data_dto_roundtrip_preserves_storage_dict` — bit-identische Round-Trip-Garantie für realistisches Storage-Dict
  - `test_graph_node_dto_handles_optional_fields` — None/Leer-Defaults
  - `test_graph_edge_dto_falls_back_episodes_to_episode_ids` — Legacy-Alias-Fallback
  - `test_graph_edge_dto_fact_type_falls_back_to_name` — Alias-Fallback
  - `test_graph_data_dto_empty_graph` — Edge-Case
  - `test_graph_data_dto_count_fallback_to_list_length` — Defensive

## Verifikation

`npm run check` 5/5 grün:
- Backend Lint: `ruff` clean
- Backend Tests: **531 passed**, 2 skipped (Redis) — **+6 neue DTO-Tests**
- Frontend Lint: 0 errors, 1 vorhandene Warning
- Frontend Tests: **40 passed**
- Frontend Build: vite, ok

Bestehende Graph-Tests (`test_graph_export.py`, `test_neo4j_*.py`) prüfen den Storage-Output und laufen weiter grün — Wire-Format vor und nach dem DTO-Roundtrip ist identisch.

## Akzeptanzkriterien #52

- [x] Stabile Graph-DTOs für Frontend-Konsumenten — `GraphNodeDTO`, `GraphEdgeDTO`, `GraphDataDTO`
- [x] Dokumentiert — Modul-Docstring + Field-Kommentare + Schnittstellen-Hinweis zu `graphPanelData.js`
- [x] Schnittstelle zu EPIC-04-ST-03 (Frontend-Mapper) — Aliasse `fact_type`/`episodes` werden weiterhin geliefert; Frontend-Mapper bleibt unangetastet

## Konsequenz für v0.9.0

Issue #52 abgeschlossen. Verbleibender v0.9.0-Backlog: **4 echte Issues** (EPIC-07 ×2: #47/#48; EPIC-08 ×2: #50 Storage-Split, #51 Pipeline-Steps).

## Folge-Slice

Open. EPIC-08-Reste: #51 (`add_text` in NER/Embed/Persist-Steps zerlegen, mittlerer Aufwand) oder #50 (Neo4jStorage 1106-LOC-Monolith in Read/Write/Search splitten — Boss-Fight). Alternativ EPIC-07 (#47 Tools, #48 Prompts).
