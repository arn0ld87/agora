### Added

- Separate public demo deployment with Supabase email confirmation, workspace-scoped encrypted provider keys, and browser login without the Agora master token.

### Security

- JWT runs use only their workspace's provider key across model, embedding, and background-job paths; missing keys and redirected provider endpoints fail closed.
- Every run persists an explicit credential scope; with `AGORA_DEMO_MODE=true` a run without scope is refused instead of falling back to operator credentials, and keyless/local connections are rejected for workspace routes.
- Workspace routes and workspace embeddings only send keys to the provider's canonical base URL.
- Workspace keys reach the simulation subprocess through an inherited pipe, not through its environment.
- Replay and resume apply the same demo limits and rate limit as simulation start.
- `bootstrap_public_demo_providers.py` refuses operator secrets for demo providers and routing defaults that point to non-demo connections.
- The public overlays blank `LLM_BASE_URL`/`LLM_MODEL_NAME` and further operator keys, and publish no host port for the Supabase gateway.
- With `AGORA_DEMO_MODE=true` the backend refuses to start, and `bootstrap_public_demo_providers.py` refuses to write, if any operator provider env var (`LLM_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `MINIMAX_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_API_KEY`, `LLM_BOOST_API_KEY`, `LLM_BASE_URL`, `LLM_BOOST_BASE_URL`, `TAVILY_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `OLLAMA_BASE_URL`, `OPENAI_BASE_URL`, `OPENAI_API_BASE_URL`) is set in the environment or persisted in `instance/settings.json`; error messages name only the variable, never its value.
- Startup logs a clear warning when Supabase JWT auth is active without `AGORA_DEMO_MODE=true`, since the workspace-credential default-deny then does not apply to background paths like `GraphMemoryUpdater`.
- Workspace-scoped simulation subprocesses no longer load the operator `.env` or `LLM_BOOST_*` settings, and web/agent tools (Tavily) are disabled for workspace runs.
- Restarting a `simulation_run` keeps the original run's credential scope and demo round/budget caps, even when the operator triggers the restart.
- Replaying a run with graph memory update enabled is refused with 403 for JWT principals, matching `/simulation/start`.
- Demo visitors' embeddings run on the operator's dedicated embedding endpoint (`qwen3-embedding:4b`), explicitly allowed via `AGORA_SHARED_EMBEDDING_BASE_URL`; only that exact URL receives the operator's `EMBEDDING_API_KEY`, never a workspace key, and every other endpoint still requires the workspace key at the canonical provider URL.
