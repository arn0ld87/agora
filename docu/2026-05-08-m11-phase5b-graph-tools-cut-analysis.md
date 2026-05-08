# M11 Phase-5b Schnittanalyse: `graph_tools.py`

**Datum:** 2026-05-08
**Autor:** Auditor (read-only, kein Code-Edit)
**Zieldatei:** `backend/app/services/graph_tools.py` (1492 LOC)
**Branch:** `feat/m11-phase5b-graph-tools-cut-analysis`

---

## (1) Zweck und Scope

`graph_tools.py` ist die Graph-Retrieval-Schicht für den Report-Agenten in Agora. Sie kapselt alle Lese-Operationen auf dem Neo4j-basierten `GraphStorage` und stellt dem `ReportAgent` vier Haupt-Werkzeuge bereit: `insight_forge` (multidimensionales LLM-gestütztes Retrieval mit automatischer Sub-Fragen-Dekompositon), `panorama_search` (Breitensuche über alle Edges inkl. abgelaufener Temporal-Daten), `quick_search` (einfaches semantisches Lookup) und `interview_agents` (Echtzeit-Agent-Befragung via `SimulationRunner.interview_agents_batch`). Zusätzlich enthält die Datei sechs Basis-Query-Methoden (`get_all_nodes`, `get_all_edges`, `get_node_detail`, `get_node_edges`, `get_entities_by_type`, `get_entity_summary`, `get_graph_statistics`, `get_simulation_context`), sieben Ergebnis-Dataclasses (`SearchResult`, `NodeInfo`, `EdgeInfo`, `InsightForgeResult`, `PanoramaResult`, `AgentInterview`, `InterviewResult`) und drei private Interview-Hilfsmethoden (`_load_agent_profiles`, `_select_agents_for_interview`, `_generate_interview_questions`, `_generate_interview_summary`) sowie einen statischen Response-Cleaner (`_clean_tool_call_response`).

Der Hotspot-Status ergibt sich aus der Kumulation von fünf fachlich unterschiedlichen Concerns — Daten-Transfer-Objekte, Graph-Basis-Queries, LLM-gestützte Retrieval-Algorithmen, OASIS-Interview-Orchestrierung und Response-Parsing — in einer einzigen 1492-LOC-Datei. Laut `docu/STATUS.md` (Z. 36) hat `graph_tools.py` 667 Statements und 19 % Coverage, da sämtliche LLM- und Neo4j-Pfade nur mit externer Ollama-Instanz und Neo4j abdeckbar sind. `PLAN.md` (Z. 121, 327) listet die Datei als viertgrößten Backend-Hotspot unter F7; das `agora_next_steps_after_p0_2026-05-07.md` war im Worktree nicht vorhanden *(unverifiziert — Datei fehlt im Worktree-Pfad; Kontext wurde aus `PLAN.md` und `CHANGELOG.md` rekonstruiert)*.

---

## (2) Verantwortlichkeiten je Sektion

### Domäne 1: Ergebnis-Dataclasses (DTOs)

| Symbol | Zeilen | Funktion |
|---|---|---|
| `SearchResult` | 25–51 | DTO für einfache Suchergebnisse: `facts`, `edges`, `nodes`, `query`, `total_count`. `to_text()` formatiert für LLM-Input. |
| `NodeInfo` | 55–75 | DTO für einen einzelnen Graph-Knoten mit `uuid`, `name`, `labels`, `summary`, `attributes`. |
| `EdgeInfo` | 79–132 | DTO für eine Graph-Kante inkl. optionaler Temporal-Felder (`valid_at`, `invalid_at`, `expired_at`). Properties `is_expired`, `is_invalid`. |
| `InsightForgeResult` | 136–204 | DTO für InsightForge-Ergebnisse mit `sub_queries`, `semantic_facts`, `entity_insights`, `relationship_chains` und statistischen Zählern. `to_text()` ist der zentrale Wording-Glossar-Pfad (Wording-Test-Pflicht). |
| `PanoramaResult` | 208–266 | DTO für Panorama-Breitensuche: `active_facts`, `historical_facts`, Temporal-Statistiken. |
| `AgentInterview` | 270–317 | DTO für ein einzelnes Interview-Transkript mit Quote-Cleaning-Logik in `to_text()` (Z. 297–316). |
| `InterviewResult` | 321–373 | DTO für gesammeltes Interview-Ergebnis mit `selection_reasoning`, `summary`, `interviewed_count`. |

