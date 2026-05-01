# Agent Tools Integration — Status & Änderungen

**Stand:** 2026-04-21, Abend
**Ziel:** Simulations-Agenten (OASIS/CAMEL) sollen während der Sim echte Web-Tools (Tavily, URL-Fetch, Graph-Search) aufrufen können, bevor sie posten.

## Ausgangslage

Die Agenten posteten nur auf Basis des Knowledge-Graphen aus der hochgeladenen Datei
— kein echter Webzugriff, keine externen Fakten. Erwartung war, dass sie bei einer
Frage wie "Wie entwickelt sich alexle135.de?" die Website tatsächlich besuchen.

## Geänderte Dateien

- `backend/scripts/agent_tools.py` — zentrale Tool-Registry + CAMEL-FunctionTools
- `backend/scripts/run_parallel_simulation.py` — Modellauswahl, Token-Handling, Tool-Attach
- `.env` — `TAVILY_API_KEY` (bereits vorhanden), `ENABLE_AGENT_TOOLS=true` (neu)

## Sequenz der Probleme und Fixes

### 1. Web-Tools gab es noch nicht

**Was:** `AgentToolRegistry` in `agent_tools.py` hatte nur Graph-Tools
(`search_graph`, `get_entity_detail`, `get_related_entities`), keinen Internet-Zugriff.

**Fix:** Zwei neue Methoden auf `AgentToolRegistry`:

- `web_fetch(url, max_chars=2000)` → `requests` + `BeautifulSoup`, entfernt
  nav/footer/script/style, gibt Reintext zurück (max 4000 Zeichen).
- `web_search(query, num_results=5)` → zuerst DuckDuckGo-HTML-Scraping
  (POST `https://html.duckduckgo.com/html/`), später ersetzt durch Tavily-API
  (`POST https://api.tavily.com/search`) mit `TAVILY_API_KEY` aus `.env`.

**Verifiziert:** Tavily findet `alexle135.de` mit Score 1.0.

### 2. `ENABLE_AGENT_TOOLS` stand auf `false`

**Was:** In `simulation_config_generator.py:391` wird `enable_agent_tools` aus
`Config.ENABLE_AGENT_TOOLS` gesetzt — und diese Env-Var war nicht gesetzt
(Default `false`). Der ganze Tool-Zweig wurde in OASIS-Skripten nie
aktiviert.

**Fix:** `ENABLE_AGENT_TOOLS=true` zur `.env` hinzugefügt (direkt nach
`TAVILY_API_KEY`).

### 3. Modellauswahl aus dem UI griff nicht

**Was:** In `run_parallel_simulation.py:1027` stand
`llm_model = os.environ.get("LLM_MODEL_NAME", "")`, `config.get("llm_model")`
war nur Fallback. Heißt: Auswahl im Frontend wurde immer durch `.env`
überschrieben.

**Fix:** Prioritäten umgedreht — `config_model = config.get("llm_model", "")`
zuerst, dann `.env`, dann Fallback `gpt-4o-mini`.

### 4. Reasoning-Tokens fraßen `content`

**Was:** `ModelFactory.create(...)` wurde ohne `model_config_dict` gerufen.
Qwen3/Nemotron-Cloud-Modelle geben bei `think=True` die komplette Antwort
ins `reasoning`-Feld, `content` bleibt leer. CAMEL las aber nur `content`
→ leere Responses, Tool-Parser findet nichts.

**Fix:** `model_config_dict = {"extra_body": {"think": <OLLAMA_THINKING>}}`
gesetzt. `OLLAMA_THINKING=false` propagiert jetzt korrekt bis zum Cloud-Endpoint.

### 5. `max_tokens = 1024` war zu klein

**Was:** CAMEL interpretierte mein `max_tokens=1024` als Gesamt-Budget. Die
System-Message (mit Persona-Bio + Tool-Definitionen) war schon 2500+ Tokens
lang → Warning `"System message alone exceeds token limit: 2531 > 1024"`.

**Fix:** `max_tokens = 8192`. Warnings verschwanden.

### 6. ReACT-Loop war der falsche Ansatz

**Was:** Ich hatte einen eigenen `ToolAwareActionLoop` gebaut, der
`<tool_call>`-Tags per Prompt-Engineering parst. Die Modelle generierten
aber keine solchen Tags — Logs voller "LLM call failed: Error code: 500".
Dieser Ansatz war technisch überflüssig.

**Recherche via Context7 + GitHub:**

- CAMEL `ChatAgent(tools=[FunctionTool(func)])` nutzt **natives**
  OpenAI-function-calling via `tools`-Parameter in `/v1/chat/completions`.
- OASIS' `SocialAgent.__init__` nimmt `tools` an und reicht es an
  `ChatAgent` weiter — **aber** `generate_twitter_agent_graph` und
  `generate_reddit_agent_graph` reichen keinen eigenen `tools`-Parameter durch.
- `ChatAgent` hat `add_tool(tool)` — Tools können nach der Initialisierung
  dynamisch nachgerüstet werden.
- Ollama v1 unterstützt den `tools`-Parameter (Qwen3, Nemotron-Super bestätigt).

