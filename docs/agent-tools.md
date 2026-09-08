# Agent Tools in der Simulation

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Status:** experimentell und standardmäßig deaktiviert.

Dieses Dokument beschreibt den **aktuellen** Tool-Pfad für OASIS/CAMEL-Agenten. Das frühere chronologische Debug-Protokoll aus April 2026 ist keine Laufzeitreferenz mehr.

Code:

- `backend/scripts/agent_tools.py`
- `backend/scripts/sim_runtime/platform_runner.py`
- `backend/scripts/run_parallel_simulation.py`
- `backend/scripts/run_twitter_simulation.py`
- `backend/scripts/run_reddit_simulation.py`

---

## 1. Aktivierung

Default:

```text
ENABLE_AGENT_TOOLS=false
```

Konfiguration:

```dotenv
ENABLE_AGENT_TOOLS=true
MAX_TOOL_CALLS_PER_ACTION=2
```

`SimulationConfigGenerator` friert `enable_agent_tools` und `max_tool_calls_per_action` in die Simulationskonfiguration ein.

Tools sind damit ein explizites Opt-in. Ein Lauf ohne aktivierte Agent-Tools darf nicht so dokumentiert werden, als hätten Agenten live recherchiert.

---

## 2. Aktuell bevorzugter Pfad: native CAMEL FunctionTools

`build_camel_function_tools(config)` erzeugt CAMEL-`FunctionTool`-Objekte. `attach_tools_to_agents(...)` hängt diese an die Social Agents.

Damit werden Tools über das native Tool-/Function-Calling des Modelladapters transportiert. Das ist der bevorzugte Pfad.

Aktuell exponiert der native Builder:

| Tool | Zweck | Voraussetzung |
|---|---|---|
| `web_search(query, num_results)` | Websuche über Tavily | `TAVILY_API_KEY` |
| `web_fetch(url, max_chars)` | HTML/Text einer URL abrufen | Netzwerkzugriff |
| `search_graph(query, limit)` | interner Hybrid-Search gegen Agora-Graph | Neo4j-/Graphzugriff |

`search_graph` wird nur hinzugefügt, wenn der Registry ein funktionierender Graph-Storage zur Verfügung steht.

---

## 3. AgentToolRegistry

`AgentToolRegistry` bündelt Toolimplementierungen und Laufzeitkontext.

Die Registry kennt neben den drei nativen Research-Tools zusätzliche Helfer wie:

- `get_entity_detail`
- `get_related_entities`
- `get_simulation_context`
- `get_recent_posts`

Diese Registry-Funktionen sind **nicht automatisch identisch mit dem Toolset, das einem CAMEL-Agenten nativ exponiert wird**. Maßgeblich ist `build_camel_function_tools()`.

---

## 4. Neo4j- und Secret-Auflösung

`AgentToolRegistry.from_config()` verwendet für die Neo4j-Verbindung:

1. Runtime-Environment,
2. danach persistierte nicht geheime Configwerte,
3. sichere Defaults, wo vorhanden.

Das Neo4j-Passwort wird ausschließlich aus der Runtime-Umgebung gelesen und nicht in `simulation_config.json` persistiert.

Der Graph-Search-Pfad konstruiert derzeit einen `EmbeddingService`. Wegen der bekannten Embedding-SSoT-Lücke #1417 muss bei Tool-/Retrieval-Tests geprüft werden, welche Embedding-Konfiguration effektiv aktiv ist.

---

## 5. Websuche

`web_search` verwendet Tavily:

```text
POST https://api.tavily.com/search
```

Voraussetzung:

```dotenv
TAVILY_API_KEY=...
```

Der Key bleibt Runtime-Secret und gehört nicht in persistierte Simulationsartefakte.

Die Antwort wird für Agenten auf Titel, URL, Snippet und Score reduziert.

---

## 6. `web_fetch` und SSRF-Grenze

Der aktuelle `web_fetch`-Pfad verwendet direkt `requests.get(...)` mit Redirects und einem Timeout und extrahiert lesbaren Text aus HTML.

**Wichtige aktuelle Sicherheitsgrenze:** In `backend/scripts/agent_tools.py::web_fetch` ist auf der geprüften Baseline **kein dedizierter Private-IP-/Loopback-/Metadata-SSRF-Guard vor dem Request sichtbar**.

Das bedeutet:

- Agenteninhalt darf nicht als vertrauenswürdige URL-Policy behandelt werden.
- `ENABLE_AGENT_TOOLS=true` erweitert die Outbound-Netzwerkfläche des OASIS-Subprozesses.
- In sensiblen Netzen sollte `web_fetch` bis zu einer expliziten SSRF-Härtung nur unter kontrollierter Egress-/Netzwerkpolicy aktiviert werden.
- Redirect-Ziele müssen bei einer künftigen Härtung genauso geprüft werden wie die Ausgangs-URL.