### Domäne 2: Graph-Basis-Queries (Thin Wrapper über GraphStorage)

| Symbol | Zeilen | Funktion |
|---|---|---|
| `GraphToolsService.__init__` | 396–406 | Initialisiert `self.storage` und `self._llm_client` (lazy via Property `llm`). |
| `GraphToolsService.llm` (Property) | 401–406 | Lazy-init von `LLMClient()` bei erstem Zugriff. |
| `get_all_nodes` | 586–603 | Liest alle Knoten via `storage.get_all_nodes(graph_id)`, mappt auf `NodeInfo`-Liste. |
| `get_all_edges` | 605–630 | Liest alle Kanten via `storage.get_all_edges(graph_id)`, befüllt optionale Temporal-Felder. |
| `get_node_detail` | 632–650 | Einzelner Knoten per UUID via `storage.get_node(uuid)`. |
| `get_node_edges` | 652–683 | Alle Kanten eines Knotens via optimierter `storage.get_node_edges(uuid)` (O(degree) Cypher). |
| `get_entities_by_type` | 685–707 | Label-basierte Knoten-Abfrage via `storage.get_nodes_by_label(graph_id, entity_type)`. |
| `get_entity_summary` | 709–740 | Kombiniert `search_graph` + `get_all_nodes` + `get_node_edges` zu einem Entitäts-Übersichts-Dict. |
| `get_graph_statistics` | 742–765 | Aggregiert Knoten/Kanten-Zähler und Label-/Relations-Verteilungen. |
| `get_simulation_context` | 767–802 | Kombiniert `search_graph` + `get_graph_statistics` + `get_all_nodes` zu einem Kontext-Dict für den Report-Agenten. Ältere API, jetzt via Backwards-Compat-Redirect auf `insight_forge` (in `tool_execution.py`). |

### Domäne 3: Semantic-Search / Fallback (GraphStorage + Keyword-Matching)

| Symbol | Zeilen | Funktion |
|---|---|---|
| `search_graph` | 410–496 | Primäre Suchmethode: delegiert an `storage.search()` (hybrid: vector + BM25), mappt auf `SearchResult`. Bei Fehler Fallback auf `_local_search()`. |
| `_local_search` | 498–584 | Keyword-Score-basierter Fallback: iteriert alle Edges/Nodes aus Storage, berechnet Match-Score, sortiert und gibt `SearchResult` zurück. Keine LLM-Abhängigkeit. |

### Domäne 4: Core Retrieval Tools (LLM-gestützt)

| Symbol | Zeilen | Funktion |
|---|---|---|
| `insight_forge` | 806–939 | Dekompositon via `_generate_sub_queries` (LLM), parallele `search_graph`-Calls pro Sub-Query, Entity-Detail-Anreicherung via `get_node_detail`, Chain-Building. Zentrale 5-Schritt-Pipeline. |
| `_generate_sub_queries` | 941–986 | LLM-Aufruf (`llm.chat_json`) zur Dekompositon einer Frage in Sub-Fragen. Fallback auf hardkodierte Standardfragen bei LLM-Fehler. |
| `panorama_search` | 988–1055 | Breitensuche: lädt alle Nodes + Edges, kategorisiert Facts in `active_facts` vs. `historical_facts` per `is_expired`/`is_invalid`, sortiert nach Relevanz-Score. Keine LLM-Abhängigkeit. |
| `quick_search` | 1057–1077 | Dünner Wrapper um `search_graph` mit `scope="edges"` und konfiguriertem Limit. |

### Domäne 5: Interview-Orchestrierung (OASIS-Kopplung + LLM)