**Fix:** Zwei neue Helper in `agent_tools.py`:

- `build_camel_function_tools(config)` → erzeugt 3 `FunctionTool`-Objekte
  mit docstrings + type hints. CAMEL generiert daraus automatisch das
  OpenAI-Schema.
- `attach_tools_to_agents(agent_graph, tools)` → iteriert alle Agents im
  Graph und ruft `agent.add_tool(tool)` pro Tool auf.

In `run_parallel_simulation.py` werden die Tools nach
`generate_*_agent_graph(...)` attached, der alte `tool_loop` ist deaktiviert
(`tool_loop = None`).

**Direkter Isolations-Test bestand:** CAMEL `ChatAgent` + `nemotron-3-super:cloud`
+ `FunctionTool(get_weather)` → Model rief `get_weather("Berlin")` nativ auf,
gab `"Sunny 22°C in Berlin"` korrekt zurück. In einem zweiten Test mit unseren
Tools rief es `web_search(query='alexle135.de', num_results=5)` auf und bekam
5 echte Tavily-Treffer.

### 7. OASIS-System-Prompt sagte nichts von Tools

**Was:** Der Persona-Prompt sagt nur "du bist ein Social-Media-Agent, poste
etwas". Die Tool-Schemas sind zwar im API-Request drin, aber das Modell
priorisiert die Persona-Instruktion.

**Fix:** `attach_tools_to_agents` hängt jetzt auch `TOOL_USE_INSTRUCTION`
an die `system_message.content` jedes Agents an:

```
## Research Tools
You have access to web_search, web_fetch and search_graph tools.
Before posting about any specific website, company, person or topic you
are not certain about, CALL web_search (and optionally web_fetch on a
relevant result) to gather real information first.
```

### 8. `max_iteration = 1` verhinderte Tool-Chains

**Was:** `SocialAgent.__init__` setzt `max_iteration = 1`. Der Agent
kann pro Runde **eine** LLM-Entscheidung treffen — entweder `web_search`
ODER `create_post`, niemals beide nacheinander. Die ganze Idee eines
Tool-Loops (research → act) kann damit nicht funktionieren.

**Fix:** `attach_tools_to_agents` setzt `agent.max_iteration = 4`.

### 9. Debug-Instrumentierung (aktuell noch offen)

**Was:** Trotz attach + prompt-patch + max_iteration → Tools werden immer
noch nicht aufgerufen (DB `trace` table zeigt nur Standard-Actions:
`sign_up, create_post, refresh, like_post, quote_post, repost`).

**Eingebaut zum Diagnostizieren (noch nicht verifiziert):**

- `print("[FunctionTool] >>> web_search(...)")` direkt in die Closure
  → wird definitiv geloggt, wenn das Tool jemals aufgerufen wird.
- Sanity-Dump nach `attach_tools_to_agents`: gibt für Agent 0 aus
  - Liste aller Tool-Namen (soll unsere 3 + OASIS' Action-Tools enthalten)
  - aktueller `max_iteration`-Wert (soll 4 sein)

## Hypothesen für das verbleibende Problem

1. **`add_tool()` aktualisiert internen OpenAI-Schema-Cache nicht.**
   CAMEL könnte die `tools`-Schema-Liste bei `ChatAgent.__init__` einmal
   generieren und cachen; spätere `add_tool()`-Aufrufe ändern zwar
   `self.tools`, aber nicht den Request-Body an Ollama.
   → Lösung: CAMEL-Quellcode prüfen, ggf. `_update_tool_schemas()` o.ä.
   nach `add_tool` aufrufen.

2. **Tools sind da, aber Modell ignoriert sie trotz expliziter Instruktion.**
   → Lösung: Tool-Calling-Mode auf `"required"` zwingen (OpenAI-API-Parameter
   `tool_choice: "required"` oder konkret `{"type":"function","function":{"name":"web_search"}}`).

3. **OASIS' `perform_action_by_llm` überschreibt `user_msg` so, dass
   Tool-Nutzung nicht plausibel erscheint.**
   → Lösung: Agent-Hook patchen oder direkt `perform_action_by_llm`
   monkey-patchen.

## Offene TODO

1. Neuen Sim-Lauf starten, Log auf `[attach_tools] sanity` und
   `[FunctionTool] >>> web_search` prüfen.
2. Je nach Ergebnis: Cache-Rebuild, `tool_choice="required"`, oder
   Monkey-Patch.
3. Sobald Tool-Calls funktionieren: aufgeräumte Version (ReACT-Loop-Code
   und Debug-Prints entfernen).

## Testumgebung

- Modell: `nemotron-3-super:cloud` via Ollama Cloud
  (`http://localhost:11434/v1`)
- Test-Dokument: `test-tavily.md` (~400 Zeichen, Thema: Hacker News)
- Test-Prompt: "Was sind die aktuell meistdiskutierten Themen auf
  news.ycombinator.com?"
- Empfohlene Sim-Settings für Speed: 3–4 Agents, 12 Sim-Hours, Max 10 Rounds,
  nur eine Platform.
