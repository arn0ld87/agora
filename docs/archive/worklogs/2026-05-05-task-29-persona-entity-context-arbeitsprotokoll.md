# Task 29 — Persona-Entity-Context API + Service (Sub-Slice 29, Refs #69)

Datum: 2026-05-05
Branch: `feat/layer-8-task-29-persona-entity-context-backend`

## Was wurde geaendert

### Neue Dateien

1. `backend/app/contracts/persona_entity_context.py` (54 LOC)
   - Pydantic v2 Contracts `EntityRelationship` und `PersonaEntityContext`
   - `model_config = ConfigDict(extra="forbid")` auf beiden Modellen
   - `entity_properties: dict[str, str | int | float | bool]` — nur Skalare
   - `source: Literal["graph", "fallback"]` — kein Union/Any

2. `backend/app/services/persona_entity_context_service.py` (185 LOC)
   - `PersonaEntityContextService(storage: GraphStorage)` Read-only Service
   - `build_context(*, simulation_id, username, profile)` -> `PersonaEntityContext`
   - `_lookup_node(uuid)` nutzt `storage.get_node(uuid)` (direkte GraphStorage-API)
   - `_build_relationships(source_uuid)` nutzt `EntityReader.get_node_edges()`
   - `_coerce_properties()` als Modul-Funktion (None-Drop, list-of-str zu CSV, sonst JSON-stringify)

3. `backend/tests/contracts/test_persona_entity_context.py` (105 LOC)
   - 9 Tests: Pflichtfelder, extra="forbid", Relationships, Skalare, Literal, Round-Trip, Schema-Idempotenz, Fallback-UUID-leer

4. `backend/tests/api/test_persona_entity_context_api.py` (220 LOC nach ruff)
   - 8 Tests: 200 graph, 404 unknown, 400 invalid-id, 400 bogus-id, 200 fallback legacy, 200 fallback graph-miss, 500 kein storage, Relationships-Mapping

### Geaenderte Dateien

5. `backend/app/contracts/__init__.py`
   - Import von `EntityRelationship, PersonaEntityContext`
   - Beide Namen in `__all__` alphabetisch eingeordnet

6. `backend/app/contracts/dump_schemas.py`
   - `PersonaEntityContext` importiert
   - `"persona-entity-context.schema.json": PersonaEntityContext` ins `CONTRACTS`-Dict

7. `backend/app/api/simulation_profiles.py`
   - `from flask import current_app` ergaenzt
   - Imports: `PersonaEntityContext`, `PersonaEntityContextService`
   - Neuer Endpoint `GET /<sim>/profiles/<username>/entity-context`

### Neues Schema

8. `schemas/persona-entity-context.schema.json` (generiert, nicht manuell)

---

## Architektur-Entscheidungen

### Warum `_lookup_node` nur eine Strategie (storage.get_node) nutzt

`GraphStorage.get_node(uuid)` ist eine abstrakte Methode, die in `Neo4jStorage`
implementiert ist und direkten O(1)-Lookup liefert (Cypher: `MATCH (n:Entity {uuid: $uuid})`).
Die im Aufgabendokument vorgeschlagene Cypher-Fallback-Strategie via `execute_cypher` /
`run_query` ist nicht notwendig — diese Methoden existieren nicht auf der `GraphStorage`-
Abstraktion. Der direkteste Weg ist `storage.get_node()`, und er ist in der abstrakten API
als `@abstractmethod` verankert.

### Warum `_coerce_properties` Listen zu CSV-Strings konvertiert

`PersonaEntityContext.entity_properties` ist `dict[str, str | int | float | bool]`.
Pydantic v2 mit `extra="forbid"` lehnt Listen-Werte ab. Neo4j-Attribute koennen jedoch
Listen-of-Strings enthalten (z. B. `interests: ["Tech", "Sport"]`). CSV-Join ist verlustfrei
bei spaeterm UI-Display und erhaelt den semantischen Inhalt ohne den Contract zu verletzen.
Komplexe Strukturen (dict, verschachtelte Listen) werden via `json.dumps` stringifiziert.
None-Werte werden vollstaendig gedroppt (nicht als `null` serialisiert).

### Warum `source="fallback"` statt 404 bei Legacy-Personas

Legacy-Personas (erstellt vor dem Entity-Linking in Sub-Slice 10) haben kein
`source_entity_uuid`. Ein 404-Response waere korrekt aus einer "ist das entity vorhanden?"-
Perspektive, aber unguenstig fuer die UI: Step 2 zeigt alle Personas in einer Liste,
und ein fehlschlagender Context-Request wuerde das gesamte Diff-Panel blockieren.
`source="fallback"` signalisiert dem Frontend klar, dass kein Graph-Context verfuegbar ist,
erlaubt aber trotzdem die Anzeige der Basis-Persona-Felder.

Gleiches gilt fuer den Fall, dass `source_entity_uuid` gesetzt ist, aber der Node nicht
mehr in Neo4j existiert (z. B. nach einem Graph-Reset). Auch hier: Fallback, kein 500.

### Warum `get_node_edges` ueber EntityReader (nicht direkt storage)

`EntityReader.get_node_edges()` wraps `storage.get_node_edges()` mit einem
Exception-Handler, der `[]` zurueckgibt statt zu werfen. Das verhindert, dass ein
fehlgeschlagener Edges-Lookup den gesamten Context-Build abwuergt. Der Service hat
zusaetzlich seinen eigenen try/except um `_reader.get_node_edges()`.

### Edge-Felder: `name` als relation_type, nicht `relation_type`

`neo4j_mappings.edge_to_dict()` gibt Edges mit den Schluesseln `source_node_uuid`,
`target_node_uuid`, und `name` (fuer den Relationship-Typ) zurueck. Das Aufgabendokument
schlug `type` / `relation_type` vor — diese Schlussel existieren nicht im tatsaechlichen
Edge-Dict. Der Service liest `edge.get("name")` als `relation_type`.

---

## Phase-2-Hinweise (nicht in diesem Slice)

- Frontend-UI in Sub-Slice 30: Diff-Panel, das `PersonaEntityContext` visualisiert
- Nach Sub-Slice 30: `Closes #69`

---

## Test-Ergebnis

```
tests/contracts/test_persona_entity_context.py: 9 passed
tests/api/test_persona_entity_context_api.py: 8 passed
Volltest (not llm): 1529 passed, 9 skipped
ruff check app/ tests/: 2 auto-fixes (pre-existing unused import in test file), 0 remaining
mypy neue Dateien: 0 neue Fehler (2 pre-existing Fehler in simulation_profiles.py betreffen unabhaengige Zeilen)
Schema-Dump idempotent: ja
```
