# Arbeitsprotokoll: Vector-Index Dimension-Drift Fix (Issue #263)

**Datum:** 2026-05-04
**Branch:** feat/task-263-vector-index-dim-drift
**Sub-Slice:** A (Backend-Fix, kein Frontend, kein Admin-Endpoint)
**Priorität:** P1

---

## Problem-Kurzbeschreibung

`backend/app/storage/neo4j_schema.py` legt die Vector-Indexe mit
`CREATE VECTOR INDEX … IF NOT EXISTS` an. Wenn ein Index bereits existiert —
auch mit falscher Dimension — wird die `CREATE`-Anweisung von Neo4j still
ignoriert. Beim Switch von `qwen3-embedding:4b` (2560 dim) auf
`text-embedding-3-small` (1536 dim) am 2026-05-04 führte das zu einem
Dimension-Mismatch: der Neo4j-Index hatte weiterhin 2560 Dimensionen, aber
die Embeddings waren 1536-dimensional. Das erzwang einen manuellen Cleanup
per Cypher-Shell.

Die Falle ist dokumentiert in `docs/2026-05-04-vector-index-dimension-drift-incident.md`.

---

## Gelöster Ansatz

### Private Methode `_ensure_vector_index_dim`

In `Neo4jStorage` wurde eine private Hilfsmethode eingeführt:

```python
def _ensure_vector_index_dim(self, session, index_name: str, expected_dim: int) -> None
```

Sie führt folgende Cypher-Query aus:

```cypher
SHOW INDEXES YIELD name, options
WHERE name = $name
RETURN options.indexConfig.`vector.dimensions` AS dim
```

Drei Fälle:
- Index existiert nicht → no-op (nachfolgende `CREATE … IF NOT EXISTS` übernimmt).
- Gespeicherte Dim == `expected_dim` → no-op.
- Gespeicherte Dim != `expected_dim` → `DROP INDEX <name>` + Warning-Log;
  die nachfolgende `CREATE`-Anweisung legt den Index mit korrekter Dimension neu an.

### Geänderte `_ensure_schema`

`_ensure_schema` ruft `_ensure_vector_index_dim` vor den beiden
`CREATE VECTOR INDEX`-Queries auf:

- vor `CREATE VECTOR INDEX entity_embedding`
- vor `CREATE VECTOR INDEX fact_embedding`

Der Check ist in `try/except` gekapselt, damit ein Fehler im Check-Schritt
(z. B. Neo4j-Version ohne SHOW INDEXES Yield) den normalen Schema-Aufbau
nicht blockiert.

---

## Geänderte Dateien

| Datei | Typ | Beschreibung |
|---|---|---|
| `backend/app/storage/neo4j_storage.py` | Geändert | `_ensure_vector_index_dim` + angepasste `_ensure_schema` |
| `backend/tests/storage/__init__.py` | Neu | Package-Marker für Subdirectory |
| `backend/tests/storage/test_vector_index_dim_drift.py` | Neu | 8 Tests (Unit + Schema-Level) |
| `docs/2026-05-04-263-vector-index-dim-drift-arbeitsprotokoll.md` | Neu | Dieses Dokument |
| `CHANGELOG.md` | Geändert | `### Fixed`-Eintrag unter `[Unreleased]` |

---

## Neue / geänderte Tests

**Datei:** `backend/tests/storage/test_vector_index_dim_drift.py`

### Klasse `TestEnsureVectorIndexDim` (Unit-Tests für die Helper-Methode)

| Test | Szenario |
|---|---|
| `test_no_index_no_drop` | Szenario 1: kein Index → kein DROP |
| `test_dim_mismatch_triggers_drop` | Szenario 2: dim=2560, Config=1536 → DROP |
| `test_dim_match_no_drop` | Szenario 3: dim=1536, Config=1536 → kein DROP |
| `test_warning_logged_on_mismatch` | Bei Mismatch wird `logger.warning` aufgerufen |
| `test_fact_embedding_drop` | Szenario 2 für `fact_embedding` |

### Klasse `TestEnsureSchemaVectorIndexGuard` (via `_ensure_schema`)

| Test | Szenario |
|---|---|
| `test_schema_no_drop_when_no_index` | Kein Index vorhanden → normaler CREATE, kein DROP |
| `test_schema_drops_mismatched_entity_index` | entity_embedding dim=2560 → DROP |
| `test_schema_no_drop_when_dim_matches` | Beide Indexe dim=1536 → kein DROP |

Alle 8 Tests laufen ohne echten Neo4j (Mock-Driver via `object.__new__`).

---

## Manuelle Verifikation

Die folgende Cypher-Query entspricht dem, was `_ensure_vector_index_dim` ausführt
und kann gegen eine laufende Neo4j-Instanz geprüft werden:

```cypher
SHOW INDEXES YIELD name, options
WHERE name = 'entity_embedding'
RETURN options.indexConfig.`vector.dimensions` AS dim
```

Im Mismatch-Fall wird ausgeführt:

```cypher
DROP INDEX entity_embedding
```

Danach erzeugt `_ensure_schema` durch die `CREATE VECTOR INDEX entity_embedding IF NOT EXISTS`-Query
den Index mit der in `Config.VECTOR_DIM` konfigurierten Dimension neu.

---

## Verbleibendes Risiko

- **Index-Drop blockiert bei aktiven Queries:** Ein `DROP INDEX` während einer
  laufenden Vektorsimilarität-Suche kann in Neo4j 5.x zu einem kurzen
  Blockierungszustand führen. Der Drop passiert beim Anwendungsstart
  (`_ensure_schema` wird im Konstruktor aufgerufen), bevor der Flask-Server
  Anfragen annimmt, was das Risiko in der Praxis minimiert. Im Cluster- oder
  Hot-Reload-Szenario (gevent) sollte geprüft werden, ob mehrere Prozesse
  gleichzeitig `_ensure_schema` aufrufen.
- **Knoten mit alter Embedding-Dim:** Bestehende `Entity`- und `RELATION`-Knoten,
  die mit der alten Dimension eingebettet wurden, bleiben im Graph. Der
  Similarity-Search liefert für diese Knoten keine sinnvollen Ergebnisse.
  Ein Re-Embed-Schritt (Admin-Endpoint `POST /api/admin/embeddings/reindex`)
  ist als Folge-Slice vorgesehen und ist explizit **nicht** Teil dieses Fix.
- **Neo4j Community Edition ohne SHOW INDEXES YIELD-Support:** Ältere Neo4j-
  Versionen (< 4.4) kennen `SHOW INDEXES YIELD` nicht. Der Check ist in
  `try/except` gekapselt, so dass er im Fehlerfall übersprungen wird und der
  bisherige Verhalten erhalten bleibt.
