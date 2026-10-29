### Fixed (Simulation Runtime — Parität SinglePlatformRunner mit Parallel-Runner)

- **Parität des SinglePlatformRunner bei Modellauswahl und Provider-Features (Befund 6.1):**
  - Modell-Präzedenz: `config["llm_model"]` > `os.environ["LLM_MODEL_NAME"]` > Default `qwen3-coder-next:cloud`.
  - Ollama-URL-Normalisierung via `resolve_camel_ollama_url`.
  - Runtime-Settings via `resolve_model_runtime_settings`: `:cloud`-Modelle erhalten kein `num_ctx`, lokale Modelle setzen `num_ctx` entsprechend Limit.
  - Gemini Thought-Signature-Integration mit `GOOGLE_API_KEY`/`GEMINI_API_KEY`-Export.
  - OpenAI MiniMax-Unterstützung via `build_minimax_extra_body`.
  - Extrahierte LLM-Konfigurationslogik in neuem Modul `sim_runtime.llm_config`.

- **Parität des SinglePlatformRunner bei Stance, FunctionTools und Live-Events (Befund 6.2):**
  - `_get_profile_path` wendet `augment_profile_with_stance` an, sodass konfigurierte Persona-Stances wirksam werden.
  - Native CAMEL `FunctionTool`-Unterstützung via `attach_function_tools_to_agent_graph` vor Legacy-Tool-Loop.
  - Runde 0: liest initiale Posts via `fetch_new_actions_from_db` mit echter `post_id` in `PlatformActionLogger` und emittiert `_emit_post_created_to_redis`.
  - Reguläre Runden: emittiert `PostCreatedEvent` für `CREATE_POST`, `CREATE_COMMENT`, `REPOST` und `QUOTE_POST` an Redis.