| Symbol | Zeilen | Funktion |
|---|---|---|
| `interview_agents` | 1079–1254 | Haupt-Interview-Methode: lädt Profile (`_load_agent_profiles`), selektiert via LLM (`_select_agents_for_interview`), generiert Fragen (`_generate_interview_questions`), ruft `SimulationRunner.interview_agents_batch` via Lazy-Import auf, parsed API-Response, generiert Summary. |
| `_clean_tool_call_response` | 1257–1275 | Statische Methode. Bereinigt JSON-Tool-Call-Wrapper aus Agent-Responses; extrahiert `content`-Feld via `json.loads` oder Regex-Fallback. |
| `_load_agent_profiles` | 1277–1319 | Disk-I/O: liest `reddit_profiles.json` oder `twitter_profiles.csv` aus `uploads/simulations/{simulation_id}/`. Keine Storage-Abhängigkeit, kein LLM. |
| `_select_agents_for_interview` | 1321–1391 | LLM-Aufruf (`llm.chat_json`) zur Auswahl der relevantesten Agents für ein Interview. Fallback: erste N Profile. |
| `_generate_interview_questions` | 1393–1440 | LLM-Aufruf (`llm.chat_json`) zur Generierung von 3–5 Interview-Fragen. Fallback: generische Standardfragen. |
| `_generate_interview_summary` | 1442–1492 | LLM-Aufruf (`llm.chat`) zur Synthese aller Interview-Transkripte in eine Zusammenfassung. |

---

## (3) Externe Call-Sites

### api/ (Boundary)

| Datei | Genutzte Symbole |
|---|---|
| `app/api/report.py` | `GraphToolsService` (Z. 27, 156, 165, 621, 627) |
| `app/api/runs.py` | `GraphToolsService` (Z. 28, 601, 616) |

Belege:
```
/backend/app/api/report.py:27:from ..services.graph_tools import GraphToolsService
/backend/app/api/report.py:156:    graph_tools = GraphToolsService(storage=storage)
/backend/app/api/runs.py:28:from ..services.graph_tools import GraphToolsService
/backend/app/api/runs.py:601:    graph_tools = GraphToolsService(storage=storage)
```

### services/ (intern)

| Datei | Genutzte Symbole |
|---|---|
| `app/services/report_agent/agent.py` | `GraphToolsService`, `SearchResult`, `InsightForgeResult`, `PanoramaResult`, `InterviewResult` (Z. 59–64, 110, 140, 261, 289, 308, 318) |
| `app/services/report_agent/planning.py` | `agent.graph_tools.get_simulation_context` (Z. 21, via Instanz-Attribut) |
| `app/services/report_agent/tools.py` | `agent.graph_tools` (Z. 85, weitergereicht an `tool_execution.execute_tool`) |
| `app/services/tool_execution.py` | `graph_tools.insight_forge`, `panorama_search`, `quick_search`, `interview_agents`, `get_graph_statistics`, `get_entity_summary`, `get_entities_by_type` (Z. 83, 96, 108, 124, 182, 187, 195) |
| `app/services/graph_tools.py` (Lazy-Import intern) | `from .simulation_runner import SimulationRunner` (Z. 1094, innerhalb `interview_agents`) |
| `app/services/report_logger.py` | Logger-Konfiguration für `'agora.graph_tools'` (Z. 347, 361 — kein Code-Import, nur Logger-Name) |

Belege:
```
/backend/app/services/report_agent/agent.py:59:from ..graph_tools import (
/backend/app/services/report_agent/agent.py:61:    SearchResult,
/backend/app/services/report_agent/planning.py:21:    context = agent.graph_tools.get_simulation_context(
/backend/app/services/tool_execution.py:83:            structured_result = graph_tools.insight_forge(
/backend/app/services/graph_tools.py:1094:        from .simulation_runner import SimulationRunner
```

### tests/

| Datei | Genutzte Symbole |
|---|---|
| `tests/test_wording_glossary.py` | `graph_tools.InsightForgeResult` (Z. 61, direkte Instantiierung für Wording-Test) |
| `tests/test_report_prompts.py` | `graph_tools.__file__` (Z. 170–171, Source-Scan auf verbotene Phrasen in `InsightForgeResult.to_text()`) |
| `tests/test_tool_execution.py` | `graph_tools.insight_forge`, `panorama_search`, `quick_search`, `interview_agents`, `get_graph_statistics`, `get_entity_summary`, `get_entities_by_type` (alle als MagicMock, ~35 Call-Sites) |
| `tests/api/test_simulation_uses_request_model.py` | `patch("app.api.runs.GraphToolsService", ...)` (Z. 219, Monkeypatch) |
| `tests/services/test_report_agent_outline.py` | `agent.graph_tools = MagicMock()`, `agent.graph_tools.get_simulation_context.return_value` (Z. 29–30) |
| `tests/services/test_anti_dekoration.py` | `agent.graph_tools = MagicMock()` (Z. 32) |
| `tests/services/test_report_agent_section_dedup.py` | `agent.graph_tools = MagicMock()` (Z. 18) |

