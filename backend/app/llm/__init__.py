"""
LLM package — split of the former ``app.utils.llm_client`` monolith (#582).

Sub-modules:
    context.py            Ollama num_ctx heuristic/resolution.
    json_mode.py           Strict-schema enforcement, json-mode env toggles,
                            LLM-JSON envelope stripping/repair.
    providers/              Provider-detection + provider-specific quirks
                            (base/openai/ollama). No new abstraction layer yet
                            (see #590/#591) — plain helper functions only.
    tool_calls.py           Native OpenAI function-calling (chat_with_tools).
    client.py               ``LLMClient`` facade.
    factory.py              ``build_client_from_profile``.

``app.utils.llm_client`` remains the stable public import path (re-export
shim) — import from there unless you are working inside this package.
"""
