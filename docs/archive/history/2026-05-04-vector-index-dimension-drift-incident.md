# Incident: Vector-Index Dimension-Drift

**Datum:** 2026-05-04
**Schwere:** P1 (Search-Pfad permanent rot)
**Dauer (sichtbar):** ca. 35 min ab User-Meldung bis Recovery
**Status:** behoben (manueller Cleanup), Code-Hardening offen → Issue [#263](https://github.com/arn0ld87/agora/issues/263)
**Stack-Komponenten:** Neo4j 5.x Vector-Index, `app.storage.neo4j_schema`, `app.storage.neo4j_storage._ensure_schema`, `app.search`

## Symptom

Beim Öffnen von Step3/Search-Pfaden im Frontend lieferte der Backend-Logger pro Search-Call zwei Warnungen:

```
WARNING [agora.search._run_edge_vector_search:159]
  Vector edge search failed (index may not exist yet):
  {code: Neo.ClientError.Procedure.ProcedureCallFailed}
  {message: Failed to invoke procedure `db.index.vector.queryRelationships`:
   Caused by: java.lang.IllegalArgumentException:
   Index query vector has 1536 dimensions, but indexed vectors have 2560.}

WARNING [agora.search._run_node_vector_search:199]
  ... 1536 vs 2560 ...
```

Search-Ergebnisse waren leer; Pipeline-State davor (Persona-Generation, Graph-Build) war OK.

## Root Cause

`backend/app/storage/neo4j_schema.py:30-45` legt die Indexe so an:

```cypher
CREATE VECTOR INDEX entity_embedding IF NOT EXISTS
FOR (n:Entity) ON (n.embedding)
OPTIONS {indexConfig: {
    `vector.dimensions`: {_VECTOR_DIM},   // = Config.VECTOR_DIM
    `vector.similarity_function`: 'cosine'
}}
```

`IF NOT EXISTS` greift nur über den **Namen**, nicht über die **Dimension**. Beim Switch des Embedding-Modells (Slice K.1 #256, OpenAI `text-embedding-3-small`, 1536 dims) blieb der alte Index aus der Ollama-`qwen3-embedding:4b`-Phase (2560 dims) bestehen. Storage-Init beim Container-Restart loggte nichts und überging den Drift stillschweigend.

Daten-Folge: alle nach dem Switch geschriebenen 1536-dim-Embeddings wurden als Property in den Knoten/Relations abgelegt, vom Index aber **nicht aufgenommen** (Dimension-Mismatch verhindert das in Neo4j-Vector-Indexen). Beim Search erzeugte `EmbeddingService` einen 1536-Vektor, der gegen den 2560-Index lief → IllegalArgumentException.

## Diagnose

```
SHOW INDEXES YIELD name, type, options, state
WHERE type IN ['VECTOR']
RETURN name, options.indexConfig['vector.dimensions'] AS dim, state;
```

| Index | Dim | State |
|---|---|---|
| `entity_embedding` | 2560 | ONLINE |
| `fact_embedding` | 2560 | ONLINE |

```
MATCH (n:Entity) WHERE n.embedding IS NOT NULL
RETURN size(n.embedding) AS dim, count(n) AS n;
```

| dim | n |
|---|---|
| 2560 | 316 |
| 1536 | 218 |

Bestätigt: Mixed-Dim-State, alte Daten + alte Indexe + neue Daten + falsche Dimension am Index.

Container-Env-Verifizierung:

```
docker exec agora env | grep VECTOR_DIM
→ VECTOR_DIM=1536        # korrekt aus .env
```

Der Code würde also bei einem fresh-Run die Indexe mit 1536 anlegen — der bestehende 2560-Index hat es bisher unterbunden.

## Recovery (manuell, 2026-05-04)

Sequenziell ausgeführt durch den Operator (User), Verify nach jedem Schritt:

1. **Indexe droppen** (User-Bestätigung Option 2: voller Cleanup):

   ```cypher
   DROP INDEX entity_embedding;
   DROP INDEX fact_embedding;
   ```

2. **Alte 2560-dim Daten löschen:**

   ```cypher
   MATCH (n:Entity) WHERE size(n.embedding) <> 1536 DETACH DELETE n;
   --> deleted: 316
   MATCH ()-[r:RELATION]->() WHERE r.fact_embedding IS NOT NULL AND size(r.fact_embedding) <> 1536 DELETE r;
   --> deleted: 0  (durch DETACH DELETE oben bereits weg)
   ```

3. **Waisen-Graphen** (Graph-Knoten ohne Entities) löschen:

   ```cypher
   MATCH (g:Graph) WHERE NOT EXISTS { MATCH (n:Entity {graph_id: g.graph_id}) }
   DETACH DELETE g;
   --> deleted: 14
   ```

4. **Container-Restart** — `_ensure_schema()` läuft im `Neo4jStorage.__init__` und legt die Indexe mit `Config.VECTOR_DIM=1536` neu an:

   ```bash
   docker compose restart agora
   ```

5. **Verify nach Restart:**

   ```cypher
   SHOW INDEXES YIELD name, type, options WHERE type IN ['VECTOR']
   RETURN name, options.indexConfig.`vector.dimensions` AS dim;
   ```

   | name | dim |
   |---|---|
   | `entity_embedding` | **1536** |
   | `fact_embedding` | **1536** |

   ```
   docker logs agora --since 2m | grep -i "embedding"
   → Embedding configuration validated (text-embedding-3-small → 1536 dims)
   ```

   Backend `/health` antwortet `ok`, keine `2560`-/`Vector edge search failed`-Warnings mehr.

## Endstand Daten

| Resource | Vorher | Nachher |
|---|---|---|
| Entities (alle dim) | 534 | 218 |
| Relations (alle dim) | 568 | 255 |
| Distinct Graphen | 16 | 2 |
| Indexe (dim) | 2× 2560 | 2× 1536 |

## Lessons Learned

1. **`IF NOT EXISTS` ist semantisch unzureichend für Vector-Indexe.** Der Mechanismus matcht nur über den Namen. Bei Indexen mit konfigurierten Schema-Properties (Dimension, Similarity-Function) muss eine Drift-Detection vor dem `CREATE` laufen.
2. **Embedding-Modell-Wechsel braucht eine Runbook-Checkliste.** Heute reichte die `.env`-Anpassung nicht; ein DB-Cleanup war nötig. Künftiger Code-Pfad sollte das automatisch machen oder zumindest bei Boot-Time fail-fast loggen.
3. **Polling via Logfile war hilfreich.** `docker logs --since 2m | grep` für die Verify-Phase war schneller als Frontend-Reload.
4. **`Config.VECTOR_DIM` als Single Source of Truth funktioniert** — der Code würde fresh sauber initialisieren. Die Falle ist nur das Persistenz-Layer.

## Nicht gemacht (bewusst)

- **Kein Re-Embedding der gelöschten 316 Entities.** Diese stammten aus Test- und Vorversionen, die sich nicht mehr produktiv nutzen lassen. Wenn Re-Embedding gewollt wäre: separater Slice mit `EmbeddingService.batch_reembed(graph_id)`-Helper.
- **Kein Backup vor dem `DETACH DELETE`.** Im aktuellen Setup gibt es keinen Production-Datenbestand, der zu schützen wäre — Test-/Dev-Stand. Bei künftigen Drift-Vorfällen in Prod: vorher Snapshot.

## Folgearbeit

- **Issue #263** — Code-Hardening: `_ensure_schema()` mit Dimension-Drift-Detection. Tests gegen ephemeral Neo4j (oder integration-mark).
- Optional: Admin-Endpoint `POST /api/admin/embeddings/reindex` für No-Restart-Recovery.
- Doku-Update in [`docs/status.md`](status.md) und [`CLAUDE.md`](../CLAUDE.md) Hot-Spots-Sektion (Embedding-Modell-Wechsel-Runbook).

## Zeitlinie

| Zeit (CEST) | Ereignis |
|---|---|
| ~09:23 | Erste `Vector edge search failed`-Warnings im Container-Log (User-Bericht) |
| ~10:50 | User meldet den Fehler im Orchestrator-Workflow |
| ~10:51 | Diagnose-Cypher-Run, Mixed-Dim-State bestätigt |
| ~10:53 | User-Auswahl: Option 2 (Index-Drop + Daten-Cleanup) |
| ~10:54 | Sequentielles Cypher: Drop + DETACH DELETE + Graph-Cleanup |
| ~10:55 | Container-Restart, Health 30 s nach Restart wieder grün |
| ~10:56 | Verify: Indexe dim=1536, keine Warnings, `/health` ok |
| ~10:57 | Issue [#263](https://github.com/arn0ld87/agora/issues/263) angelegt für Code-Hardening |

## Referenzen

- [Issue #263](https://github.com/arn0ld87/agora/issues/263) — Code-Hardening
- [Slice K.1 (PR #256)](https://github.com/arn0ld87/agora/pull/256) — OpenAI-Embedding-Switch (Auslöser)
- [Slice K.2 (PR #257)](https://github.com/arn0ld87/agora/pull/257) — Compose-Substitution-Fix
- `backend/app/storage/neo4j_schema.py:28-45` — `CREATE VECTOR INDEX … IF NOT EXISTS`
- `backend/app/storage/neo4j_storage.py:112-119` — `_ensure_schema`