Belege:
```
/backend/tests/test_wording_glossary.py:19:from app.services import graph_tools, report_prompts
/backend/tests/test_wording_glossary.py:61:    result = graph_tools.InsightForgeResult(
/backend/tests/test_report_prompts.py:170:        from app.services import graph_tools
/backend/tests/test_tool_execution.py:49:        graph_tools.insight_forge.return_value = _structured("ifs result")
/backend/tests/api/test_simulation_uses_request_model.py:219:        patch("app.api.runs.GraphToolsService", return_value=fake_graph_tools),
```

---

## (4) Coupling-Analyse

### Interne Methodenkopplung

`insight_forge` (Z. 806–939) ruft intern `_generate_sub_queries` (Z. 941), `search_graph` (Z. 410) und `get_node_detail` (Z. 632) auf — drei verschiedene Domänen in einer Methode. `get_entity_summary` (Z. 709) ruft `search_graph`, `get_all_nodes` und `get_node_edges` auf — ebenfalls domänenübergreifend. `panorama_search` (Z. 988) ruft `get_all_nodes` und `get_all_edges` auf.

`interview_agents` ist der stärkste Coupling-Punkt: es kombiniert alle fünf Domänen in einer Methode — Disk-I/O (`_load_agent_profiles`), LLM-Selection (`_select_agents_for_interview`), LLM-Fragen-Generierung (`_generate_interview_questions`), OASIS-IPC (`SimulationRunner.interview_agents_batch`), Response-Parsing (`_clean_tool_call_response`) und LLM-Summary (`_generate_interview_summary`).

### Geteilte Klassenattribute

`self.storage` (GraphStorage-Instanz) wird von allen Basis-Query-Methoden und transitiv von allen Core-Retrieval-Tools genutzt. `self._llm_client` (lazy via `self.llm`) wird von `insight_forge`, `_generate_sub_queries`, `_select_agents_for_interview`, `_generate_interview_questions` und `_generate_interview_summary` geteilt — fünf Methoden aus zwei fachlich getrennten Domänen.

### Externe Library-Kopplung

- **`GraphStorage` (Neo4j-Adapter):** `storage.search()`, `get_all_nodes()`, `get_all_edges()`, `get_node()`, `get_node_edges()`, `get_nodes_by_label()` — alle Basis-Query-Methoden sind direkte Thin-Wrapper. Ohne `GraphStorage` sind acht der neun Service-Methoden nicht nutzbar.
- **`LLMClient`:** Kopplung in `_generate_sub_queries`, `_select_agents_for_interview`, `_generate_interview_questions`, `_generate_interview_summary` — vier LLM-Calls mit `chat_json` und `chat`.
- **`SimulationRunner` (Lazy-Import Z. 1094):** Circuläre-Import-Gefahr: `graph_tools.py` liegt in `services/`, `simulation_runner.py` ebenfalls. Der Lazy-Import in `interview_agents` verhindert zirkulären Import beim Modul-Load, bleibt aber ein Runtime-Coupling-Punkt.
- **`json`, `csv`, `os` (stdlib):** Nur in `_load_agent_profiles` und `_clean_tool_call_response`. Diese Methoden sind die einzigen mit direkter Disk-I/O ohne Storage-Abstraktion.
- **`re` (Lazy-Import Z. 1199, 1264):** Inline-Imports in `interview_agents` und `_clean_tool_call_response` für Response-Parsing.

### Fachliche Cluster

Eng verzahnt:
- `insight_forge` + `_generate_sub_queries` + `search_graph` + `_local_search` + `get_node_detail` bilden eine Pipeline; Trennung nur sinnvoll als Einheit.
- `interview_agents` + alle vier privaten Interview-Helfer sind eng verzahnt; alle Helfer sind ausschließlich von `interview_agents` aufgerufen.

Fachlich isoliert (schwach gekoppelt):
- Die sieben DTOs (`SearchResult`, `NodeInfo`, `EdgeInfo`, `InsightForgeResult`, `PanoramaResult`, `AgentInterview`, `InterviewResult`) haben keine Rückwärts-Abhängigkeit auf `GraphToolsService`.
- `_local_search` hat keine LLM-Abhängigkeit und nur einen Caller (`search_graph`).
- `panorama_search` und `quick_search` sind kurze Wrapper ohne eigene Logik.

