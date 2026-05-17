# Codex-Prompt: Root-Cause OASIS Tool-Call-Problem

Manuell feuern mit:

```bash
codex task --write "$(cat docs/codex-prompt-tool-debug.md)"
```

oder interaktiv via `/codex` und unten stehenden Body einfügen.

---

<task>
Root-cause-Analyse: Warum werden Custom FunctionTools (web_search, web_fetch, search_graph) in OASIS nie aufgerufen, obwohl sie via ChatAgent.add_tool() in _internal_tools registriert sind?

Repo-Root: /mnt/brain/Projekte/MiroFish-Offline

Relevante Dateien (alle lesen, nicht raten):
- backend/scripts/agent_tools.py
- backend/scripts/run_parallel_simulation.py
- backend/.venv/lib/python3.12/site-packages/oasis/social_agent/agent.py
- backend/.venv/lib/python3.12/site-packages/oasis/social_agent/agents_generator.py
- backend/.venv/lib/python3.12/site-packages/camel/agents/chat_agent.py
- backend/.venv/lib/python3.12/site-packages/camel/models/openai_compatible_model.py

Bekannte Fakten:
- SocialAgent.__init__ (agent.py:58-111) übergibt tools-Liste an ChatAgent via `tools=all_tools`.
- attach_tools_to_agents() (agent_tools.py:891) ruft agent.add_tool(tool) für jeden SocialAgent im Graph auf.
- ChatAgent.add_tool (chat_agent.py:769) schreibt in self._internal_tools; kein Cache.
- _get_full_tool_schemas() (chat_agent.py:756) aggregiert external+internal Tools bei jedem Call frisch.
- perform_action_by_llm (agent.py:125) ruft `await self.astep(user_msg)`.
- Isolationstest außerhalb OASIS (reiner ChatAgent + FunctionTool + nemotron-3-super:cloud) funktioniert → Tool wird aufgerufen.
- In OASIS: Debug-Prints `[FunctionTool] >>> web_search(...)` im Tool-Closure erscheinen NIE. Trace-DB zeigt nur OASIS-Action-Tools (create_post, like_post, sign_up, ...).
- Modell: nemotron-3-super:cloud (Ollama Cloud, OpenAI-compatible endpoint http://localhost:11434/v1).
- Web-Recherche deutet auf Ollama-Bug hin: Qwen3-Derivate packen Tool-Calls manchmal ins <think>-Block, Ollama verwirft sie still (Issue #11381). Auch: Tool-Definitionen werden bei Übergabe via `tools`-Parameter als Go-Structs statt JSON serialisiert (Issue #14601).

Zu prüfende Hypothesen (jeweils mit Datei:Zeile belegen oder widerlegen):
H1: astep()-Codepfad in camel/agents/chat_agent.py (~Z.1888) reicht _get_full_tool_schemas() nicht in den Ollama-Request-Body weiter.
H2: perform_action_by_llm oder _aget_model_response in agent.py setzt tool_choice='none' oder überschreibt den Request.
H3: openai_compatible_model.py sendet Tools nicht wenn tool_choice fehlt oder default 'none' ist.
H4: max_iteration=4 wird intern zurückgesetzt (prüfe SocialAgent und OASIS env-loop).
H5: OASIS verwendet Ray-Actors oder Prozess-Isolation — add_tool() wirkt auf anderer Objekt-Instanz als die, die tatsächlich perform_action_by_llm ausführt (agents_generator.py).
H6: Ollama-Upstream-Bug: nemotron/qwen3 packt Tool-Call ins <think>-Block → Ollama verwirft still. Mitigation erforderlich (tool_choice="required" oder Hermes-Embedding).

Aufgabe:
1. Alle genannten Dateien vollständig lesen.
2. Call-Stack verfolgen: perform_action_by_llm → astep → _get_full_tool_schemas → HTTP-Request an Ollama.
3. Exakte Zeile(n) identifizieren wo Custom-Tools aus dem Request herausfallen oder nie ankommen.
4. agents_generator.py vollständig auf Ray/Actor-Pattern oder ähnliche Isolation prüfen.
5. Klares Verdikt: welche Hypothese(n) stimmen, welche nicht.
6. Minimalen konkreten Patch (unified diff) liefern. Falls Root-Cause der Ollama-Bug ist: konkreter Mitigation-Patch (tool_choice forcieren, Hermes-Embedding, o.ä.).
</task>

<compact_output_contract>
- Deutsch, technisch präzise, keine Füllsätze
- Struktur: Verdikt (1-3 Sätze) → Ursache (Datei:Zeile, was passiert) → Patch (unified diff) → verworfene Hypothesen (1 Zeile je)
- Patch muss auf tatsächlich gelesenem Code basieren, keine Annahmen
</compact_output_contract>

<default_follow_through_policy>
Fehlende oder nicht lesbare Datei: explizit nennen, trotzdem Verdikt auf Basis verfügbarer Evidenz.
Mehrere zutreffende Hypothesen: alle benennen, kombinierter Patch.
Keine halbgaren Theorien — nur bewiesene Fakten mit Zeilennummern.
</default_follow_through_policy>

<completeness_contract>
- Jede Hypothese mit konkreter Datei:Zeile bestätigt oder widerlegt
- Patch syntaktisch korrekt Python
- Keine Hypothesen ohne Codebeleg
</completeness_contract>

<action_safety>
Änderungen nur in:
- backend/scripts/agent_tools.py
- backend/scripts/run_parallel_simulation.py
Keine Änderungen in site-packages (venv) außer temporäre Diagnose-Prints falls nötig.
</action_safety>
