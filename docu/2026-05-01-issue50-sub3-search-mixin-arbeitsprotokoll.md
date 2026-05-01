# Arbeitsprotokoll — Issue #50, Sub-Slice 3: Search-Mixin + Closure

**Datum:** 2026-05-01
**Branch:** `claude/eloquent-chandrasekhar-9ef8ff`
**Slice:** v0.9.0 → EPIC-08-ST-01 → Sub-Slice 3 (von 3) — **schließt Issue #50, EPIC-08 und v0.9.0**
**Issue:** [#50 — Neo4jStorage in Read/Write/Search schneiden](https://github.com/arn0ld87/agora/issues/50)
**Vorgänger-Commit:** `b91d3cf` (Sub-Slice 2, Write-Mixin)

## Ziel

Letzte Etappe des EPIC-08-Boss-Fights: die `search`-Methode in ein
eigenes `Neo4jSearchMixin` ziehen und die Klassen-Komposition
finalisieren. Damit ist die Akzeptanzbedingung „Schreiblogik,
Leselogik und Suche liegen nicht mehr in einer Datei" vollständig
erfüllt.

## Änderungen

### Neu: `backend/app/storage/neo4j_search.py` (57 LOC)

`Neo4jSearchMixin`-Klasse mit der einen Methode `search(graph_id, query,
limit=10, scope='edges')`. Hybrid-Search-Einstieg, der die
eigentliche Vektor-/Keyword-Logik via `self._search` (eine
`SearchService`-Instanz vom konkreten Storage-Konstruktor) nutzt.

Mixin-Voraussetzungen am konkreten Storage:
`self._driver`, `self._call_with_retry`, `self._search`.

### Geändert: `backend/app/storage/neo4j_storage.py` (228 → 195 LOC, −33)

- Klassen-Definition final: `class Neo4jStorage(Neo4jReadMixin,
  Neo4jWriteMixin, Neo4jSearchMixin, GraphStorage)`.
- `search`-Methode gelöscht.
- Imports `typing.Any`/`typing.Dict` entfallen — nicht mehr genutzt.
- Übrig im Storage-Modul:
  - **Konstanten**: `MAX_RETRIES`, `RETRY_DELAY_BASE`
  - **Konstruktor + Lifecycle**: `__init__` (Driver-Setup,
    DI-Konstruktor-Args), `close`, `set_ontology_mutation_service`,
    `_verify_connectivity`, `_ensure_schema`
  - **Health-Status**: `is_connected`, `last_error`, `last_success_ts`
    (Properties, exposed über `/api/status`)
  - **Retry-Wrapper**: `_call_with_retry` (Health-State-Tracking
    inklusive)
  - **Re-Export-Aliasse**: `_node_to_dict`, `_edge_to_dict` als
    `staticmethod` (Wire-Identity, falls externe Subklassen — laut
    grep keine Caller, aber billig zu erhalten)

## Verifikation

```bash
npm run check
```

- `lint:backend` → All checks passed (Ruff)
- `test:backend` → **671 passed, 2 skipped** (unverändert)
- `lint:frontend` → 1 warning, 0 errors (Vorzustand)
- `test:frontend` → 40 passed
- `build:frontend` → ✓ built in 7.23s

`search`-Verhalten ist Wire-Identical zur Vorher-Variante; bestehende
Suiten via konkrete Storage-Instanz decken das ab.

## Akzeptanzkriterien Issue #50 — vollständig

- [x] **Schreiblogik, Leselogik und Suche liegen nicht mehr in einer
  Datei** — `neo4j_read.py`, `neo4j_write.py`, `neo4j_search.py` als
  drei separate Module mit eigenen Mixins. Komposition über Python-MRO
  in `Neo4jStorage(Neo4jReadMixin, Neo4jWriteMixin, Neo4jSearchMixin,
  GraphStorage)`.
- [x] **Mappings sind zentral wiederverwendbar** — `neo4j_mappings.py`
  mit `node_to_dict`, `edge_to_dict`, `sanitize_label`. Importiert von
  Read- und Write-Pfaden.

## LOC-Bilanz Issue #50 (gesamt)

- `neo4j_storage.py`: **1127 → 195 LOC** (**−932, −82,7 %, vier
  Fünftel weg**)
- `neo4j_read.py`: 0 → 381 LOC (10 Read-Methoden)
- `neo4j_write.py`: 0 → 513 LOC (11 Write-Methoden inkl. Phase-3-Cypher)
- `neo4j_search.py`: 0 → 57 LOC (1 Search-Methode)
- `neo4j_mappings.py`: 0 → 118 LOC (3 Helfer)
- **Total verteilt: 1264 LOC in 5 Dateien** (vs. vorher 1127 LOC in
  einer Datei). Steigerung um +137 LOC kommt von Modul-Docstrings,
  Mixin-Signaturen und Re-Export-Kommentaren — explizite
  API-Dokumentation, kein Logic-Duplikat.

## EPIC-08 — abgeschlossen (4/4)

- #41 ist EPIC-06 (nicht EPIC-08).
- EPIC-08-Stories: #50 ✓, #51 ✓, #52 ✓ — alle drei durch.

## v0.9.0 — abgeschlossen (12/12)

- EPIC-06 ✓ (4/4): #41, #42, #43, #44
- EPIC-07 ✓ (5/5): #45, #46, #47, #48, #49
- EPIC-08 ✓ (3/3): #50, #51, #52

**Milestone „v0.9.0 — Domain Cleanup" ist mit diesem Slice komplett.**

## Test-Counter (final)

- Backend: **671** (Baseline 531 → 671, +140 in v0.9.0-Pfad-A)
- Frontend: 40 (unverändert)
- Total: **711**

## Folge-Empfehlung

- Release v0.9.0 mit `[Unreleased]`-Block-Konsolidierung in
  `[0.9.0]`.
- LOC-Bilanz im Release-Notes-Eintrag herausstellen:
  - `simulation_manager.py`: 789 → 403 (−49 %)
  - `report_agent.py`: 3184 → 2179 (−31,6 %)
  - `neo4j_storage.py`: 1127 → 195 (−82,7 %)
- Honcho-Memory-Update: v0.9.0 ist Open-Source-Slice (kein
  IHK-Facharbeitsdruck), 1.005 LOC + 932 LOC + 386 LOC raus aus
  Hot-Spots.