---

## (5) Schnittkandidaten

### Kandidat 1: `graph_dtos`

**Was raus:** `SearchResult` (Z. 25–51), `NodeInfo` (Z. 55–75), `EdgeInfo` (Z. 79–132), `InsightForgeResult` (Z. 136–204), `PanoramaResult` (Z. 208–266), `AgentInterview` (Z. 270–317), `InterviewResult` (Z. 321–373)

**Wohin:** `backend/app/services/graph/graph_dtos.py`

**Pure?** Ja. Die Dataclasses haben keine Side-Effects, keine I/O, keine externen Calls. `AgentInterview.to_text()` enthält string-processing (Zeichen-Filterung, Regex-freie Character-Loop) — kein externer State. `InsightForgeResult.to_text()` ist der Wording-Glossar-kritische Pfad; er muss nach dem Refactor weiterhin vom Wording-Test (`test_wording_glossary.py`) und Source-Scan-Test (`test_report_prompts.py`) abgedeckt werden.

**Risiko:** L — Die DTOs sind in `report_agent/agent.py` importiert (`SearchResult`, `InsightForgeResult`, `PanoramaResult`, `InterviewResult` — vier Klassen, Z. 61–64). `test_wording_glossary.py` importiert das Modul `from app.services import graph_tools` und greift auf `graph_tools.InsightForgeResult` zu. Ein Re-Export aus `graph_tools.py` hält beide Imports grün. `NodeInfo`, `EdgeInfo`, `AgentInterview` haben keine externen Importer — nur intern in `graph_tools.py` genutzt.

**Test-Strategie:** `test_wording_glossary.py` und `test_report_prompts.py` bleiben über Re-Export grün. Nach dem Refactor sollten Unit-Tests für `InsightForgeResult.to_text()` und `EdgeInfo.is_expired`/`is_invalid` in `tests/services/test_graph_dtos.py` angelegt werden (derzeit fehlen direkte Unit-Tests für die DTO-Properties).

---

### Kandidat 2: `graph_reader`

**Was raus:** `GraphToolsService.get_all_nodes` (Z. 586–603), `get_all_edges` (Z. 605–630), `get_node_detail` (Z. 632–650), `get_node_edges` (Z. 652–683), `get_entities_by_type` (Z. 685–707), `get_entity_summary` (Z. 709–740), `get_graph_statistics` (Z. 742–765), `get_simulation_context` (Z. 767–802), `search_graph` (Z. 410–496), `_local_search` (Z. 498–584)

**Wohin:** `backend/app/services/graph/graph_reader.py`

**Pure?** Nein. Alle Methoden delegieren an `self.storage` (GraphStorage / Neo4j) — I/O-Side-Effects. `get_entity_summary` und `get_simulation_context` sind Komposition aus mehreren Storage-Calls. `search_graph` hat einen Exception-Fallback-Pfad auf `_local_search`. Kein LLM, keine Disk-I/O außerhalb Storage-Abstraktion.

**Risiko:** M — `get_graph_statistics`, `get_entity_summary`, `get_entities_by_type` werden direkt in `tool_execution.py` aufgerufen (Z. 182–195) und sind in `test_tool_execution.py` mit ~8 Test-Fällen als MagicMock gestubbt. Eine Pfadänderung ohne Re-Export bricht die Monkeypatch-Stubs. `get_simulation_context` ist in `report_agent/planning.py` (Z. 21) über das Instanz-Attribut `agent.graph_tools` aufgerufen und nicht direkt importiert — kein Monkeypatch-Problem, aber Verhaltensänderung würde alle Planning-Tests betreffen. `test_entity_reader.py` nutzt `get_entities_by_type` eines separaten `EntityReader` (nicht `GraphToolsService`) — kein Konflikt.

**Test-Strategie:** `test_tool_execution.py` bleibt über Re-Export auf `GraphToolsService` grün. Neue Unit-Tests für `_local_search` mit einer Stub-`GraphStorage`-Instanz und vorbefüllten Edges/Nodes sind vor dem Refactor empfohlen — diese Methode hat aktuell null Coverage.