Eine allgemeine SSRF-Härtung anderer Agora-Webpfade beweist nicht automatisch, dass dieser Subprozesspfad geschützt ist.

---

## 7. Prompt-/Observation-Sicherheit

Tool-Resultate und Social-Observations sind **untrusted Modellinput**.

Sie können enthalten:

- instruktionsähnlichen Webtext,
- Prompt-Injection,
- manipulierte Agentenposts,
- falsche oder widersprüchliche externe Informationen.

Das Modell darf solche Inhalte als Daten verwenden, aber nicht als neue Systemregeln interpretieren. Zusätzliche Härtung von untrusted Observation wird unter #1224 verfolgt.

---

## 8. Legacy `ToolAwareActionLoop`

`agent_tools.py` enthält weiterhin einen älteren ReACT-/Prompt-Parsing-Pfad (`ToolAwareActionLoop`, `<tool_call>...</tool_call>` und `<action>...</action>`).

Dieser Code ist **nicht die kanonische Erklärung des aktuellen Parallel-Laufs**. Native CAMEL FunctionTools sind der bevorzugte Pfad.

Besonders wichtig wegen #1215: Regeln, die ausschließlich im Legacy-Prompt stehen, dürfen nicht als wirksame Produktionsregel dokumentiert werden, wenn der produktive Lauf diesen Promptpfad nicht erreicht.

Bei Änderungen an Agentenverhalten immer prüfen:

```text
Welche Funktion baut den tatsächlichen Agenten?
Welche Tools landen tatsächlich in ChatAgent.tools?
Welche System-/User-Message erreicht das Modell?
```

Nicht aus einem vorhandenen Promptstring schließen, dass er benutzt wird. Toter Code ist ausgesprochen überzeugend, solange man ihn nur liest.

---

## 9. Tool-Calling-Fähigkeit des Modells

Ein aktivierter Toolpfad funktioniert nur, wenn der effektive Provider-/Modelladapter Tool-Calling unterstützt.

Prüfen:

- effektive `AiRoute`/Modell-ID,
- Provider-Typ,
- Tool-Capability,
- tatsächliche Tool-Calls im Laufzeitlog/Trace.

Ein Lauf mit `ENABLE_AGENT_TOOLS=true`, aber ohne beobachteten Tool-Call ist **kein Nachweis**, dass das Modell recherchiert hat.

---

## 10. Tool-Limits

`MAX_TOOL_CALLS_PER_ACTION` begrenzt die vorgesehenen Toolinteraktionen pro Agentenaktion. Die konkrete Durchsetzung hängt vom aktiven OASIS/CAMEL-Pfad ab.

Tool-Calls sind außerdem echte Modell-/Netzwerkoperationen und müssen in Kosten-/Budgetbetrachtungen einbezogen werden.

Die allgemeine `LLMClient`-Budget-Härtung aus #1478 deckt viele physische Call-Pfade ab; der OASIS-Subprozess besitzt jedoch eigene Adapter-/IPC-Wege. Budget- und Tool-Tests müssen deshalb den tatsächlich verwendeten Subprozesspfad abdecken, nicht nur den Flask-Client.

---

## 11. Verifikation eines Tool-Laufs

Für einen echten Testlauf mindestens nachweisen:

1. `ENABLE_AGENT_TOOLS=true` steht in der effektiven Simulationsconfig.
2. `build_camel_function_tools()` liefert das erwartete Toolset.
3. Tools werden an alle gewünschten Agenten angehängt.
4. Der Provider akzeptiert Tool-Calling.
5. Logs/Traces zeigen einen **realen Tool-Aufruf**.
6. Das Tool-Resultat fließt in eine nachfolgende Agentenentscheidung ein.
7. Outbound-Webtools verhalten sich unter Fehlern/Timeouts kontrolliert.
8. Secrets tauchen nicht in Artefakten/Logs auf.

---

## 12. Was diese Funktion nicht beweist

Live-Webtools machen eine Simulation nicht automatisch „realer“ oder „wahrer“.

Ein Agent kann:

- schlechte Treffer auswählen,
- Suchergebnisse falsch interpretieren,
- Prompt-Injection übernehmen,
- dieselbe Quelle mehrfach echoen,
- externe Information mit Persona-/Simulationsannahmen vermischen.

Toolnutzung ist deshalb eine zusätzliche Evidence-/Attack-Surface, kein Wahrheitsstempel.
