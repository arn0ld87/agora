
  # Stabilize OASIS Tool Use and Context Handling

  ## Summary

  Fix the simulation regressions by separating three concerns that are currently conflated:

  - Output length: keep max_tokens as the LLM completion cap.
  - Agent memory context: set CAMEL/OASIS memory budget independently from max_tokens.
  - Ollama request context: only send num_ctx where it is actually supported and useful.

  This is driven by verified runtime facts in the installed stack:

  - In the current CAMEL version, ScoreBasedContextCreator.token_limit is read-only and stores its value in _token_limit.
  - ChatAgent.add_tool() updates _internal_tools, and tool schemas are rebuilt from _internal_tools on each step, so the current “agent 0 has 0 tools” sanity log is not trustworthy.
  - Ollama’s current docs say the OpenAI-compatible /v1 API does not provide a standard way to set context size, and Cloud models are already run at their maximum context by default. Relevant sources:
      - https://docs.ollama.com/openai
      - https://docs.ollama.com/context-length
      - https://docs.ollama.com/cloud
      - https://github.com/ollama/ollama/issues/6544
      - https://github.com/ollama/ollama/issues/5356

  ## Implementation Changes

  ### 1. Split model runtime settings into explicit knobs

  Add a small helper in the simulation runner path that resolves per-model runtime settings:

  - completion_max_tokens: default 8192
  - memory_token_limit: default Config.LLM_CONTEXT_LIMIT
  - ollama_num_ctx: only set for local Ollama models, never for *:cloud

  Use these rules:

  - If model name ends with :cloud:
      - keep extra_body.think
      - omit extra_body.options.num_ctx
      - use memory_token_limit = Config.LLM_CONTEXT_LIMIT unless overridden
  - If model is local Ollama:
      - keep extra_body.think
      - include extra_body.options.num_ctx = memory_token_limit

  Add config support:

  - LLM_MAX_OUTPUT_TOKENS default 8192
  - LLM_CONTEXT_LIMIT keeps its current role as the memory budget default
  - LLM_MODEL_CONTEXT_LIMITS_JSON optional JSON object mapping model name to memory token limit override

  Chosen default behavior:

  - qwen3-coder-next:cloud stays the preferred fallback model.
  - Unknown cloud models fall back to LLM_CONTEXT_LIMIT rather than a smaller hardcoded value.

  ### 2. Replace the broken token_limit setter patch

  In backend/scripts/agent_tools.py:

  - Remove creator.token_limit = ctx_limit
  - Replace it with a guarded patch:
      - fetch creator = memory.get_context_creator()
      - if it has _token_limit, set creator._token_limit = resolved_memory_token_limit
      - log old and new values once per agent
      - if the object shape differs, warn and skip instead of raising

  Do not rebuild agent memory objects or monkey-patch CAMEL globally. The least invasive repo-local fix is to patch the existing creator instance after agent creation.

  ### 3. Fix the false-negative tool sanity check

  Update the post-attach diagnostics to inspect CAMEL’s real registry:

  - read agent.tool_dict first
  - fall back to _internal_tools only if needed
  - log tool names from that dict
  - also log:
      - max_iteration
      - actual memory context limit from memory.get_context_creator()
      - model completion cap from agent.model_backend.model_config_dict

  This turns the current misleading “0 tools” log into a real verification step.

  ### 4. Keep tool attachment logic, but stop blaming the wrong layer

  Keep:

  - agent.add_tool(tool)
  - system prompt extension
  - agent.max_iteration = max(existing, 4)

  Do not add any CAMEL cache-rebuild workaround, because the installed ChatAgent rebuilds tool schemas from _internal_tools during each step().

  ### 5. Remove duplicate main simulation log lines

  In backend/scripts/run_parallel_simulation.py:

  - change log_info() to:
      - use main_logger.info(...) when a logger exists
      - otherwise print(...)
  - do not write both for the same event

  This addresses the duplicated status lines without changing subprocess wiring in simulation_runner.py.

  ### 6. Treat GPU and BERT warnings as non-code issues for this change

  Do not change repo dependencies or PyTorch versions in this fix.

  - The GTX 1060 CUDA warning is an environment/runtime compatibility issue, not a logic bug.
  - The twhin-bert-base pooler warning is expected unless OASIS actually uses the pooler output.

  Only add a short comment in the analysis docs or follow-up notes if needed; no code change for these warnings in this pass.

  ## Public Interfaces / Config

  Add or clarify these env vars:

  - LLM_MAX_OUTPUT_TOKENS
  - LLM_CONTEXT_LIMIT
    Meaning after this fix: default agent-memory context budget, not “force Ollama Cloud request context”
  - LLM_MODEL_CONTEXT_LIMITS_JSON
    Example:

    {
      "qwen3-coder-next:cloud": 262144,
      "qwen3.5:cloud": 262144,
      "qwen2.5:32b": 32768
    }

  No API payload shape needs to change.

  ## Test Plan

  1. Unit test the runtime-settings resolver.
      - Cloud model: no num_ctx, memory limit from override/default, max_tokens unchanged.
      - Local model: num_ctx present, memory limit applied, max_tokens unchanged.
  2. Unit test attach_tools_to_agents().
      - After attach, agent.tool_dict contains the expected tools.
      - agent.max_iteration >= 4
      - context creator internal limit changes from 8192 to the resolved memory limit
      - no property 'token_limit' ... has no setter error is emitted
  3. Smoke test one prepared simulation with tools enabled.
      - Confirm no token_limit patch failed lines.
      - Confirm sanity log reports tools from tool_dict.
      - Confirm duplicate “Attached 3 FunctionTools…” / progress lines are gone.
  4. Regression check with a cloud model and a local model.
      - Cloud: no reliance on num_ctx request overrides.
      - Local: num_ctx still sent.
      - Both: long personas no longer fail from CAMEL’s accidental 8192 memory ceiling.

  ## Assumptions

  - Context7 MCP is not available in this session, so the plan is based on installed package source, official Ollama docs, and GitHub issue history instead.
  - The current target fix is “make the existing architecture stable” rather than upgrading CAMEL/OASIS versions.
  - GPU/PyTorch compatibility is intentionally out of scope for this patch because changing Torch/CUDA would be higher risk than the repo-local fixes above.