---

### Kandidat 3: `insight_forge_tool`

**Was raus:** `GraphToolsService.insight_forge` (Z. 806–939), `_generate_sub_queries` (Z. 941–986), `panorama_search` (Z. 988–1055), `quick_search` (Z. 1057–1077)

**Wohin:** `backend/app/services/graph/insight_forge_tool.py`

**Pure?** Nein. `insight_forge` ruft `_generate_sub_queries` mit `self.llm.chat_json` auf (LLM-I/O) und intern `search_graph`/`get_node_detail` (Storage-I/O). `panorama_search` liest alle Nodes+Edges via Storage. `quick_search` ist ein Thin-Wrapper ohne eigene Side-Effects.

**Risiko:** M — `insight_forge`, `panorama_search` und `quick_search` sind die am häufigsten in `test_tool_execution.py` gemockten Methoden (~20 Test-Stellen). Alle Mock-Stubs laufen über das `graph_tools`-Objekt (MagicMock-Instanz), nicht über direkten Import — Re-Export ist nicht notwendig, aber die Methode muss weiterhin über `GraphToolsService`-Instanzen erreichbar sein. `insight_forge` hängt von `graph_reader`-Methoden ab (Kandidat 2); dieser Schnitt sollte sequenziell nach Kandidat 2 erfolgen. Der LLM-Aufruf in `_generate_sub_queries` macht Integration-Tests ohne Mock unmöglich — Fallback-Pfad (Z. 981–986) ist testbar.

**Test-Strategie:** `test_tool_execution.py` bleibt grün, weil Mocks auf der Instanz-Ebene operieren. Vor dem Refactor: Unit-Test für `_generate_sub_queries`-Fallback (LLM schlägt fehl → hardkodierte Sub-Queries); Unit-Test für `panorama_search` mit Stub-Storage und gemischten expired/active Edges.

---

### Kandidat 4: `interview_tool`

**Was raus:** `GraphToolsService.interview_agents` (Z. 1079–1254), `_clean_tool_call_response` (Z. 1257–1275), `_load_agent_profiles` (Z. 1277–1319), `_select_agents_for_interview` (Z. 1321–1391), `_generate_interview_questions` (Z. 1393–1440), `_generate_interview_summary` (Z. 1442–1492)

**Wohin:** `backend/app/services/graph/interview_tool.py`

**Pure?** Nein. `interview_agents` hat drei unabhängige Side-Effect-Quellen: Disk-I/O (`_load_agent_profiles` liest CSV/JSON), LLM-Calls (`_select_agents_for_interview`, `_generate_interview_questions`, `_generate_interview_summary`) und OASIS-IPC (`SimulationRunner.interview_agents_batch` via Lazy-Import Z. 1094). `_clean_tool_call_response` ist die einzige Pure-Methode in dieser Gruppe (String-Transformation ohne I/O).

**Risiko:** H — Lazy-Import von `SimulationRunner` (Z. 1094) erzeugt eine Runtime-Kopplung zwischen `graph_tools.py` und `simulation_runner.py`. Beim Verschieben nach `graph/interview_tool.py` muss der Lazy-Import-Pfad angepasst werden (`from ..simulation_runner import SimulationRunner` oder entsprechend dem neuen Pfad). `interview_agents` wird in `test_tool_execution.py` mit `graph_tools.interview_agents.return_value = _structured()` gemockt (Z. 125–142) — kein Import-Problem, da über Instanz. Die Methode hat keine dedizierten Integration-Tests; der komplette OASIS-IPC-Pfad ist ungetestet. Das Risiko liegt im fehlenden Testnetz rund um `_load_agent_profiles` und den Lazy-Import.

**Test-Strategie:** `_clean_tool_call_response` ist ohne Mocks direkt testbar (pure String-Funktion). `_load_agent_profiles` benötigt Fixture-Verzeichnisse mit `reddit_profiles.json` / `twitter_profiles.csv`. `_select_agents_for_interview`- und `_generate_interview_questions`-Fallbacks sind testbar ohne LLM. Vor dem Refactor: Absicherung des Lazy-Import-Pfads und Mock für `SimulationRunner.interview_agents_batch`.

---

### Kandidat 5: `graph_tools_facade` (Klassen-Facade)

**Was raus:** `GraphToolsService` als Klasse (nach Extraktion der vier Kandidaten oben verbleibend: `__init__`, `llm`-Property und Delegations-Methoden)

**Wohin:** `graph_tools.py` verbleibt als dünne Facade, die `GraphToolsService` als aggregierende Klasse re-exportiert; alle Methoden delegieren an die extrahierten Module.

**Pure?** Nein — `GraphToolsService.__init__` injiziert `storage` und `llm_client`.

**Risiko:** L — Dieser Schnitt ist das natürliche Abschluss-PR nach Kandidaten 1–4. Die Facade ist der einzige Import-Pfad für `api/report.py`, `api/runs.py` und `report_agent/agent.py`. Solange `GraphToolsService` aus `graph_tools.py` re-exportiert wird, sind alle Call-Sites grün ohne Import-Änderung.

**Test-Strategie:** Kein neuer Test nötig. Bestehende `test_tool_execution.py`-Mocks und `test_wording_glossary.py`-Imports bleiben durch Re-Export-Pattern grün.

---

## (6) Empfohlene PR-Reihenfolge

1. **PR 1 — Kandidat 1: `graph_dtos`**
   Begründung: Die sieben Dataclasses sind das stable Fundament. Sie haben keine Side-Effects, keine Rückwärts-Abhängigkeiten auf `GraphToolsService` und keine externen Importer außer `report_agent/agent.py` (vier Klassen). Ein Re-Export aus `graph_tools.py` hält alle bestehenden Imports grün. Der Wording-Glossar-Pfad in `InsightForgeResult.to_text()` ist durch die bestehenden Tests (`test_wording_glossary.py`, `test_report_prompts.py`) abgesichert und muss nach dem Refactor unverändert weiter grün bleiben. Dieser Schnitt hat null Risiko für laufende LLM- oder Storage-Pfade.

2. **PR 2 — Kandidat 2: `graph_reader`**
   Begründung: Die Basis-Query-Methoden sind nach PR 1 (DTOs im neuen Pfad) sauber trennbar. `get_graph_statistics`, `get_entity_summary`, `get_entities_by_type` sind direkt in `tool_execution.py` genutzt und in `test_tool_execution.py` gemockt — Re-Export hält die ~8 Monkeypatch-Stubs grün. `search_graph` und `_local_search` sind Voraussetzung für Kandidat 3 (`insight_forge_tool`); sie müssen im neuen Modul stabil sein, bevor `insight_forge` extrahiert wird.

3. **PR 3 — Kandidat 3: `insight_forge_tool`**
   Begründung: `insight_forge`, `panorama_search` und `quick_search` bauen auf den in PR 2 extrahierten `graph_reader`-Methoden auf. Nach PR 1+2 sind die Abhängigkeiten klar getrennt. Die ~20 Monkeypatch-Stubs in `test_tool_execution.py` für diese drei Methoden operieren auf MagicMock-Instanzen und sind unabhängig vom tatsächlichen Import-Pfad. `_generate_sub_queries` kann mit dem LLM-Fallback-Pfad ohne externe Abhängigkeit unit-getestet werden.

4. **PR 4 — Kandidat 4: `interview_tool`**
   Begründung: Die Interview-Methoden sind fachlich vollständig isoliert von Kandidaten 1–3. Der kritische Lazy-Import von `SimulationRunner` muss beim Verschieben explizit angepasst werden — daher erst nach PR 1–3, wenn die Modul-Struktur unter `services/graph/` stabil ist. Das fehlende Test-Netz für den OASIS-IPC-Pfad macht diesen Schnitt zum zweithöchsten Risiko; die Implementierung sollte Fixtures für `_load_agent_profiles` und einen Mock für `SimulationRunner.interview_agents_batch` vorab anlegen.

5. **PR 5 — Kandidat 5: `graph_tools_facade` (Abschluss)**
   Begründung: Nach Extraktion aller vier Kandidaten reduziert sich `GraphToolsService` auf `__init__`, `llm`-Property und Delegations-Methoden. Die Facade bleibt als einziger öffentlicher Import-Punkt für `api/report.py`, `api/runs.py` und `report_agent/agent.py` erhalten — kein Breaking Change. Dieser PR schließt Phase 5b ab und markiert `graph_tools.py` als stabile Thin-Facade unter ~100 LOC.
